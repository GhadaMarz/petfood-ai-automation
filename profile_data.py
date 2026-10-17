from pathlib import Path
import pandas as pd

catalogue_path = (
    Path(__file__).resolve().parent / "data" / "en.openpetfoodfacts.org.products.csv"
)
catalogue = pd.read_csv(catalogue_path, sep="\t", low_memory=False)

print(f"Number of rows: {len(catalogue)}")
print("\nMissing values per column:")
print(catalogue.isna().sum().to_string())
print(f"\nNumber of duplicate barcodes: {catalogue['code'].duplicated().sum()}")

for label, column in (
    ("net_weight_g", "product_quantity"),
    ("protein_pct", "proteins_100g"),
):
    values = pd.to_numeric(catalogue[column], errors="coerce")
    print(f"\n{label} min: {values.min()}")
    print(f"{label} max: {values.max()}")


    rc = catalogue[catalogue["brands"].str.contains("royal canin", case=False, na=False)]
cols = ["code", "product_name", "brands", "categories", "ingredients_text",
        "quantity", "product_quantity", "countries", "last_modified_datetime"]
rc[cols].to_csv(Path(__file__).resolve().parent / "data" / "royal_canin_products.csv", index=False)
print(f"\nRoyal Canin products saved: {len(rc)}")