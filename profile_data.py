from pathlib import Path
import re
import unicodedata
import pandas as pd

catalogue_path = (Path(__file__).resolve().parent / "data" / "en.openpetfoodfacts.org.products.csv")

# Load the tab-separated catalogue and keep mixed-type columns intact.
catalogue = pd.read_csv(catalogue_path, sep="\t", low_memory=False, dtype={"code": str})

# Report the catalogue size and the percentage of missing values in each column.
print(f"Number of rows: {len(catalogue)}")
print("\nPercentage of missing values per column:")
print((catalogue.isna().mean() * 100).map(lambda percentage: f"{percentage:.2f}%").to_string())

# Count repeated barcode values after their first occurrence.
print(f"\nNumber of duplicate barcodes: {catalogue['code'].duplicated().sum()}")

# Show weight and protein ranges using the corresponding source columns.
for label, column in (
    ("net_weight_g", "product_quantity"),
    ("protein_pct", "proteins_100g"),
):
    values = pd.to_numeric(catalogue[column], errors="coerce")
    print(f"\n{label} min: {values.min()}")
    print(f"{label} max: {values.max()}")

# Broad first-pass filter: keep every possible Royal Canin product, false positives are triaged later.
TARGETS = ("royal", "canin", "royalcanin")
MAX_TYPOS = 1
# Royal Canin GS1 company prefixes, as 13-digit GTINs: France, North America (UPC), Brazil (two prefixes).
# 9003579 (Austria) is left out on purpose: it is shared with other Mars brands such as Whiskas and Kitekat.
RC_BARCODE_PREFIXES = ("3182550", "0030111", "7896181", "7908248")
# Other brands caught by the filter or the barcode prefix, excluded after review (compared without case or symbols).
EXCLUDED_BRANDS = ("zooroyal", "brekkies", "affinity", "clubspecialperformance", "pureorigine")


def edit_distance(a, b):
    # Levenshtein distance, short-circuited when the length gap alone exceeds the typo budget.
    if abs(len(a) - len(b)) > MAX_TYPOS:
        return MAX_TYPOS + 1
    previous = list(range(len(b) + 1))
    for i, char_a in enumerate(a, 1):
        current = [i]
        for j, char_b in enumerate(b, 1):
            current.append(min(previous[j] + 1, current[j - 1] + 1, previous[j - 1] + (char_a != char_b)))
        previous = current
    return previous[-1]


def match_reason(text):
    # Ignore case, accents and punctuation, then compare words and adjacent word pairs to the targets.
    text = unicodedata.normalize("NFKD", str(text)).encode("ascii", "ignore").decode().lower()
    words = re.findall(r"[a-z0-9]+", text)
    candidates = words + [a + b for a, b in zip(words, words[1:])]
    for word in candidates:
        if "royal" in word or "canin" in word:
            return f"contains:{word}"
    for word in candidates:
        if any(edit_distance(word, target) <= MAX_TYPOS for target in TARGETS):
            return f"typo:{word}"
    return None


# Match on brands; fall back to product_name only when brands is empty (no letters or digits).
brands_empty = ~catalogue["brands"].fillna("").str.contains(r"[^\W_]", regex=True)
source_column = pd.Series("brands", index=catalogue.index).where(~brands_empty, "product_name")
source_text = catalogue["brands"].where(~brands_empty, catalogue["product_name"])
reasons = source_text.dropna().map(match_reason).reindex(catalogue.index)
reasons = (source_column + ":" + reasons).where(reasons.notna())
# Pad 12-digit UPC codes to 13-digit GTINs so North American prefixes compare like the others.
code = catalogue["code"].fillna("")
gtin13 = code.where(code.str.len() != 12, "0" + code)
for prefix in RC_BARCODE_PREFIXES:
    reasons[gtin13.str.startswith(prefix) & reasons.isna()] = f"barcode:{prefix}"

# Drop excluded brands, whatever rule matched them (the brand, or the product name when the brand is empty).
compact_text = source_text.fillna("").map(
    lambda t: re.sub(r"[^a-z0-9]", "", unicodedata.normalize("NFKD", t).encode("ascii", "ignore").decode().lower()))
excluded = reasons.notna() & compact_text.map(lambda t: any(brand in t for brand in EXCLUDED_BRANDS))
print(f"\nExcluded brands removed: {excluded.sum()}")
reasons[excluded] = None

# Save the fields needed for further analysis, with the reason each product was kept.
rc = catalogue[reasons.notna()].copy()
rc["match_reason"] = reasons
cols = ["code", "product_name", "brands", "categories", "ingredients_text",
    "quantity", "product_quantity", "countries", "last_modified_datetime",
    "proteins_100g", "fat_100g", "completeness", "data_quality_errors_tags", "match_reason"]
rc[cols].to_csv(Path(__file__).resolve().parent / "data" / "royal_canin_products.csv", index=False,
    sep=";", decimal=",", encoding="utf-8-sig")  # French Excel format
print(f"\nRoyal Canin products saved: {len(rc)}")
print(rc["match_reason"].str.split(":").str[0].value_counts().to_string())