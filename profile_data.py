from pathlib import Path
import pandas as pd

catalogue_path = (Path(__file__).resolve().parent / "data" / "en.openpetfoodfacts.org.products.csv")

# Load the tab-separated catalogue and keep mixed-type columns intact.
catalogue = pd.read_csv(catalogue_path, sep="\t", low_memory=False)

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

    # Select Royal Canin products and save the fields needed for further analysis.
    rc = catalogue[catalogue["brands"].str.contains("royal canin", case=False, na=False)]
    cols = ["code", "product_name", "brands", "categories", "ingredients_text",
        "quantity", "product_quantity", "countries", "last_modified_datetime",
        "proteins_100g", "fat_100g", "completeness", "data_quality_errors_tags"]
    rc[cols].to_csv(Path(__file__).resolve().parent / "data" / "royal_canin_products.csv", index=False)
    print(f"\nRoyal Canin products saved: {len(rc)}")