#!/usr/bin/env bash
# Rebuild data/salesforce_import.csv and upsert it into Pet_Food_Product__c.
# Records are matched on Barcode__c (external ID, unique): running this again updates them instead of duplicating.
# Usage: scripts/import_salesforce.sh [org alias, default petfood-dev]
set -euo pipefail

ORG="${1:-petfood-dev}"
cd "$(dirname "$0")/.."

python3 prepare_import.py
sf data upsert bulk --sobject Pet_Food_Product__c --file data/salesforce_import.csv \
    --external-id Barcode__c --target-org "$ORG" --wait 10
sf data query --query "SELECT COUNT() FROM Pet_Food_Product__c" --target-org "$ORG"
