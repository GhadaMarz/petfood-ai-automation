from pathlib import Path
import re
import unicodedata
import pandas as pd

# A weight written in a product name: "4KG", "1,5 kg", "400 GR", "12+2 KG" (bonus) or "12X85G" (multipack).
WEIGHT = re.compile(r"(?:(\d+)\s*[x×]\s*)?(\d+(?:[.,]\d+)?)(?:\s*\+\s*(\d+(?:[.,]\d+)?))?\s*(kg|gr|g|lbs?|oz)(?![a-z])",
    re.IGNORECASE)
GRAMS_PER_UNIT = {"kg": 1000, "gr": 1, "g": 1, "lb": 453.592, "lbs": 453.592, "oz": 28.3495}


def extract_weight_g(name):
    """Return the weight in grams found in a product name, or None. "15 KG+3KG" bonus bags are added up."""
    if not isinstance(name, str):
        return None
    total, previous_end = 0.0, None
    for match in WEIGHT.finditer(name):
        if previous_end is not None and name[previous_end:match.start()].strip() != "+":
            break
        count, amount, bonus, unit = match.groups()
        amount = float(amount.replace(",", ".")) + (float(bonus.replace(",", ".")) if bonus else 0)
        total += int(count or 1) * amount * GRAMS_PER_UNIT[unit.lower()]
        previous_end = match.end()
    return round(total) if total else None


# Fields used to calculate product completeness.
DATA = Path(__file__).resolve().parents[1] / "data"
KEY_FIELDS = ["product_name", "categories", "ingredients_text", "quantity", "countries"]

# Royal Canin GS1 prefixes trusted for brand suggestions (France, North America), as 13-digit GTINs.
RC_BARCODE_PREFIXES = ("3182550", "0030111")
# Brand values that name a product type rather than a manufacturer.
GENERIC_BRANDS = {"dog food", "cat food"}


def normalized_brand(brands):
    """Lower case, single spaces, no leading or trailing spaces; empty string when the brand is missing."""
    return brands.fillna("").str.replace(r"\s+", " ", regex=True).str.strip().str.lower()


def has_rc_barcode(codes):
    # Pad 12-digit UPC codes to 13-digit GTINs so the North American prefix compares like the French one.
    codes = codes.fillna("")
    return codes.where(codes.str.len() != 12, "0" + codes).str.startswith(RC_BARCODE_PREFIXES)


def standardize_brand(brands):
    """Rewrite obvious variants of Royal Canin, which only differ by case or spaces ("royal canin", "ROYAL  CANIN"),
    as "Royal Canin". Any other value, including a missing brand, is left unchanged for the data steward."""
    return brands.where(normalized_brand(brands) != "royal canin", "Royal Canin")


# Country names as written in the catalogue (English, French, Spanish, Portuguese, Russian) -> English name. A name
# leaves no doubt: it is standardized automatically. Keys are written as country_key() returns them.
COUNTRY_NAMES = {
    "australia": "Australia", "belgium": "Belgium", "belgique": "Belgium", "brasil": "Brazil", "brazil": "Brazil",
    "canada": "Canada", "france": "France", "francia": "France", "germany": "Germany", "allemagne": "Germany",
    "india": "India", "indonesia": "Indonesia", "indonesie": "Indonesia", "iran": "Iran", "italy": "Italy",
    "italie": "Italy", "latvia": "Latvia", "mexico": "Mexico", "netherlands": "Netherlands",
    "the netherlands": "Netherlands", "new caledonia": "New Caledonia", "new zealand": "New Zealand",
    "norway": "Norway", "philippines": "Philippines", "poland": "Poland", "portugal": "Portugal", "russia": "Russia",
    "russie": "Russia", "россия": "Russia", "senegal": "Senegal", "serbia": "Serbia", "somalia": "Somalia",
    "south africa": "South Africa", "spain": "Spain", "espana": "Spain", "espagne": "Spain", "sweden": "Sweden",
    "switzerland": "Switzerland", "suisse": "Switzerland", "thailand": "Thailand",
    "trinidad and tobago": "Trinidad and Tobago", "tunisia": "Tunisia", "united kingdom": "United Kingdom",
    "united states": "United States",
}
# Codes, abbreviations and regions: probable, not certain, so the country is suggested to the data steward.
COUNTRY_CODES = {
    "be": "Belgium", "ca": "Canada", "ch": "Switzerland", "cz": "Czechia", "es": "Spain", "fr": "France",
    "gb": "United Kingdom", "it": "Italy", "mx": "Mexico", "pf": "French Polynesia", "pt": "Portugal",
    "us": "United States", "usa": "United States", "gironde": "France",
}


def country_key(country):
    """Lower case, without the "en:" language prefix, accents or hyphens: "en:united-states" -> "united states"."""
    key = re.sub(r"^[a-z]{2}:", "", country.strip().lower()).replace("-", " ")
    return "".join(c for c in unicodedata.normalize("NFD", key) if unicodedata.category(c) != "Mn").strip()


def join_countries(countries):
    return ", ".join(dict.fromkeys(countries))  # without duplicates, in their original order


def standardize_countries(value):
    """Return (standardized, suggested) for a comma-separated countries value. Country names, in any language, are
    rewritten as English names; codes and abbreviations are only resolved in the suggestion, which is empty when
    there is nothing to suggest. Unknown values are kept as they are, for manual review."""
    if not isinstance(value, str):
        return value, ""
    countries = [c.strip() for c in value.split(",") if c.strip()]
    keys = [country_key(c) for c in countries]
    standardized = join_countries(COUNTRY_NAMES.get(k, c) for k, c in zip(keys, countries))
    if not any(k in COUNTRY_CODES for k in keys):
        return standardized, ""
    return standardized, join_countries(COUNTRY_NAMES.get(k) or COUNTRY_CODES.get(k, c) for k, c in zip(keys, countries))


def country_invalid(value):
    """True when a countries value holds anything else than country names (a code, a region, an unknown value)."""
    return isinstance(value, str) and any(country_key(c) not in COUNTRY_NAMES for c in value.split(",") if c.strip())


def suggest_brand(df):
    """"Royal Canin" when the brand is empty or generic on a Royal Canin barcode; empty otherwise, so that ambiguous
    brands and other manufacturers stay in manual review. Case and space variants need no suggestion: they are
    standardized automatically."""
    brand = normalized_brand(df["brands"])
    blank_on_rc_barcode = (brand.eq("") | brand.isin(GENERIC_BRANDS)) & has_rc_barcode(df["code"])
    return pd.Series("", index=df.index).where(~blank_on_rc_barcode, "Royal Canin")


def evaluate_rules(df, today):
    """Return one boolean column per data-quality rule, True when the product has the defect. Brand rules apply to the
    standardized brand: a case or space variant of Royal Canin is corrected automatically, not reported as a defect."""
    # Convert values to usable types before checking numeric ranges and record age.
    qty = pd.to_numeric(df["product_quantity"], errors="coerce")
    prot = pd.to_numeric(df["proteins_100g"], errors="coerce")
    fat = pd.to_numeric(df["fat_100g"], errors="coerce")
    modified = pd.to_datetime(df["last_modified_datetime"], errors="coerce", utc=True)
    code = df["code"].fillna("")
    brand = normalized_brand(df["brands"])
    other_manufacturer = brand.ne("") & ~brand.isin(GENERIC_BRANDS) & ~brand.str.contains("royal|canin")

    return pd.DataFrame({
        "missing_name": df["product_name"].isna(),
        "missing_category": df["categories"].isna(),
        "missing_ingredients": df["ingredients_text"].isna(),
        "missing_quantity": df["quantity"].isna() & qty.isna(),
        "implausible_weight": (qty <= 0) | (qty > 20000),
        "implausible_protein": (prot < 0) | (prot > 60),
        "implausible_fat": (fat < 0) | (fat > 40),
        "invalid_barcode": ~code.str.fullmatch(r"\d{8}|\d{12,14}"),
        "duplicate_barcode": code.duplicated(keep=False) & (code != ""),
        "brand_invalid_value": df["brands"].notna() & (standardize_brand(df["brands"]) != "Royal Canin"),
        "stale_record": modified < today - pd.DateOffset(years=3),
        "missing_brand": df["brands"].isna(),
        "brand_barcode_conflict": has_rc_barcode(df["code"]) & other_manufacturer,
        "country_invalid_value": df["countries"].map(country_invalid).astype(bool),
    })


def check(df, today):
    """Add issues, issue_count, completeness_score, suggested_quantity, suggested_brand, standardized_brand,
    brand_auto_corrected, standardized_countries, suggested_countries and countries_auto_corrected to the products;
    also return the rule table. The original brand and countries are kept in "brands" and "countries"."""
    df = df.copy()
    issues = evaluate_rules(df, today)
    df["issues"] = issues.apply(lambda r: ", ".join(issues.columns[r.values]), axis=1)
    df["issue_count"] = issues.sum(axis=1)
    df["completeness_score"] = (df[KEY_FIELDS].notna().mean(axis=1) * 100).round(0)

    # Suggest a weight in grams from the product name when the quantity is missing or implausible.
    needs_quantity = issues["missing_quantity"] | issues["implausible_weight"]
    df["suggested_quantity"] = df["product_name"].where(needs_quantity).map(extract_weight_g).astype("Int64")
    df["suggested_brand"] = suggest_brand(df)
    df["standardized_brand"] = standardize_brand(df["brands"])
    df["brand_auto_corrected"] = df["brands"].notna() & (df["standardized_brand"] != df["brands"])
    countries = df["countries"].map(standardize_countries)
    df["standardized_countries"] = countries.str[0]
    df["suggested_countries"] = countries.str[1]
    df["countries_auto_corrected"] = df["countries"].notna() & (df["standardized_countries"] != df["countries"])
    return df, issues


if __name__ == "__main__":
    # Load the Royal Canin product data, check it and save the results.
    products = pd.read_csv(DATA / "royal_canin_products.csv", dtype={"code": str},
        sep=";", decimal=",", encoding="utf-8-sig")
    df, issues = check(products, pd.Timestamp.now(tz="UTC"))
    df.to_csv(DATA / "dq_report.csv", index=False, sep=";", decimal=",", encoding="utf-8-sig")  # French Excel format

    # Summarize the overall results and counts for each quality rule.
    needs_quantity = issues["missing_quantity"] | issues["implausible_weight"]
    with_issue = df["issue_count"] > 0
    print(f"Products checked: {len(df)}")
    print(f"Products with at least one issue: {with_issue.sum()} ({with_issue.mean():.0%})")
    print(f"Average completeness score: {df['completeness_score'].mean():.0f}%\n")
    print("Issues by rule:")
    print(issues.sum().sort_values(ascending=False).to_string())
    print(f"\nQuantities suggested from the product name: {df['suggested_quantity'].notna().sum()} of {needs_quantity.sum()}")
    print(f"Brands standardized automatically: {df['brand_auto_corrected'].sum()}")
    print(f"Brands suggested for steward review: {(df['suggested_brand'] != '').sum()}")
    print(f"Countries standardized automatically: {df['countries_auto_corrected'].sum()}")
    print(f"Countries suggested for steward review: {(df['suggested_countries'] != '').sum()}")
    print("\nSaved: data/dq_report.csv")
