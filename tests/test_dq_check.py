import pandas as pd
import pytest

from dq_check import (check, country_invalid, evaluate_rules, extract_weight_g, standardize_brand,
                      standardize_countries, suggest_brand)

TODAY = pd.Timestamp("2026-10-17", tz="UTC")

# A complete, valid product: every rule should pass on it.
CLEAN = {
    "code": "3182550702379",
    "product_name": "Persian Adult",
    "brands": "Royal Canin",
    "categories": "Dry cat food",
    "ingredients_text": "Dehydrated poultry protein, rice",
    "quantity": "4 kg",
    "product_quantity": 4000.0,
    "countries": "France",
    "last_modified_datetime": "2026-01-15T10:00:00Z",
    "proteins_100g": 30.0,
    "fat_100g": 15.0,
}


def products(*overrides):
    """Build a DataFrame with one clean product per override dict, each with its own barcode."""
    rows = []
    for i, override in enumerate(overrides):
        row = {**CLEAN, "code": f"318255070{i:04d}", **override}
        rows.append(row)
    return pd.DataFrame(rows)


def failed_rules(override):
    issues = evaluate_rules(products(override), TODAY)
    return set(issues.columns[issues.iloc[0].values])


def test_clean_product_has_no_issue():
    df, _ = check(products({}), TODAY)
    assert df.loc[0, "issues"] == ""
    assert df.loc[0, "issue_count"] == 0
    assert df.loc[0, "completeness_score"] == 100


@pytest.mark.parametrize("override, rule", [
    ({"product_name": None}, "missing_name"),
    ({"categories": None}, "missing_category"),
    ({"ingredients_text": None}, "missing_ingredients"),
    ({"quantity": None, "product_quantity": None}, "missing_quantity"),
    ({"product_quantity": 0.0}, "implausible_weight"),
    ({"product_quantity": 24200.0}, "implausible_weight"),
    ({"proteins_100g": 75.0}, "implausible_protein"),
    ({"fat_100g": -1.0}, "implausible_fat"),
    ({"code": "5680"}, "invalid_barcode"),
    ({"code": "31825507023790"}, None),
    ({"brands": "Royal Canin Veterinary"}, "brand_invalid_value"),
    ({"brands": "ROYAL CANIN"}, None),
    ({"last_modified_datetime": "2022-01-01T00:00:00Z"}, "stale_record"),
])
def test_each_rule_flags_only_its_defect(override, rule):
    expected = {rule} if rule else set()
    assert failed_rules(override) == expected


def test_empty_brand_is_only_missing_not_invalid():
    assert failed_rules({"brands": None}) == {"missing_brand"}


@pytest.mark.parametrize("brand, standardized", [
    ("royal canin", "Royal Canin"),
    ("ROYAL CANIN", "Royal Canin"),
    ("  Royal   canin ", "Royal Canin"),
    ("Royal Canin", "Royal Canin"),
    ("Royal", "Royal"),
    ("Royal Canin Veterinary", "Royal Canin Veterinary"),
    ("Toyal Canin", "Toyal Canin"),
    ("ROYAL-CANIN", "ROYAL-CANIN"),
])
def test_only_case_and_space_variants_are_standardized(brand, standardized):
    assert standardize_brand(pd.Series([brand])).iloc[0] == standardized


def test_missing_brand_stays_missing():
    assert pd.isna(standardize_brand(pd.Series([None], dtype=object)).iloc[0])


@pytest.mark.parametrize("brand, code, conflict", [
    ("Brekkies", "3182550011600", True),
    ("Affinity, Brekkies", "0030111428271", True),
    ("Brekkies", "8410650151090", False),
    ("Dog Food", "3182550928663", False),
    ("Royal Canin Veterinary", "3182550702379", False),
    (None, "3182550702379", False),
])
def test_other_manufacturer_on_royal_canin_barcode_is_a_conflict(brand, code, conflict):
    assert ("brand_barcode_conflict" in failed_rules({"brands": brand, "code": code})) == conflict


@pytest.mark.parametrize("brand, code, suggestion", [
    ("royal canin", "3182550702379", ""),
    (None, "3182550702379", "Royal Canin"),
    (None, "0030111428271", "Royal Canin"),
    (None, "030111428271", "Royal Canin"),
    ("Dog Food", "3182550928663", "Royal Canin"),
    ("Cat Food", "0030111428271", "Royal Canin"),
    ("Royal Canin", "3182550702379", ""),
    (None, "9003579311479", ""),
    ("Dog Food", "8896111214908", ""),
    ("Royal Canin Veterinary", "3182550702379", ""),
    ("Toyal Canin", "3182550702379", ""),
    ("Brekkies", "3182550011600", ""),
])
def test_suggested_brand_only_for_safe_cases(brand, code, suggestion):
    assert suggest_brand(products({"brands": brand, "code": code})).iloc[0] == suggestion


def test_check_standardizes_variant_and_keeps_original_brand():
    df, _ = check(products({"brands": "ROYAL CANIN"}, {"brands": None}), TODAY)
    assert df.loc[0, "brands"] == "ROYAL CANIN"
    assert df.loc[0, "standardized_brand"] == "Royal Canin"
    assert df["brand_auto_corrected"].tolist() == [True, False]
    assert df["suggested_brand"].tolist() == ["", "Royal Canin"]


def test_text_quantity_alone_is_not_missing():
    assert "missing_quantity" not in failed_rules({"product_quantity": None})


def test_barcode_with_leading_zeros_is_valid():
    assert "invalid_barcode" not in failed_rules({"code": "00005680"})


def test_duplicate_barcodes_are_flagged_on_both_products():
    df = products({}, {})
    df["code"] = "3182550702379"
    issues = evaluate_rules(df, TODAY)
    assert issues["duplicate_barcode"].tolist() == [True, True]


def test_completeness_counts_the_five_key_fields():
    df, _ = check(products({"categories": None, "ingredients_text": None}), TODAY)
    assert df.loc[0, "completeness_score"] == 60


@pytest.mark.parametrize("name, grams", [
    ("ROYAL CANIN FBN PERSIAN 4KG", 4000),
    ("Royal canin renal special 1,5kg", 1500),
    ("Royal Canin Persian Adulto 7.5kg", 7500),
    ("RC CAT DRY FHN EXIGENT SAVOUR 400GR", 400),
    ("Babydog Milk 400G", 400),
    ("SHN Maxi Adult 15 KG+3KG", 18000),
    ("BHN Golden Retriever 12+2 KG", 14000),
    ("Sachets Urinary Care Pour Chat - 12X85G", 1020),
    ("Weight control 24.2 lb", 10977),
    ("Royal canin gatos +7 1,5 kg sterelised", 1500),
    ("Royal Canin Vdiet Dog - Anallergenic An18 - 8 KG", 8000),
    ("regular sterilised 37", None),
    ("Green pouch", None),
    (None, None),
])
def test_extract_weight_from_name(name, grams):
    assert extract_weight_g(name) == grams


def test_weight_is_suggested_only_when_quantity_is_missing_or_implausible():
    df, _ = check(products(
        {"product_name": "Persian 2KG"},
        {"product_name": "Persian 2KG", "quantity": None, "product_quantity": None},
        {"product_name": "Persian 2KG", "quantity": "2k", "product_quantity": 0.0},
    ), TODAY)
    assert df["suggested_quantity"].tolist() == [pd.NA, 2000, 2000]


@pytest.mark.parametrize("countries, standardized, suggested", [
    ("France", "France", ""),
    ("en:france", "France", ""),
    ("en:France", "France", ""),
    ("Francia", "France", ""),
    ("Россия", "Russia", ""),
    ("Indonésie", "Indonesia", ""),
    ("en:united-states", "United States", ""),
    ("Allemagne, Sweden", "Germany, Sweden", ""),
    ("France,Russie", "France, Russia", ""),
    ("en:fr", "en:fr", "France"),
    ("en:FR", "en:FR", "France"),
    ("Canada, USA", "Canada, USA", "Canada, United States"),
    ("France, gironde", "France, gironde", "France"),
    ("Atlantis", "Atlantis", ""),
])
def test_country_names_are_standardized_and_codes_only_suggested(countries, standardized, suggested):
    assert standardize_countries(countries) == (standardized, suggested)


def test_missing_countries_stay_missing():
    standardized, suggested = standardize_countries(None)
    assert standardized is None and suggested == ""


@pytest.mark.parametrize("countries, invalid", [
    ("Россия", False), ("France, Germany", False), ("en:fr", True), ("Atlantis", True), (None, False),
])
def test_country_invalid_value_flags_codes_and_unknown_values(countries, invalid):
    assert country_invalid(countries) is invalid
    assert ("country_invalid_value" in failed_rules({"countries": countries})) is invalid


def test_check_standardizes_countries_and_keeps_the_original():
    df, _ = check(products({"countries": "en:russia"}, {"countries": "en:it"}), TODAY)
    assert df["countries"].tolist() == ["en:russia", "en:it"]
    assert df["standardized_countries"].tolist() == ["Russia", "en:it"]
    assert df["suggested_countries"].tolist() == ["", "Italy"]
    assert df["countries_auto_corrected"].tolist() == [True, False]
