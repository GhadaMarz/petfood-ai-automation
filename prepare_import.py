"""Prepare a clean, consistently formatted product file for Salesforce import.
This script selects the catalogue fields Salesforce needs, applies field-length
limits, converts numeric and date values, and excludes products without barcodes.
"""

from pathlib import Path
import xml.etree.ElementTree as ET
import pandas as pd

DATA = Path(__file__).resolve().parent / "data"
# Barcodes of records a data steward has already reviewed in Salesforce, exported just before an import.
REVIEWED_BARCODES = DATA / "reviewed_barcodes.csv"
# Fields a data steward decides on in Salesforce: an import must never overwrite them on reviewed records.
STEWARD_FIELDS = ["Brand__c", "Suggested_Brand__c"]


def build_import(df):
    """Map the data-quality report to the Pet_Food_Product__c fields, one row per product with a barcode."""
    # Convert numeric fields safely (the report uses decimal commas), round them to the decimals of their Salesforce
    # field, and limit text fields to their import lengths.
    num = lambda c, decimals=0: pd.to_numeric(df[c].str.replace(",", ".", regex=False), errors="coerce").round(decimals)
    whole = lambda c: num(c).astype("Int64")
    txt = lambda c, n: df[c].fillna("").str[:n]

    # Columns use the API names of the Pet_Food_Product__c fields, as the Bulk API upsert requires.
    # Barcode__c (external ID, unique) is the upsert key: re-importing updates records instead of duplicating them.
    return pd.DataFrame({
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


def protect_reviewed(out, reviewed_barcodes):
    """Blank the steward fields of already reviewed records. An upsert ignores empty cells, so the brand a data
    steward accepted in Salesforce is kept, while every other field is still refreshed."""
    out = out.copy()
    out.loc[out["Barcode__c"].isin(set(reviewed_barcodes)), STEWARD_FIELDS] = ""
    return out


def field_labels():
    """API name -> label of every Pet_Food_Product__c field, read from the Salesforce DX metadata in force-app."""
    tag = "{http://soap.sforce.com/2006/04/metadata}"
    folder = Path(__file__).resolve().parent / "force-app/main/default/objects/Pet_Food_Product__c"
    obj = ET.parse(folder / "Pet_Food_Product__c.object-meta.xml").getroot()
    labels = {"Name": obj.find(f"{tag}nameField/{tag}label").text}
    for path in (folder / "fields").glob("*.field-meta.xml"):
        labels[path.name.removesuffix(".field-meta.xml")] = ET.parse(path).getroot().find(f"{tag}label").text
    return labels


if __name__ == "__main__":
    # Load the data-quality report created by the previous processing step.
    out = build_import(pd.read_csv(DATA / "dq_report.csv", dtype=str, sep=";", encoding="utf-8-sig"))

    if REVIEWED_BARCODES.exists():
        reviewed = pd.read_csv(REVIEWED_BARCODES, dtype=str)["Barcode__c"].dropna()
        out = protect_reviewed(out, reviewed)
        print(f"Reviewed records protected (brand fields left unchanged): {out['Barcode__c'].isin(set(reviewed)).sum()}")
    else:
        print("No reviewed_barcodes.csv: brand fields of reviewed records are NOT protected")

    # Export only products with barcodes and report the number of rows prepared.
    out.to_csv(DATA / "salesforce_import.csv", index=False)
    print(f"Rows ready for Salesforce: {len(out)}")

    # Same file with field labels as headers ("Product Name"...): the Data Import Wizard maps columns by label,
    # so it maps this file on its own instead of asking for the mapping at every import.
    out.rename(columns=field_labels()).to_csv(DATA / "salesforce_import_wizard.csv", index=False)
    print("Data Import Wizard file: data/salesforce_import_wizard.csv")
