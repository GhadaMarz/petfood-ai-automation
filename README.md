# petfood-ai-automation

AI-assisted data quality and test automation for a pet food product catalogue.

Real product master data is rarely clean. This project takes the public Open Pet Food Facts catalogue, isolates the
Royal Canin products, measures their data quality with explicit rules, suggests corrections where they can be derived
safely, and loads the results into a Salesforce org where a data steward reviews and accepts them.

```
Open Pet Food Facts ─► Python pipeline (perimeter, 14 quality rules, suggestions) ─► Salesforce Pet Food Product object
     15,136 products         src/ + tests/ (98 tests, GitHub Actions)                 upsert on Barcode__c, review flow
```

## Repository structure

| Folder / file | Content |
|---|---|
| `src/` | Python pipeline: `profile_data.py`, `dq_check.py`, `prepare_import.py`, `ai_quality_assistant.py` |
| `tests/` | pytest suite for the quality rules, the import file and the AI assistant |
| `data/` | Raw catalogue (not versioned) and the generated CSV files |
| `scripts/` | `import_salesforce.sh`: rebuild the import file and upsert it into Salesforce |
| `salesforce/` | Salesforce DX project: object, fields, tab, layout, permission set, flow and button (`force-app/`) |
| `docs/` | [Technical guide](docs/TECHNICAL_GUIDE.md): installation, versions, every command, how to rebuild from scratch |
| `.github/workflows/` | GitHub Actions workflow that runs the tests at every push |
| `requirements.txt`, `pytest.ini` | Python dependencies and test configuration |

## Quick start

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
curl -o data/products.csv.gz https://static.openpetfoodfacts.org/data/en.openpetfoodfacts.org.products.csv.gz
gunzip -c data/products.csv.gz > data/en.openpetfoodfacts.org.products.csv

python src/profile_data.py      # raw catalogue  -> data/royal_canin_products.csv
python src/dq_check.py          # quality rules  -> data/dq_report.csv
python src/prepare_import.py    # Salesforce     -> data/salesforce_import.csv
python -m pytest                # 98 tests
scripts/import_salesforce.sh    # upsert into the petfood-dev org (Salesforce CLI login required)
```

Full setup, Salesforce deployment and every command: [docs/TECHNICAL_GUIDE.md](docs/TECHNICAL_GUIDE.md).

## What the pipeline does

- **Finds the Royal Canin perimeter:** a plain brand search finds 226 products; the filter finds 515, using the brand
  (case, accents and symbols ignored, one typo allowed), the product name when the brand is empty, and Royal Canin
  GS1 barcode prefixes. Competitor brands and single-word matches ("canine", "per cani") are excluded. Every product
  records why it was kept (`match_reason`).
- **Checks 14 quality rules** (missing fields, implausible weights, invalid barcodes, invalid brands or countries,
  stale records…) and computes a completeness score on 5 key fields.
- **Fixes the obvious automatically:** a brand that only differs from "Royal Canin" by case or spaces ("royal canin",
  "ROYAL CANIN") is standardized before the import (124 products); a country name written in any language or case
  ("en:france", "Francia", "Россия", "Allemagne") becomes its English name (227 products). The original values are
  kept in the report.
- **Suggests the rest for review:** a weight read from the product name ("PERSIAN 4KG" → 4000 g) and "Royal Canin" for
  empty or generic brands on a Royal Canin barcode, a country for a code or an abbreviation ("en:fr" → France, "USA"
  → United States). Ambiguous brands ("Royal", "Toyal Canin") go to manual review.
- **Mirrors the pipeline in Salesforce without duplicates:** upsert on a unique external ID (`Barcode__c`); values that
  disappeared are cleared; brands and weights already decided by a data steward are never overwritten by an import.
- **Keeps a human in the loop:** an "Accept Suggestions" button shows the brand and weight suggestions of a record; the
  data steward accepts them ("Corrected") or rejects them ("Validated"). Countries suggestions are reviewed the same way. On the product list, a second button lists
  every pending suggestion, all pre-checked: the steward unchecks the ones to leave aside and accepts the rest at once.
- **Uses Claude for what needs language:** `ai_quality_assistant.py` classifies ambiguous brand spellings (JSON schema
  output) and writes a business-readable report from figures computed in Python.

## Results (October 2026)

| Indicator | Value |
|---|---|
| Products in the catalogue | 15,136 |
| Found by a plain "royal canin" brand search | 226 |
| Royal Canin perimeter | **515** |
| Products with at least one defect | 492 (96 %) |
| Average completeness score | 61 % |
| Weights suggested from the product name | 58 of 209 products with a missing or implausible quantity |
| Brands standardized automatically (case or spaces) | 124 |
| Brands suggested for steward review ("Royal Canin") | 126 |
| Countries standardized automatically (names in any language) | 227 |
| Countries suggested for steward review (codes, abbreviations) | 44 |

| Rule | Products |
|---|---|
| `missing_ingredients` | 429 |
| `missing_category` | 342 |
| `missing_brand` | 282 |
| `missing_quantity` | 168 |
| `stale_record` | 143 |
| `missing_name` | 58 |
| `country_invalid_value` | 44 |
| `implausible_weight` | 41 |
| `brand_invalid_value` | 12 |
| `invalid_barcode` | 6 |
| `implausible_protein`, `implausible_fat`, `duplicate_barcode`, `brand_barcode_conflict` | 0 |

`stale_record` depends on the day the script runs, so its count grows over time.

## Data source and limits

- [Open Pet Food Facts](https://world.openpetfoodfacts.org/), licensed under the Open Database License (ODbL). It is
  collaborative: records are entered by contributors, not by Royal Canin.
- The GS1 prefixes were inferred from the data and still need confirming in the GS1 registry (GEPIR).
