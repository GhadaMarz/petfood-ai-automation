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
| `data/dq_report.csv` | `dq_check.py` | Same products + `issues`, `issue_count`, `completeness_score`, `suggested_quantity`, `suggested_brand` |
| `data/salesforce_import.csv` | `prepare_import.py` | Renamed fields, truncated texts, `YYYY-MM-DD` dates |
| `data/salesforce_import_wizard.csv` | `prepare_import.py` | Same rows with field labels as headers, for the Data Import Wizard |

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
"club special performance" and "pure origine". A single word is not enough either: a product must name both
"royal" and "canin" (in its brand or product name), carry a Royal Canin barcode prefix, or be one of 4 products
validated by hand. This removes competitor products such as Hill's "Canine" ranges or Italian "per cani" (for dogs)
names. Every kept product records why in `match_reason`
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
| `brand_barcode_conflict` | Royal Canin barcode prefix but another manufacturer's brand (e.g. Brekkies) |

The **completeness score** is the share of 5 key fields filled in: name, category, ingredients, quantity, country.

When the quantity is missing or implausible, `suggested_quantity` proposes a weight in grams read from the product
name: "PERSIAN 4KG" → 4000, "1,5kg" → 1500, "15 KG+3KG" (bonus bag) → 18000, "12X85G" (multipack) → 1020.

`suggested_brand` proposes "Royal Canin" only in safe cases: the brand differs only by case or spaces
("ROYAL CANIN"), or it is empty or generic ("Dog Food", "Cat Food") on a `3182550` or `0030111` barcode. Ambiguous
brands and other manufacturers get no suggestion and stay in manual review.

### 3. Salesforce file (`prepare_import.py`)

Selects the fields of the `Pet_Food_Product__c` object, names the columns with their API names (as the Bulk API
requires), applies field-length limits, rounds numbers to each field's decimals, formats dates and drops products
without a barcode.

`scripts/import_salesforce.sh` rebuilds this file and **upserts** it into the org on `Barcode__c`, an external ID
marked unique: running the import again updates existing records instead of creating duplicates.

Before each import, the script exports the barcodes of records already reviewed in Salesforce ("Corrected" or
"Validated"). For those records, `Brand__c` and `Suggested_Brand__c` are left empty in the file, and an upsert ignores
empty cells: a brand accepted by a data steward is never reverted by a later import, while every other field is still
refreshed. This protection needs the script; the Data Import Wizard cannot query Salesforce before an import.

```bash
scripts/import_salesforce.sh            # default org alias: petfood-dev
```

In VS Code, the same import runs from **Terminal › Run Task › Import Salesforce**.

To import through the Salesforce Data Import Wizard instead, use `data/salesforce_import_wizard.csv`: same rows, with
field labels as headers ("Product Name"...), read from the metadata in `force-app/`, so the wizard maps every column
by itself. Choose "Add new and update existing records", match by "Barcode (External ID)" and UTF-8 encoding.

The object, its fields, tab, page layout and the "Pet Food Data Steward" permission set are Salesforce DX metadata in
`force-app/`.

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

### 5. Brand suggestion review in Salesforce

Suggestions are never applied to the data automatically. On each Pet Food Product record, an **Accept Brand
Suggestion** button starts a screen flow that:

1. reads the record and stops without any change if `Suggested_Brand__c` is empty;
2. shows the current brand and the suggested brand, and asks the data steward to confirm;
3. copies the suggestion into `Brand__c`, sets `Review_Status__c` to "Corrected" and clears `Suggested_Brand__c`.

The flow and the button were built in the Salesforce org (Flow Builder) and are not yet stored in `force-app/`.

## Results (October 2026)

| Indicator | Value |
|---|---|
| Products in the catalogue | 15,136 |
| Found by a plain "royal canin" brand search | 226 |
| Royal Canin perimeter | **515** |
| Products with at least one defect | 500 (97 %) |
| Average completeness score | 61 % |
| Weights suggested from the product name | 58 of 209 products with a missing or implausible quantity |
| Brands suggested ("Royal Canin") | 250 |

| Rule | Products |
|---|---|
| `missing_ingredients` | 429 |
| `non_standard_brand` | 418 |
| `missing_category` | 342 |
| `missing_brand` | 282 |
| `missing_quantity` | 168 |
| `stale_record` | 143 |
| `missing_name` | 58 |
| `implausible_weight` | 41 |
| `invalid_barcode` | 6 |
| `implausible_protein`, `implausible_fat`, `duplicate_barcode`, `brand_barcode_conflict` | 0 |

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
time), the completeness score, the weight extraction from product names and the brand suggestions.

```bash
python -m pytest
```

The tests also run on GitHub Actions at every push (`.github/workflows/tests.yml`).

## Limits

- Open Pet Food Facts is collaborative: records are entered by contributors, not by Royal Canin.
- The GS1 prefixes were inferred from the data and still need confirming in the GS1 registry (GEPIR).
