import pandas as pd

from prepare_import import CLEAR, build_import, clear_empty_fields, protect_reviewed


def report(*rows):
    defaults = {"code": "3182550702379", "product_name": "Persian", "brands": "royal canin", "standardized_brand": "Royal Canin",
                "suggested_brand": "Royal Canin", "categories": "Dry cat food", "ingredients_text": "Rice",
                "quantity": "4 kg", "product_quantity": "4000,0", "suggested_quantity": "", "countries": "en:fr",
                "standardized_countries": "en:fr", "suggested_countries": "France",
                "last_modified_datetime": "2026-01-15T10:00:00Z", "proteins_100g": "30,25", "fat_100g": "",
                "completeness_score": "100,0", "issue_count": "1", "issues": "missing_category"}
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


def reviewed(*rows):
    return pd.DataFrame(rows, columns=["Barcode__c", "Review_Status__c", "Countries__c"])


def test_reviewed_records_keep_their_brand_and_weight():
    out = protect_reviewed(build_import(report({"code": "3182550000001"}, {"code": "3182550000002"})),
                           reviewed(("3182550000002", "Validated", "en:fr")))
    validated, to_review = out.set_index("Barcode__c").loc["3182550000002"], out.set_index("Barcode__c").loc["3182550000001"]
    assert validated[["Brand__c", "Suggested_Brand__c", "Weight_g__c", "Suggested_Weight_g__c", "Countries__c",
                     "Suggested_Countries__c"]].isna().all()
    assert validated["Issue_Count__c"] == 1
    assert to_review["Brand__c"] == "Royal Canin"
    assert to_review["Suggested_Brand__c"] == "Royal Canin"
    assert to_review["Weight_g__c"] == 4000


def test_import_sends_the_standardized_brand():
    assert build_import(report({})).iloc[0]["Brand__c"] == "Royal Canin"


def test_disappeared_suggestions_are_cleared_in_salesforce():
    out = clear_empty_fields(build_import(report({"suggested_brand": "", "suggested_quantity": "2000"})))
    assert out.iloc[0]["Suggested_Brand__c"] == CLEAR
    assert out.iloc[0]["Suggested_Weight_g__c"] == "2000"


def test_every_empty_field_is_cleared_except_the_keys():
    out = clear_empty_fields(build_import(report({"issues": "", "fat_100g": ""})))
    assert out.iloc[0][["DQ_Issues__c", "Fat_Pct__c"]].tolist() == [CLEAR, CLEAR]
    assert out.iloc[0]["Barcode__c"] == "3182550702379"


def test_reviewed_records_are_left_untouched_even_when_suggestions_disappear():
    out = protect_reviewed(clear_empty_fields(build_import(report({"suggested_brand": ""}))),
                           reviewed(("3182550702379", "Corrected", "France")))
    assert out.iloc[0][["Suggested_Brand__c", "Suggested_Weight_g__c"]].isna().all()


def test_import_sends_the_standardized_countries_and_the_suggestion():
    out = build_import(report({"countries": "Россия", "standardized_countries": "Russia", "suggested_countries": ""},
                              {"code": "3182550000002"}))
    assert out["Countries__c"].tolist() == ["Russia", "en:fr"]
    assert out["Suggested_Countries__c"].tolist() == ["", "France"]


def test_corrected_records_get_their_salesforce_countries_standardized():
    out = protect_reviewed(clear_empty_fields(build_import(report(*({"code": c} for c in "123")))),
                           reviewed(("1", "Corrected", "France"), ("2", "Corrected", "Россия, en:fr"),
                                    ("3", "Corrected", None)))
    assert out["Countries__c"].tolist() == ["France", "Russia, en:fr", CLEAR]
    assert out["Suggested_Countries__c"].tolist() == [CLEAR, "Russia, France", CLEAR]
    assert out[["Brand__c", "Weight_g__c"]].isna().all().all()
