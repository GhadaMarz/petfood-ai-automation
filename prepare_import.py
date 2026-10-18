"""Prepare a clean, consistently formatted product file for Salesforce import.
This script selects the catalogue fields Salesforce needs, applies field-length
limits, converts numeric and date values, and excludes products without barcodes.
"""

from pathlib import Path
import pandas as pd

# Load the data-quality report created by the previous processing step.
DATA = Path(__file__).resolve().parent / "data"
df = pd.read_csv(DATA / "dq_report.csv", dtype=str, sep=";", encoding="utf-8-sig")

# Convert numeric fields safely (the report uses decimal commas), round them to the decimals of their Salesforce
# field, and limit text fields to their import lengths.
num = lambda c, decimals=0: pd.to_numeric(df[c].str.replace(",", ".", regex=False), errors="coerce").round(decimals)
whole = lambda c: num(c).astype("Int64")
txt = lambda c, n: df[c].fillna("").str[:n]

# Columns use the API names of the Pet_Food_Product__c fields, as the Bulk API upsert requires.
# Barcode__c (external ID, unique) is the upsert key: re-importing updates records instead of duplicating them.
out = pd.DataFrame({
    "Name": df["code"],
    "Barcode__c": df["code"],
    "Product_Name__c": txt("product_name", 255),
    "Brand__c": txt("brands", 255),
    "Suggested_Brand__c": txt("suggested_brand", 255),
    "Categories__c": txt("categories", 1000),
    "Ingredients__c": txt("ingredients_text", 5000),
    "Quantity__c": txt("quantity", 255),
    "Weight_g__c": whole("product_quantity"),
    "Suggested_Weight_g__c": whole("suggested_quantity"),
    "Countries__c": txt("countries", 255),
    "Last_Modified__c": pd.to_datetime(df["last_modified_datetime"], errors="coerce", utc=True).dt.strftime("%Y-%m-%d"),
    "Protein_Pct__c": num("proteins_100g", 1),
    "Fat_Pct__c": num("fat_100g", 1),
    "Completeness_Score__c": whole("completeness_score"),
    "Issue_Count__c": whole("issue_count"),
    "DQ_Issues__c": txt("issues", 1000),
}).dropna(subset=["Barcode__c"])

# Export only products with barcodes and report the number of rows prepared.
out.to_csv(DATA / "salesforce_import.csv", index=False)
print(f"Rows ready for Salesforce: {len(out)}")