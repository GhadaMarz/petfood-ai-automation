from pathlib import Path
import pandas as pd

# Load the Royal Canin product data from the project data directory.
DATA = Path(__file__).resolve().parent / "data"
df = pd.read_csv(DATA / "royal_canin_products.csv", dtype={"code": str})

# Define fields used to calculate product completeness and the reference time for stale records.
KEY_FIELDS = ["product_name", "categories", "ingredients_text", "quantity", "countries"]
today = pd.Timestamp.now(tz="UTC")

# Convert values to usable types before checking numeric ranges and record age.
qty = pd.to_numeric(df["product_quantity"], errors="coerce")
prot = pd.to_numeric(df["proteins_100g"], errors="coerce")
fat = pd.to_numeric(df["fat_100g"], errors="coerce")
modified = pd.to_datetime(df["last_modified_datetime"], errors="coerce", utc=True)
code = df["code"].fillna("")

# Evaluate each data-quality rule for every product.
rules = {
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
}

# Combine rule results into per-product issue details and completeness scores.
issues = pd.DataFrame(rules)
df["issues"] = issues.apply(lambda r: ", ".join(issues.columns[r.values]), axis=1)
df["issue_count"] = issues.sum(axis=1)
df["completeness_score"] = (df[KEY_FIELDS].notna().mean(axis=1) * 100).round(0)

# Save the checked products and their quality results.
df.to_csv(DATA / "dq_report.csv", index=False)

# Summarize the overall results and counts for each quality rule.
with_issue = df["issue_count"] > 0
print(f"Products checked: {len(df)}")
print(f"Products with at least one issue: {with_issue.sum()} ({with_issue.mean():.0%})")
print(f"Average completeness score: {df['completeness_score'].mean():.0f}%\n")
print("Issues by rule:")
print(issues.sum().sort_values(ascending=False).to_string())
print("\nSaved: data/dq_report.csv")