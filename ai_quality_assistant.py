"""Use the Claude API to suggest brand corrections and to write a readable data-quality report.

The API key is read from the ANTHROPIC_API_KEY environment variable, never from the code:
    export ANTHROPIC_API_KEY=...        (macOS / Linux)
    python ai_quality_assistant.py
Run with --dry-run to see what would be sent to Claude without calling the API.
"""

import argparse
import json
import os
import sys
from pathlib import Path

import anthropic
import pandas as pd

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"
REPORTS = ROOT / "reports"

MODEL = "claude-opus-5-5"
# If a safety classifier declines a request, the API retries it on a recommended fallback model.
FALLBACK_BETA = "server-side-fallback-2026-07-01"

BRAND_SYSTEM = """You are a master data steward for Royal Canin, a pet food brand owned by Mars.
You review brand values found in a public, crowd-sourced product catalogue (Open Pet Food Facts).
The only official brand value is exactly "Royal Canin".

For each brand spelling, decide:
- "correct_to_royal_canin": the value is Royal Canin written differently (case, symbols, typo) or a Royal Canin
  range or product line typed into the brand field (for example "Royal Canin Veterinary"). Suggest "Royal Canin".
- "keep_other_brand": the value is another manufacturer's brand. Suggest that brand's usual spelling.
- "needs_review": the evidence is not enough to decide. Suggest the most likely value and explain the doubt.

Barcodes starting with 3182550 (France), 0030111 (North America), 7896181 or 7908248 (Brazil) are strong evidence
of a Royal Canin product. Base each decision only on the evidence given; do not invent facts about a brand."""

BRAND_SCHEMA = {
    "type": "object",
    "properties": {
        "suggestions": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "brand": {"type": "string"},
                    "suggested_brand": {"type": "string"},
                    "decision": {"type": "string", "enum": ["correct_to_royal_canin", "keep_other_brand", "needs_review"]},
                    "confidence": {"type": "string", "enum": ["high", "medium", "low"]},
                    "reason": {"type": "string"},
                },
                "required": ["brand", "suggested_brand", "decision", "confidence", "reason"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["suggestions"],
    "additionalProperties": False,
}

REPORT_SYSTEM = """You write data-quality reports for a product master data team at Royal Canin.
Your readers are business people, not developers: explain what the numbers mean for the catalogue,
which defects matter most and why, and what to fix first. Use only the figures provided; never invent numbers.
Write in Markdown with short sections and tables where they help."""


def load_report():
    return pd.read_csv(DATA / "dq_report.csv", dtype={"code": str}, sep=";", decimal=",", encoding="utf-8-sig")


def brand_conflicts(df):
    """One entry per brand spelling that is filled in but not exactly "Royal Canin", with evidence for the decision."""
    brands = df["brands"].str.strip()
    conflicts = df[brands.notna() & (brands != "Royal Canin")].assign(brand=brands)
    entries = []
    for brand, group in conflicts.groupby("brand", sort=True):
        entries.append({
            "brand": brand,
            "products": len(group),
            "example_names": group["product_name"].dropna().astype(str).head(3).tolist(),
            "example_barcodes": group["code"].dropna().head(3).tolist(),
            "match_reasons": sorted(group["match_reason"].dropna().unique().tolist()),
        })
    return entries


def quality_stats(df):
    """Figures the report is written from, computed here so that Claude never has to count."""
    issues = df["issues"].fillna("").str.split(", ").explode()
    worst = df.sort_values("issue_count", ascending=False).head(5)
    return {
        "products_checked": len(df),
        "products_with_at_least_one_issue": int((df["issue_count"] > 0).sum()),
        "average_completeness_score_pct": round(float(df["completeness_score"].mean()), 1),
        "completeness_definition": "share of 5 key fields filled in: name, category, ingredients, quantity, country",
        "issues_by_rule": issues[issues != ""].value_counts().to_dict(),
        "products_by_selection_rule": df["match_reason"].str.split(":").str[0].value_counts().to_dict(),
        "brand_spellings": df["brands"].fillna("(empty)").str.strip().value_counts().head(10).to_dict(),
        "weights_suggested_from_product_name": int(df["suggested_quantity"].notna().sum()),
        "products_with_most_issues": worst[["code", "product_name", "issue_count", "issues"]]
            .fillna("").to_dict(orient="records"),
    }


def response_text(response):
    """Return the text of a response, or stop with a clear message if Claude declined or was cut off."""
    if response.stop_reason == "refusal":
        sys.exit("Claude declined the request (refusal). Nothing was written.")
    if response.stop_reason == "max_tokens":
        sys.exit("The response was cut off (max_tokens). Nothing was written.")
    return "".join(block.text for block in response.content if block.type == "text")


def suggest_brands(client, conflicts):
    response = client.beta.messages.create(
        model=MODEL,
        max_tokens=16000,
        betas=[FALLBACK_BETA],
        fallbacks="default",
        output_config={"effort": "medium", "format": {"type": "json_schema", "schema": BRAND_SCHEMA}},
        system=BRAND_SYSTEM,
        messages=[{"role": "user", "content":
            "Here are the brand spellings to review, as JSON:\n" + json.dumps(conflicts, ensure_ascii=False, indent=2)}],
    )
    suggestions = json.loads(response_text(response))["suggestions"]
    counts = {c["brand"]: c["products"] for c in conflicts}
    table = pd.DataFrame(suggestions)
    table.insert(1, "products", table["brand"].map(counts))
    return table


def write_report(client, stats, language):
    with client.beta.messages.stream(
        model=MODEL,
        max_tokens=32000,
        betas=[FALLBACK_BETA],
        fallbacks="default",
        output_config={"effort": "medium"},
        system=REPORT_SYSTEM,
        messages=[{"role": "user", "content":
            f"Write the data-quality report in {language} from these figures (JSON):\n"
            + json.dumps(stats, ensure_ascii=False, indent=2)}],
    ) as stream:
        response = stream.get_final_message()
    return response_text(response)


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--dry-run", action="store_true", help="show the data sent to Claude without calling the API")
    parser.add_argument("--language", default="French", help="language of the quality report (default: French)")
    args = parser.parse_args()

    df = load_report()
    conflicts = brand_conflicts(df)
    stats = quality_stats(df)

    if args.dry_run:
        print(f"Brand spellings to review: {len(conflicts)}")
        print(json.dumps(conflicts[:3], ensure_ascii=False, indent=2))
        print("\nFigures for the quality report:")
        print(json.dumps(stats, ensure_ascii=False, indent=2))
        return

    if not os.environ.get("ANTHROPIC_API_KEY"):
        sys.exit("Set the ANTHROPIC_API_KEY environment variable first (never write the key in the code).")
    client = anthropic.Anthropic()

    suggestions = suggest_brands(client, conflicts)
    suggestions.to_csv(DATA / "brand_suggestions.csv", index=False, sep=";", encoding="utf-8-sig")  # French Excel format
    print(f"Brand suggestions saved: data/brand_suggestions.csv ({len(suggestions)} spellings)")
    print(suggestions["decision"].value_counts().to_string())

    REPORTS.mkdir(exist_ok=True)
    (REPORTS / "quality_report.md").write_text(write_report(client, stats, args.language), encoding="utf-8")
    print("Quality report saved: reports/quality_report.md")


if __name__ == "__main__":
    main()
