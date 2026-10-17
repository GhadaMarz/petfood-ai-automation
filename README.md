# petfood-ai-automation

AI-assisted data quality and test automation for a pet food product catalogue.

## Goal

Real product master data is rarely clean. This project takes the public Open Pet Food Facts catalogue, isolates the
Royal Canin products, measures their data quality with explicit rules, suggests corrections where they can be derived
safely, and prepares a clean file for a Salesforce import.

## Data

- **Source:** [Open Pet Food Facts](https://world.openpetfoodfacts.org/) full export, 15,136 products, licensed under
  the Open Database License (ODbL).
- **Raw file:** `data/en.openpetfoodfacts.org.products.csv` (tab-separated, 200+ columns). It is too large for GitHub
  and is excluded by `.gitignore`. Download and unzip it before running the scripts:

  ```bash
  curl -o data/products.csv.gz https://static.openpetfoodfacts.org/data/en.openpetfoodfacts.org.products.csv.gz
  gunzip -c data/products.csv.gz > data/en.openpetfoodfacts.org.products.csv
  ```

| File | Produced by | Content |
|---|---|---|
| `data/royal_canin_products.csv` | `profile_data.py` | Royal Canin perimeter, 13 columns + `match_reason` |
| `data/dq_report.csv` | `dq_check.py` | Same products + `issues`, `issue_count`, `completeness_score`, `suggested_quantity` |
| `data/salesforce_import.csv` | `prepare_import.py` | Renamed fields, truncated texts, `YYYY-MM-DD` dates |

The two working files use the French Excel format (`;` separator, decimal comma, UTF-8 with BOM) so they open
directly in Excel. The Salesforce file uses the standard CSV format (`,` separator, decimal point, UTF-8) expected by
the Salesforce import tools.

## Pipeline

```
raw catalogue ──> profile_data.py ──> royal_canin_products.csv ──> dq_check.py ──> dq_report.csv ──> prepare_import.py ──> salesforce_import.csv
```

### 1. Royal Canin perimeter (`profile_data.py`)

A plain brand search for "royal canin" finds only 226 products. The filter keeps a product when:

1. its **brand** contains "royal", "canin" or "royalcanin", ignoring case, accents and symbols, with **one typo
   allowed** (so "Toyal Canin", "ROYAL-CANIN" and "royal canın" are found);
2. or, **only when the brand is empty**, its **product name** matches the same rule;
3. or its **barcode starts with a Royal Canin GS1 prefix**: `3182550` (France), `0030111` (North America),
   `7896181` and `7908248` (Brazil). `9003579` (Austria) is left out on purpose: it is shared with other Mars brands
   such as Whiskas and Kitekat.

Brands caught by mistake are then excluded, whatever rule matched them: Zooroyal, Brekkies / Affinity,
"club special performance" and "pure origine". Every kept product records why in `match_reason`
(for example `brands:contains:royal`, `product_name:typo:cani` or `barcode:0030111`), so each inclusion can be
justified and doubtful cases reviewed.

### 2. Quality rules (`dq_check.py`)

| Rule | Defect detected |
|---|---|
| `missing_name` | Empty product name |
| `missing_category` | Empty category |
| `missing_ingredients` | Empty ingredient list |
| `missing_quantity` | Both text and numeric quantity empty |
| `implausible_weight` | Weight ≤ 0 g or > 20 kg |
| `implausible_protein` | Protein outside 0–60 % |
| `implausible_fat` | Fat outside 0–40 % |
| `invalid_barcode` | Barcode without 8, 12, 13 or 14 digits |
| `duplicate_barcode` | Same barcode on several products |
| `non_standard_brand` | Brand not written exactly "Royal Canin" |
| `stale_record` | Not updated for more than 3 years |
| `missing_brand` | Empty brand |

The **completeness score** is the share of 5 key fields filled in: name, category, ingredients, quantity, country.

When the quantity is missing or implausible, `suggested_quantity` proposes a weight in grams read from the product
name: "PERSIAN 4KG" → 4000, "1,5kg" → 1500, "15 KG+3KG" (bonus bag) → 18000, "12X85G" (multipack) → 1020.

### 3. Salesforce file (`prepare_import.py`)

Selects and renames the fields of the Salesforce template, applies field-length limits, converts numbers and dates,
and drops products without a barcode.

### 4. AI assistant (`ai_quality_assistant.py`)

Calls the Claude API (`claude-opus-5-5`) to:

- **suggest brand corrections** for every brand spelling that is not exactly "Royal Canin": correct it to
  "Royal Canin", keep it as another manufacturer's brand, or flag it for review, with a confidence level and a reason.
  The answer is constrained to a JSON schema and saved to `data/brand_suggestions.csv`. Nothing is changed in the data:
  the suggestions are for a data steward to approve.
- **write a readable quality report** (`reports/quality_report.md`) for business readers. All figures are computed in
  Python first, so the model explains the numbers but never counts them.

The API key is read from the `ANTHROPIC_API_KEY` environment variable and never written in the code. Requests opt into
server-side refusal fallbacks (`fallbacks: "default"`).

```bash
export ANTHROPIC_API_KEY=...                 # your key, from console.anthropic.com
python ai_quality_assistant.py --dry-run     # show what would be sent, without calling the API
python ai_quality_assistant.py               # brand suggestions + report in French
python ai_quality_assistant.py --language English
```

## Results (October 2026)

| Indicator | Value |
|---|---|
| Products in the catalogue | 15,136 |
| Found by a plain "royal canin" brand search | 226 |
| Royal Canin perimeter | **557** |
| Products with at least one defect | 542 (97 %) |
| Average completeness score | 60 % |
| Weights suggested from the product name | 58 of 239 products with a missing or implausible quantity |

| Rule | Products |
|---|---|
| `missing_ingredients` | 468 |
| `non_standard_brand` | 460 |
| `missing_category` | 377 |
| `missing_brand` | 315 |
| `missing_quantity` | 196 |
| `stale_record` | 161 |
| `missing_name` | 59 |
| `implausible_weight` | 43 |
| `invalid_barcode` | 6 |
| `implausible_protein`, `implausible_fat`, `duplicate_barcode` | 0 |

`stale_record` depends on the day the script runs, so its count grows over time.

## How to run

Requires Python 3.

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

python profile_data.py     # raw catalogue -> data/royal_canin_products.csv
python dq_check.py         # quality rules  -> data/dq_report.csv
python prepare_import.py   # Salesforce     -> data/salesforce_import.csv
python ai_quality_assistant.py  # Claude API -> data/brand_suggestions.csv, reports/quality_report.md
```

## Tests

`tests/test_dq_check.py` checks every quality rule on small sample products (one clean product, then one defect at a
time), the completeness score, and the weight extraction from product names.

```bash
python -m pytest
```

The tests also run on GitHub Actions at every push (`.github/workflows/tests.yml`).

## Limits

- Open Pet Food Facts is collaborative: records are entered by contributors, not by Royal Canin.
- The GS1 prefixes were inferred from the data and still need confirming in the GS1 registry (GEPIR).
- 39 products are kept only because of words like "canine", "cani" or "canis" and still need a decision.
