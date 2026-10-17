"""Prepare a clean, consistently formatted product file for Salesforce import.
This script selects the catalogue fields Salesforce needs, applies field-length
limits, converts numeric and date values, and excludes products without barcodes.
"""

from pathlib import Path
import pandas as pd

# Load the data-quality report created by the previous processing step.
DATA = Path(__file__).resolve().parent / "data"
df = pd.read_csv(DATA / "dq_report.csv", dtype=str, sep=";", encoding="utf-8-sig")

# Convert numeric fields safely (the report uses decimal commas) and limit text fields to their import lengths.
num = lambda c: pd.to_numeric(df[c].str.replace(",", ".", regex=False), errors="coerce")
txt = lambda c, n: df[c].fillna("").str[:n]

# Rename and format catalogue fields to match the Salesforce import template.
out = pd.DataFrame({
    "Barcode": df["code"],
    "Product Name": txt("product_name", 255),
    "Brand": txt("brands", 255),
    "Categories": txt("categories", 1000),
    "Ingredients": txt("ingredients_text", 5000),
    "Quantity": txt("quantity", 255),
    "Weight (g)": num("product_quantity"),
    "Suggested Weight (g)": num("suggested_quantity"),
    "Countries": txt("countries", 255),
    "Last Modified": pd.to_datetime(df["last_modified_datetime"], errors="coerce", utc=True).dt.strftime("%Y-%m-%d"),
    "Protein (%)": num("proteins_100g"),
    "Fat (%)": num("fat_100g"),
    "Completeness Score": num("completeness_score"),
    "Issue Count": num("issue_count"),
    "DQ Issues": txt("issues", 1000),
}).dropna(subset=["Barcode"])

# Export only products with barcodes and report the number of rows prepared.
out.to_csv(DATA / "salesforce_import.csv", index=False)
print(f"Rows ready for Salesforce: {len(out)}")