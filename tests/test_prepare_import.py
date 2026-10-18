import pandas as pd

from prepare_import import build_import, protect_reviewed


def report(*rows):
    defaults = {"code": "3182550702379", "product_name": "Persian", "brands": "royal canin",
                "suggested_brand": "Royal Canin", "categories": "Dry cat food", "ingredients_text": "Rice",
                "quantity": "4 kg", "product_quantity": "4000,0", "suggested_quantity": "", "countries": "France",
                "last_modified_datetime": "2026-01-15T10:00:00Z", "proteins_100g": "30,25", "fat_100g": "",
                "completeness_score": "100,0", "issue_count": "1", "issues": "non_standard_brand"}
    return pd.DataFrame([{**defaults, **row} for row in rows], dtype=str)


def test_import_uses_api_names_and_salesforce_formats():
    out = build_import(report({}))
    row = out.iloc[0]
    assert row["Name"] == row["Barcode__c"] == "3182550702379"
    assert row["Weight_g__c"] == 4000
    assert row["Protein_Pct__c"] == 30.2
    assert row["Last_Modified__c"] == "2026-01-15"


def test_products_without_barcode_are_dropped():
    assert len(build_import(report({}, {"code": None}))) == 1


def test_reviewed_records_keep_their_brand_and_weight():
    out = protect_reviewed(build_import(report({"code": "3182550000001"}, {"code": "3182550000002"})),
                           ["3182550000002"])
    reviewed, to_review = out.set_index("Barcode__c").loc["3182550000002"], out.set_index("Barcode__c").loc["3182550000001"]
    assert reviewed[["Brand__c", "Suggested_Brand__c", "Weight_g__c", "Suggested_Weight_g__c"]].isna().all()
    assert reviewed["Issue_Count__c"] == 1
    assert to_review["Brand__c"] == "royal canin"
    assert to_review["Suggested_Brand__c"] == "Royal Canin"
    assert to_review["Weight_g__c"] == 4000
