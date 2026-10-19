# Technical guide

This guide describes everything needed to understand, run and rebuild the project from scratch: tools and versions,
accounts, installation commands, the Python pipeline, the Salesforce configuration, the AI assistant, tests and CI,
and the problems met along the way with their fixes.

Functional choices (why each rule exists, which trade-offs were made) are kept in a separate functional dossier.

---

## 1. Architecture

```
                       ┌──────────────────────────── Python pipeline (src/) ────────────────────────────┐
Open Pet Food Facts ──►│ profile_data.py ──► dq_check.py ──► prepare_import.py ──► salesforce_import.csv │
  raw CSV export       │  perimeter         14 rules,         Salesforce format,                         │
  (15,136 products)    │  (515 products)    suggestions       reviewed records protected                 │
                       └──────────────────────────────────────────────┬─────────────────────────────────┘
                                                                      │ scripts/import_salesforce.sh
                                                                      ▼ (Bulk API upsert on Barcode__c)
 ai_quality_assistant.py ──► Claude API              Salesforce org "petfood-dev"
 (brand suggestions, report)                         Pet_Food_Product__c + Accept Suggestions flow

 tests/ (pytest, 98 tests) ──► GitHub Actions at every push
```

| Layer | Technology | Role |
|---|---|---|
| Data source | Open Pet Food Facts CSV export | Real, public pet food catalogue |
| Processing | Python 3, pandas | Perimeter, quality rules, suggestions, import file |
| Tests | pytest, GitHub Actions | Regression tests on every rule, run at every push |
| CRM | Salesforce Developer Edition, Salesforce DX, Salesforce CLI | Object, fields, permissions, review flow, data |
| Generative AI | Claude API (`anthropic` Python SDK) | Brand classification and report writing |
| Tooling | macOS, Homebrew, Git, GitHub, VS Code | Development environment and versioning |

---

## 2. Repository structure

```
petfood-ai-automation/
├── README.md                     Project overview, quick start, results
├── requirements.txt              Python dependencies (pinned versions)
├── pytest.ini                    Test configuration (code in src/, tests in tests/)
├── .gitignore                    Files never committed (raw data, virtual env, private documents…)
├── src/
│   ├── profile_data.py           Step 1: profile the raw catalogue, select the Royal Canin perimeter
│   ├── dq_check.py               Step 2: quality rules, completeness score, suggested weight and brand
│   ├── prepare_import.py         Step 3: Salesforce import files, protection of reviewed records
│   └── ai_quality_assistant.py   Optional: Claude API brand suggestions and quality report
├── tests/
│   ├── test_dq_check.py          Quality rules, weight extraction, brand and country standardization and suggestion (83 tests)
│   ├── test_prepare_import.py    Import format, cleared fields, protection of reviewed records (9 tests)
│   └── test_ai_quality_assistant.py  AI assistant inputs and response handling, no API call (6 tests)
├── data/
│   ├── en.openpetfoodfacts.org.products.csv   Raw export (downloaded, not versioned, ~38 MB)
│   ├── royal_canin_products.csv  Output of step 1
│   ├── dq_report.csv             Output of step 2
│   ├── salesforce_import.csv     Output of step 3, for the CLI upsert (API names as headers)
│   ├── salesforce_import_wizard.csv  Same rows, field labels as headers, for the Data Import Wizard
│   └── reviewed_barcodes.csv     Exported from Salesforce before each import (not versioned)
├── scripts/
│   └── import_salesforce.sh      Export reviewed records, rebuild the file, upsert, count
├── salesforce/                   Salesforce DX project
│   ├── sfdx-project.json         Project definition (package directory, API version 68.0)
│   ├── .forceignore              Files the CLI must not deploy
│   └── force-app/main/default/
│       ├── objects/Pet_Food_Product__c/   Object definition, 18 custom fields, list view button
│       ├── layouts/              Page layout (sections and Accept Suggestions button)
│       ├── tabs/                 "Pet Food Products" tab
│       ├── permissionsets/       "Pet Food Data Steward" permission set
│       ├── flows/                Accept_Suggestions (one record) and Bulk_Accept_Suggestions (list) screen flows
│       ├── lwc/suggestionReviewTable/  Full-height table used by Bulk_Accept_Suggestions
│       └── quickActions/         Button that launches Accept_Suggestions on a record
├── docs/
│   ├── TECHNICAL_GUIDE.md        This guide
│   └── images/                   Screenshots shown in the README
├── .github/workflows/tests.yml   CI: install dependencies and run pytest
├── .vscode/
│   ├── settings.json             pytest in the Testing panel, hidden technical folders
│   └── tasks.json                "Import Salesforce" task
└── Documentation/                Private notes (git-ignored, never pushed)
```

Generated folders that are not versioned and can be deleted at any time: `.venv/` (virtual environment),
`__pycache__/`, `.pytest_cache/`, `salesforce/.sf/`, `salesforce/.sfdx/`, `reports/`.

---

## 3. Tools and versions

Versions used to build the project (October 2026, Apple Silicon Mac).

| Tool | Version | Installed with | Used for |
|---|---|---|---|
| macOS | 26.4 (arm64) | – | Operating system |
| Homebrew | 7.0.9 | official install script | Package manager for macOS |
| Git | 2.56.0 | `brew install git` | Version control |
| Python | 3.15.0 | `brew install python` | Pipeline and tests |
| pandas | 3.0.6 | `pip` (requirements.txt) | Data processing |
| pytest | 9.1.1 | `pip` (requirements.txt) | Tests |
| anthropic | 1.15.0 | `pip` (requirements.txt) | Claude API SDK |
| Node.js | 26.12.0 | `brew install node` | Runtime of the Salesforce CLI |
| Salesforce CLI (`sf`) | 2.154.4 | `npm install -g @salesforce/cli` | Deploy metadata, load and query data |
| Salesforce API | 68.0 | – | API version of the org and of the metadata |
| Visual Studio Code | 1.142.0 | `brew install --cask visual-studio-code` | Editor |
| GitHub Actions runner | ubuntu-latest, Python 3.13 | `.github/workflows/tests.yml` | CI |

VS Code extensions: Python (`ms-python.python`), Pylance (`ms-python.vscode-pylance`), Python Debugger
(`ms-python.debugpy`), Claude Code (`anthropic.claude-code`). GitHub Copilot can be added for AI code completion.

---

## 4. Accounts

| Account | Where | Notes |
|---|---|---|
| GitHub | github.com | Public repository `GhadaMarz/petfood-ai-automation` |
| Salesforce Developer Edition | developer.salesforce.com/signup | Free org with Agentforce. Use a personal e-mail and keep the username. An org inactive for 45 days can be deleted |
| Trailhead | trailhead.salesforce.com | Learning modules and badges, same login as the org |
| Anthropic Console | console.anthropic.com | API key and a few dollars of credit for the AI assistant. Never share or commit the key |

---

## 5. Installation from scratch (macOS)

### 5.1 Command-line tools

```bash
chsh -s /bin/zsh                                   # use zsh as the default shell
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
echo 'eval "$(/opt/homebrew/bin/brew shellenv zsh)"' >> ~/.zprofile
eval "$(/opt/homebrew/bin/brew shellenv zsh)"

brew install git python node
brew install --cask visual-studio-code
npm install -g @salesforce/cli

git --version && python3 --version && node --version && sf --version   # check the installs
```

### 5.2 Git identity (once per machine)

```bash
git config --global user.name "Your Name"
git config --global user.email "your-github-email@example.com"
```

### 5.3 Project and Python environment

```bash
cd ~/Projets
git clone https://github.com/GhadaMarz/petfood-ai-automation.git
cd petfood-ai-automation

python3 -m venv .venv              # isolated environment for the project's libraries
source .venv/bin/activate          # the prompt now starts with (.venv)
pip install -r requirements.txt
```

In VS Code: **File › Open Folder** on `petfood-ai-automation`, then **Cmd+Shift+P › Python: Select Interpreter** and
choose the `.venv` interpreter.

### 5.4 Raw data

```bash
curl -o data/products.csv.gz https://static.openpetfoodfacts.org/data/en.openpetfoodfacts.org.products.csv.gz
gunzip -c data/products.csv.gz > data/en.openpetfoodfacts.org.products.csv
```

The export is tab-separated, has more than 200 columns and is too large for GitHub (`data/en.openpetfoodfacts*` is in
`.gitignore`). Barcodes must be read as text to keep their leading zeros.

### 5.5 Salesforce CLI connection

```bash
sf org login web --alias petfood-dev          # opens the browser to log in to the Developer Edition org
sf org list                                    # petfood-dev must show "Connected"
sf org display --target-org petfood-dev        # instance URL and API version
```

---

## 6. Python pipeline

Run the steps in order from the project root, with the virtual environment active.

```bash
python src/profile_data.py
python src/dq_check.py
python src/prepare_import.py
```

### 6.1 `src/profile_data.py` – profile and select the Royal Canin perimeter

- **Input:** `data/en.openpetfoodfacts.org.products.csv` (`sep="\t"`, `dtype={"code": str}`).
- **Profiling printed:** number of rows, percentage of missing values per column, duplicate barcodes, min/max of
  `product_quantity` and `proteins_100g`.
- **Selection logic:**
  1. Text is normalised: accents removed (NFKD), lower case, only letters and digits kept; words and adjacent word
     pairs are compared ("royal canin" → "royalcanin").
  2. A product matches when a word contains "royal" or "canin", or is within `MAX_TYPOS = 1` edit (Levenshtein
     distance) of "royal", "canin" or "royalcanin".
  3. The brand is used; the product name only when the brand is empty (no letter or digit).
  4. Barcodes starting with `RC_BARCODE_PREFIXES = ("3182550", "0030111", "7896181", "7908248")` are kept. 12-digit UPC
     codes are padded to 13 digits first.
  5. `EXCLUDED_BRANDS` (zooroyal, brekkies, affinity, clubspecialperformance, pureorigine) are removed, whatever rule
     matched them.
  6. A single word is not enough: the brand plus product name must contain both "royal" and "canin", or the barcode
     must have a Royal Canin prefix, or be one of `VALIDATED_BARCODES` (4 products validated by hand).
- **Output:** `data/royal_canin_products.csv`, 515 rows, 13 columns plus `match_reason`
  (`<field>:<rule>:<word>`, e.g. `brands:contains:royal`, `barcode:0030111`).

### 6.2 `src/dq_check.py` – quality rules and suggestions

- **Functions:** `evaluate_rules(df, today)` returns one boolean column per rule; `check(df, today)` adds the result
  columns; `standardize_brand(brands)` fixes the obvious brand variants; `standardize_countries(value)` returns the
  standardized countries and the countries suggestion; `extract_weight_g(name)` and
  `suggest_brand(df)` compute the suggestions. The script part runs only under
  `if __name__ == "__main__":`, so the functions can be imported by the tests.
- **Rules:** `missing_name`, `missing_category`, `missing_ingredients`, `missing_quantity` (text and numeric quantity
  both empty), `implausible_weight` (≤ 0 g or > 20,000 g), `implausible_protein` (outside 0–60 %), `implausible_fat`
  (outside 0–40 %), `invalid_barcode` (not 8, 12, 13 or 14 digits), `duplicate_barcode`, `brand_invalid_value` (a
  brand that is filled in and still not "Royal Canin" after standardization, e.g. "Royal", "Toyal Canin"), `stale_record` (last modified more than 3 years ago), `missing_brand`,
  `brand_barcode_conflict` (barcode prefix 3182550 or 0030111 with another manufacturer's brand),
  `country_invalid_value` (a countries value holding anything else than a country name: a code, a region, an unknown
  value; 44 records).
- **Completeness score:** share of the 5 `KEY_FIELDS` filled in (name, categories, ingredients, quantity, countries),
  0–100.
- **`suggested_quantity`:** only when `missing_quantity` or `implausible_weight` is true. The `WEIGHT` regular
  expression reads kg / g / gr / lb / lbs / oz, decimal commas, bonus bags (`15 KG+3KG`, `12+2 KG`, added up) and
  multipacks (`12X85G`).
- **Automatic brand standardization:** a brand that only differs from "Royal Canin" by case or spaces ("royal canin",
  "ROYAL  CANIN") becomes "Royal Canin" in `standardized_brand`; `brand_auto_corrected` flags those records (124). The
  original value stays in `brands`. Brand rules are evaluated on the standardized brand, so a fixed variant is not a
  defect. Symbols, typos and other words ("ROYAL-CANIN", "Toyal Canin", "Royal") are not changed.
- **`suggested_brand`:** "Royal Canin" when the brand is empty or generic (`GENERIC_BRANDS = {"dog food", "cat food"}`)
  on a 3182550 or 0030111 barcode (126 records); empty otherwise.
- **Countries:** each comma-separated value is read with `country_key()` (lower case, "en:" prefix, accents and
  hyphens removed). A country name in English, French, Spanish, Portuguese or Russian (`COUNTRY_NAMES`: "en:france",
  "Francia", "Россия", "Allemagne", "España") is rewritten as its English name in `standardized_countries`, duplicates
  removed (227 records, flagged by `countries_auto_corrected`). Codes, abbreviations and regions (`COUNTRY_CODES`:
  "en:fr", "USA", "gironde") are only resolved in `suggested_countries`, the full value as it would be after
  acceptance (44 records). Unknown values are left unchanged. The original value stays in `countries`.
- **Output:** `data/dq_report.csv` = input columns + `issues`, `issue_count`, `completeness_score`,
  `suggested_quantity`, `suggested_brand`, `standardized_brand`, `brand_auto_corrected`, `standardized_countries`,
  `suggested_countries`, `countries_auto_corrected`.

### 6.3 `src/prepare_import.py` – Salesforce import files

- `build_import(df)` maps the report to the API names of `Pet_Food_Product__c`, truncates texts to the field lengths,
  rounds numbers to the field decimals (`Int64` for whole numbers), formats dates as `YYYY-MM-DD` and drops products
  without a barcode. `Name` and `Barcode__c` both receive the barcode; `Brand__c` and `Countries__c` receive the
  standardized values, `Suggested_Countries__c` the countries suggestion.
- `clear_empty_fields(out)` writes `#N/A` in every empty cell except the keys. In a Bulk API upsert an empty cell leaves
  the field unchanged and `#N/A` clears it, so Salesforce mirrors the pipeline: a suggestion made unnecessary or a
  defect that disappeared is removed instead of staying.
- `protect_reviewed(out, reviewed)` reads `data/reviewed_barcodes.csv` (barcode, review status and countries of the
  records reviewed in Salesforce) and keeps the data steward's decisions while the other fields are refreshed:
  - Corrected or Validated: `Brand__c`, `Suggested_Brand__c`, `Weight_g__c` and `Suggested_Weight_g__c` left empty,
    therefore unchanged;
  - Validated (suggestions rejected): `Countries__c` and `Suggested_Countries__c` left empty too;
  - Corrected: the countries are standardized from their Salesforce value instead of the source value. A country
    accepted in Salesforce is already a name and stays as it is; a country never reviewed (the record was corrected
    for its brand or weight) is still standardized or suggested.
  Without that file, the script prints a warning.
- `field_labels()` reads each field label from `salesforce/force-app/.../Pet_Food_Product__c` so that the wizard file
  always matches the object.
- **Outputs:** `data/salesforce_import.csv` (API names as headers) and `data/salesforce_import_wizard.csv` (labels as
  headers, no `#N/A`: the wizard cannot clear a field and would store the text).

### 6.4 File formats

| File | Separator | Decimal | Encoding | Why |
|---|---|---|---|---|
| `royal_canin_products.csv`, `dq_report.csv` | `;` | `,` | UTF-8 with BOM | Open directly in Excel with French settings |
| `salesforce_import*.csv` | `,` | `.` | UTF-8 without BOM | Format expected by the Salesforce import tools |

Reading a working file in pandas: `pd.read_csv(path, sep=";", decimal=",", encoding="utf-8-sig", dtype={"code": str})`.
Never re-save the Salesforce files from Excel: Excel would rewrite them with `;`.

---

## 7. Salesforce

### 7.1 Data model

Object `Pet_Food_Product__c` (label "Pet Food Product", plural "Pet Food Products"), sharing model Read/Write, reports
and search enabled. Standard `Name` field labelled "Barcode" (Text).

| API name | Label | Type |
|---|---|---|
| `Barcode__c` | Barcode (External ID) | Text(20), External ID, Unique (case-insensitive) |
| `Product_Name__c` | Product Name | Text(255) |
| `Brand__c` | Brand | Text(255) |
| `Suggested_Brand__c` | Suggested Brand | Text(255) |
| `Quantity__c` | Quantity | Text(255) |
| `Countries__c` | Countries | Text(255) |
| `Suggested_Countries__c` | Suggested Countries | Text(255) |
| `Categories__c` | Categories | Long Text Area(1000) |
| `DQ_Issues__c` | DQ Issues | Long Text Area(1000) |
| `Ingredients__c` | Ingredients | Long Text Area(5000) |
| `Weight_g__c` | Weight (g) | Number(10,0) |
| `Suggested_Weight_g__c` | Suggested Weight (g) | Number(10,0) |
| `Protein_Pct__c` | Protein (%) | Number(5,1) |
| `Fat_Pct__c` | Fat (%) | Number(5,1) |
| `Completeness_Score__c` | Completeness Score | Number(3,0) |
| `Issue_Count__c` | Issue Count | Number(3,0) |
| `Last_Modified__c` | Last Modified | Date |
| `Review_Status__c` | Review Status | Picklist (restricted): To Review (default), Validated, Corrected |

Other components in `salesforce/force-app/main/default/`:

- **Tab** `Pet_Food_Product__c` (icon `Custom18: Form`).
- **Page layout** "Pet Food Product Layout": sections Product, Data Quality, Details, System Information; the record
  actions start with the Accept Suggestions button.
- **Permission set** `Pet_Food_Data_Steward`: read, create and edit on the object (no delete), read and edit on every
  custom field, tab visible.
- **Screen flow** `Accept_Suggestions` (input variable `recordId`), launched by the record button:
  1. Get Records `Get_Product`, then Decision `Has_Any_Suggestion` (Suggested Brand, Weight or Countries not null);
     without any suggestion, screen `No_Suggestion` and no change.
  2. Screen `Review`: formulas `BrandLine`, `WeightLine` and `CountryLine` show "current → suggested" (or "no suggestion"), and a
     required radio button `Decision`: "Accept the suggestions" (`accept`, default) or "Reject them and keep the
     current values" (`reject`).
  3. Accept: Update Records `Apply_Brand` (Brand ← Suggested Brand, Suggested Brand cleared) if a brand is suggested,
     `Apply_Weight` (Weight ← Suggested Weight, Suggested Weight cleared) if a weight is suggested, `Apply_Countries`
     (Countries ← Suggested Countries, suggestion cleared) if countries are suggested, then `Mark_Corrected` (Review
     Status ← "Corrected").
  4. Reject: `Reject_Suggestions` clears the three suggestions and sets Review Status to "Validated".
  5. Screen `Done`.
- **Quick action** `Pet_Food_Product__c.Accept_Suggestions` (type Flow): the button on the record page.
- **Screen flow** `Bulk_Accept_Suggestions` (no input), launched by the list view button:
  1. Get Records `Get_Products`: every record whose Suggested Brand, Weight or Countries is not null, sorted by barcode;
     without any, screen `No_Suggestion`.
  2. Screen `Select_Changes`: the Lightning Web Component `suggestionReviewTable` (input `records`, output
     `selectedRecords`) shows barcode, product name, brand, suggested brand, weight, suggested weight, countries and
     suggested countries, with a search box and a "checked" counter. Every row starts checked; the data steward
     unchecks the rows to leave unchanged, then clicks Accept. Rows hidden by a search keep their state. The standard
     Data Table (`flowruntime:datatable`) was replaced because its height is fixed (internal scroll, about 7 rows
     visible) and no input attribute changes it; the component has no height limit and wraps long texts.
  3. Loop `Each_Product` over `selectedRecords`; Assignment `Accept_Row` sets Brand ← `NewBrand` (suggested brand, or
     the current one if none), Weight ← `NewWeight` and Countries ← `NewCountries` (same logic), clears the suggestions, sets Review Status to
     "Corrected", adds the row to `ProductsToUpdate` and counts it in `AcceptedCount`.
  4. Update Records `Update_Products` saves the collection in one operation (skipped if no row is selected);
     unchecked rows are not modified. Screen `Done` shows the number of products updated.
- **List view button** `Bulk_Accept_Suggestions` (web link, label "Accept Suggestions", type list button, URL
  `/flow/Bulk_Accept_Suggestions?retURL=/lightning/o/Pet_Food_Product__c/list`): added to every list view through
  `searchLayouts/listViewButtons` in the object file. The flow opens as a full page and returns to the list at the end:
  a web link of type flow (modal window) cannot be created through the Metadata API.
- **Former flow** `Accept_Brand_Suggestion` and its quick action (the first version, brand only, built in Flow
  Builder) were deleted from the org and the project on 19 October 2026.

The object, fields, tab, layout, permission set, both flows, the table component and the buttons are written as metadata files and deployed
with the CLI.

### 7.2 Deploying the metadata

All metadata commands run from the `salesforce/` folder, where `sfdx-project.json` lives.

```bash
cd salesforce

# 1. Check-only validation: compiles and checks everything, changes nothing in the org
sf project deploy validate --source-dir force-app --target-org petfood-dev

# 2. Real deployment
sf project deploy start --source-dir force-app --target-org petfood-dev

# 3. Give the current user access, then open the org on the tab
sf org assign permset --name Pet_Food_Data_Steward --target-org petfood-dev
sf org open --target-org petfood-dev --path lightning/o/Pet_Food_Product__c/list
```

Deploy a subset only, e.g. one field and the permission set:

```bash
sf project deploy start --target-org petfood-dev \
    --source-dir force-app/main/default/objects/Pet_Food_Product__c/fields/Barcode__c.field-meta.xml \
    --source-dir force-app/main/default/permissionsets
```

Bring changes made in the org (Flow Builder, Setup) back into the project before committing them:

```bash
sf project retrieve start --target-org petfood-dev \
    --metadata "Flow:Accept_Suggestions" \
    --metadata "Flow:Bulk_Accept_Suggestions" \
    --metadata "QuickAction:Pet_Food_Product__c.Accept_Suggestions" \
    --metadata "Layout:Pet_Food_Product__c-Pet Food Product Layout"
```

Useful pages in Setup: Object Manager › Pet Food Product; Permission Sets; Deployment Status
(`sf org open --path lightning/setup/DeployStatus/home`); View Setup Audit Trail; Bulk Data Load Jobs.

### 7.3 Loading data

**Recommended: the import script** (also available in VS Code as **Terminal › Run Task › Import Salesforce**):

```bash
scripts/import_salesforce.sh              # org alias defaults to petfood-dev
scripts/import_salesforce.sh other-alias
```

It runs four commands:

```bash
sf data query --target-org petfood-dev --result-format csv --output-file data/reviewed_barcodes.csv \
    --query "SELECT Barcode__c, Review_Status__c, Countries__c FROM Pet_Food_Product__c WHERE Review_Status__c IN ('Corrected', 'Validated')"
python3 src/prepare_import.py
sf data upsert bulk --sobject Pet_Food_Product__c --file data/salesforce_import.csv \
    --external-id Barcode__c --target-org petfood-dev --wait 10
sf data query --query "SELECT COUNT() FROM Pet_Food_Product__c" --target-org petfood-dev
```

Every empty value is sent as `#N/A`, so a field that became empty in the pipeline is cleared in Salesforce too;
reviewed records keep their brand and weight, and their countries as described in 6.3. Running it twice leaves the same number of records (515): the upsert
updates the records found by `Barcode__c` and
creates only the missing ones.

**Alternative: Data Import Wizard** (Setup › Data Import Wizard › Custom objects › Pet Food Products), with
`data/salesforce_import_wizard.csv`:

| Setting | Value |
|---|---|
| What do you want to do? | Add new and update existing records |
| Match by | Barcode (External ID) |
| Character code | Unicode (UTF-8) |
| Values separated by | Comma |
| Mapping | Automatic (headers are the field labels); `Barcode` → Name, `Barcode (External ID)` → Barcode__c |

The wizard cannot protect reviewed records nor clear a field that became empty: prefer the script.

### 7.4 Data commands

```bash
# Count records, check uniqueness, see review statuses
sf data query --target-org petfood-dev --query "SELECT COUNT(Id) n, COUNT_DISTINCT(Barcode__c) codes FROM Pet_Food_Product__c"
sf data query --target-org petfood-dev --query "SELECT Review_Status__c, COUNT(Id) n FROM Pet_Food_Product__c GROUP BY Review_Status__c"

# Delete every record (they go to the Recycle Bin for 15 days). Keep the ID file outside the repository.
sf data query --target-org petfood-dev --query "SELECT Id FROM Pet_Food_Product__c" \
    --result-format csv --output-file /tmp/pet_food_ids.csv
sf data delete bulk --sobject Pet_Food_Product__c --file /tmp/pet_food_ids.csv --target-org petfood-dev --wait 10

# Export every record (no 500-row limit, Long Text Areas included) to check the org against the import file
sf data export bulk --target-org petfood-dev --result-format csv --output-file /tmp/org_export.csv --wait 10 \
    --query "SELECT Barcode__c, Brand__c, Suggested_Brand__c, Review_Status__c, DQ_Issues__c FROM Pet_Food_Product__c"

# List the Bulk API jobs run on the org
sf api request rest "/services/data/v68.0/jobs/ingest" --target-org petfood-dev
```

---

## 8. AI assistant (`src/ai_quality_assistant.py`)

- **Model:** `claude-opus-5-5`, effort `medium`, through the official `anthropic` SDK.
- **Brand suggestions:** every brand spelling that is not exactly "Royal Canin" is sent with its product count,
  example names, barcodes and match reasons. The answer is constrained by a JSON schema (`output_config.format`) to
  `brand`, `suggested_brand`, `decision` (`correct_to_royal_canin` / `keep_other_brand` / `needs_review`),
  `confidence` and `reason`, and saved to `data/brand_suggestions.csv`. Nothing is written to the data.
- **Quality report:** figures are computed in Python (`quality_stats`), then Claude writes
  `reports/quality_report.md` for business readers (streaming request, `--language` option, French by default).
- **Safety:** requests opt into server-side refusal fallbacks (`fallbacks="default"`, beta
  `server-side-fallback-2026-07-01`); a refusal or a truncated answer stops the script without writing partial output.
- **API key:** read from the `ANTHROPIC_API_KEY` environment variable only.

```bash
export ANTHROPIC_API_KEY=sk-ant-...                     # never commit this value
python src/ai_quality_assistant.py --dry-run             # show the data that would be sent, no API call
python src/ai_quality_assistant.py                       # suggestions + report in French
python src/ai_quality_assistant.py --language English
```

---

## 9. Tests and continuous integration

```bash
python -m pytest              # 98 tests, one dot per passing test
python -m pytest -v           # one line per test with PASSED / FAILED
python -m pytest tests/test_dq_check.py -k weight     # a subset
```

- `pytest.ini` sets `pythonpath = src` and `testpaths = tests`.
- Tests build small sample products in memory (one clean product, then one defect at a time) and never read the data
  files or call an API.
- **VS Code:** Testing panel (flask icon) › Configure Python Tests › pytest › `tests` (already set in
  `.vscode/settings.json`).
- **GitHub Actions:** `.github/workflows/tests.yml` runs on every push and pull request: checkout, Python 3.13 with
  pip cache, `pip install -r requirements.txt`, `python -m pytest -v`. Results: repository › Actions tab › latest
  "Tests" run › job `pytest`.

---

## 10. Git workflow

```bash
git status                            # what changed
git diff --stat                       # how much changed per file
git add <files>                       # stage specific files (never Documentation/ or data/en.openpetfoodfacts*)
git commit -m "Clear message in English"
git push origin main                  # or VS Code › Source Control › Sync Changes
git log --oneline -10                 # recent history
```

Commits go directly to `main`, one commit per validated step. `.gitignore` excludes the Python/IDE defaults plus:
`data/en.openpetfoodfacts*` (raw export), `Documentation/` (private notes), `data/reviewed_barcodes.csv` (exported
from Salesforce at each import), `.sf/` and `.sfdx/` (Salesforce CLI state), `.DS_Store`.

---

## 11. Problems met and fixes

| Symptom | Cause | Fix |
|---|---|---|
| CSV opens in Excel as a single column | French Excel expects `;` and a decimal comma | Working files written with `sep=";"`, `decimal=","`, UTF-8 BOM |
| Accents garbled in Excel ("BÅ“uf") | UTF-8 without BOM read as Latin-1 | `encoding="utf-8-sig"` |
| 69 false `invalid_barcode` defects | pandas read barcodes as numbers and dropped leading zeros | `dtype={"code": str}` when reading |
| Filter with 2 typos returned 964 products | Short words ("real", "lapin", "casino") are 2 edits from "royal"/"canin" | `MAX_TYPOS = 1` and both words required |
| Quick deploy refused after a successful validation | Quick deploy needs a validation that ran Apex tests | Normal `sf project deploy start` of the same files |
| 1,029 records for 515 products | Two "Add new records" imports | `Barcode__c` external ID, unique, and upsert |
| Bulk upsert rejected label headers | Bulk API needs API names | `salesforce_import.csv` uses API names |
| Wizard asked for the mapping at each import | The wizard maps by label, not API name | `salesforce_import_wizard.csv` with label headers |
| Re-import would revert accepted brands | The file still contained the old brand and the suggestion | Reviewed records exported first, brand cells left empty |
| Countries of 171 Corrected records not standardized | Reviewed records had all steward fields protected, countries included, although only brand or weight had been reviewed | Corrected records: countries standardized from their Salesforce value; Validated records still fully protected |
| Old suggestions and defects stayed in Salesforce | A Bulk API upsert ignores empty cells | Empty cells sent as `#N/A`, which clears the field |
| Query on `DQ_Issues__c` refused | SOQL cannot filter on a Long Text Area | Export with `sf data export bulk` and filter in Python |
| `Barcode__c` missing from the wizard "Match by" list | Only Name and Salesforce ID offered in that list | Match on Name (holds the barcode) or map `Barcode__c` explicitly |
| Flow deletion fails: "insufficient access rights on cross-reference id" | The flow still has versions (active or obsolete) | Delete the quick action first, deactivate the flow, then delete each version: `sf data delete record -t -s Flow -i <version Id>` |
| "You can't create weblink of type flow" | A list button that opens a flow in a window cannot be deployed as metadata | URL list button to `/flow/<Flow_Name>?retURL=...` |
| "We can't find this input attribute: preSelectedRows" | The Data Table pre-selection input is named `selectedRows` | Set `selectedRows` to the collection to pre-check |
| Flow Data Table shows ~7 rows with its own scroll bar | The standard Data Table has a fixed height; no attribute (`tableHeight`, `maxHeight`…) exists | Custom LWC `suggestionReviewTable` without height limit |

---

## 12. Rebuild checklist

1. Create the accounts (section 4).
2. Install the tools (5.1), set the Git identity (5.2), clone and create the virtual environment (5.3).
3. Download the raw export (5.4).
4. Run the pipeline (6) and the tests (9): 515 products, 98 tests passing.
5. Log in to the org (5.5), validate then deploy `salesforce/force-app` (7.2), assign the permission set.
6. Load the data with `scripts/import_salesforce.sh` (7.3) and check the count: 515.
7. Open a record with a suggestion and test the Accept Suggestions button (accept and reject); on the list, test the
   Accept Suggestions list button (uncheck one row, accept the others).
8. Optional: set `ANTHROPIC_API_KEY` and run the AI assistant (8).
9. Commit and push (10); check the Actions tab is green.
