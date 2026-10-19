from types import SimpleNamespace

import pandas as pd
import pytest

from ai_quality_assistant import brand_conflicts, quality_stats, response_text


def report(*rows):
    defaults = {"code": "3182550702379", "product_name": "Persian", "brands": "Royal Canin",
                "match_reason": "brands:contains:royal", "issues": "", "issue_count": 0,
                "completeness_score": 100.0, "suggested_quantity": pd.NA}
    return pd.DataFrame([{**defaults, **row} for row in rows])


def test_brand_conflicts_group_spellings_and_skip_standard_and_empty_brands():
    df = report(
        {},
        {"brands": None},
        {"brands": "royal canin", "product_name": "Mini Adult"},
        {"brands": "royal canin ", "product_name": "Maxi Adult"},
        {"brands": "Terra Canis", "match_reason": "brands:typo:canis"},
    )
    conflicts = {c["brand"]: c for c in brand_conflicts(df)}
    assert set(conflicts) == {"royal canin", "Terra Canis"}
    assert conflicts["royal canin"]["products"] == 2
    assert conflicts["royal canin"]["example_names"] == ["Mini Adult", "Maxi Adult"]
    assert conflicts["Terra Canis"]["match_reasons"] == ["brands:typo:canis"]


def test_quality_stats_count_issues_and_selection_rules():
    df = report(
        {},
        {"issues": "missing_category, missing_brand", "issue_count": 2, "completeness_score": 80.0,
         "brands": None, "match_reason": "product_name:contains:royal"},
        {"issues": "missing_category", "issue_count": 1, "completeness_score": 60.0, "suggested_quantity": 2000},
    )
    stats = quality_stats(df)
    assert stats["products_checked"] == 3
    assert stats["products_with_at_least_one_issue"] == 2
    assert stats["average_completeness_score_pct"] == 80.0
    assert stats["issues_by_rule"] == {"missing_category": 2, "missing_brand": 1}
    assert stats["products_by_selection_rule"] == {"brands": 2, "product_name": 1}
    assert stats["weights_suggested_from_product_name"] == 1


def fake_response(stop_reason, *texts):
    blocks = [SimpleNamespace(type="thinking", thinking="")] + [SimpleNamespace(type="text", text=t) for t in texts]
    return SimpleNamespace(stop_reason=stop_reason, content=blocks)


def test_response_text_joins_text_blocks():
    assert response_text(fake_response("end_turn", "# Report", "\nBody")) == "# Report\nBody"


@pytest.mark.parametrize("stop_reason", ["refusal", "max_tokens"])
def test_response_text_stops_on_refusal_or_truncation(stop_reason):
    with pytest.raises(SystemExit):
        response_text(fake_response(stop_reason, "partial"))


def test_brand_conflicts_skip_variants_already_standardized():
    df = report({"brands": "royal canin", "standardized_brand": "Royal Canin"},
                {"brands": "Royal", "standardized_brand": "Royal"})
    assert [c["brand"] for c in brand_conflicts(df)] == ["Royal"]
