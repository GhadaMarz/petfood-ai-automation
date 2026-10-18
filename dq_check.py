from pathlib import Path
import re
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
DATA = Path(__file__).resolve().parent / "data"
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


def suggest_brand(df):
    """"Royal Canin" when the brand only differs by case or spaces, or when it is empty or generic on a
    Royal Canin barcode; empty otherwise, so that ambiguous brands and other manufacturers stay in manual review."""
    brand = normalized_brand(df["brands"])
    case_variant = (brand == "royal canin") & (df["brands"] != "Royal Canin")
    blank_on_rc_barcode = (brand.eq("") | brand.isin(GENERIC_BRANDS)) & has_rc_barcode(df["code"])
    return pd.Series("", index=df.index).where(~(case_variant | blank_on_rc_barcode), "Royal Canin")


def evaluate_rules(df, today):
    """Return one boolean column per data-quality rule, True when the product has the defect."""
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
        "non_standard_brand": df["brands"].str.strip() != "Royal Canin",
        "stale_record": modified < today - pd.DateOffset(years=3),
        "missing_brand": df["brands"].isna(),
        "brand_barcode_conflict": has_rc_barcode(df["code"]) & other_manufacturer,
    })


def check(df, today):
    """Add issues, issue_count, completeness_score and suggested_quantity to the products; also return the rule table."""
    df = df.copy()
    issues = evaluate_rules(df, today)
    df["issues"] = issues.apply(lambda r: ", ".join(issues.columns[r.values]), axis=1)
    df["issue_count"] = issues.sum(axis=1)
    df["completeness_score"] = (df[KEY_FIELDS].notna().mean(axis=1) * 100).round(0)

    # Suggest a weight in grams from the product name when the quantity is missing or implausible.
    needs_quantity = issues["missing_quantity"] | issues["implausible_weight"]
    df["suggested_quantity"] = df["product_name"].where(needs_quantity).map(extract_weight_g).astype("Int64")
    df["suggested_brand"] = suggest_brand(df)
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
    print(f"Brands suggested: {(df['suggested_brand'] != '').sum()}")
    print("\nSaved: data/dq_report.csv")
