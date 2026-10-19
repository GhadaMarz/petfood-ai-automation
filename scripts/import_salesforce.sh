#!/usr/bin/env bash
# Rebuild data/salesforce_import.csv and upsert it into Pet_Food_Product__c.
# Records are matched on Barcode__c (external ID, unique): running this again updates them instead of duplicating.
# Records already reviewed in Salesforce (Corrected or Validated) keep the brand and weight the data steward decided
# on; their countries are standardized from the Salesforce value (left unchanged on Validated records).
# Usage: scripts/import_salesforce.sh [org alias, default petfood-dev]
set -euo pipefail

ORG="${1:-petfood-dev}"
cd "$(dirname "$0")/.."

sf data query --target-org "$ORG" --result-format csv --output-file data/reviewed_barcodes.csv \
    --query "SELECT Barcode__c, Review_Status__c, Countries__c FROM Pet_Food_Product__c WHERE Review_Status__c IN ('Corrected', 'Validated')"
python3 src/prepare_import.py
sf data upsert bulk --sobject Pet_Food_Product__c --file data/salesforce_import.csv \
    --external-id Barcode__c --target-org "$ORG" --wait 10
sf data query --query "SELECT COUNT() FROM Pet_Food_Product__c" --target-org "$ORG"
