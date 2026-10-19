import { LightningElement, api } from 'lwc';
import { FlowAttributeChangeEvent } from 'lightning/flowSupport';

const COLUMNS = [
    { label: 'Barcode', fieldName: 'Name' },
    { label: 'Product Name', fieldName: 'Product_Name__c', wrapText: true },
    { label: 'Brand', fieldName: 'Brand__c' },
    { label: 'Suggested Brand', fieldName: 'Suggested_Brand__c' },
    { label: 'Weight (g)', fieldName: 'Weight_g__c', type: 'number' },
    { label: 'Suggested Weight (g)', fieldName: 'Suggested_Weight_g__c', type: 'number' },
    { label: 'Countries', fieldName: 'Countries__c', wrapText: true },
    { label: 'Suggested Countries', fieldName: 'Suggested_Countries__c', wrapText: true }
];

/**
 * Screen flow table of products with pending suggestions. Every row starts checked; the data steward unchecks the
 * rows to leave unchanged. Unlike the standard flow Data Table, it has no fixed height. The checked rows are kept
 * across searches and returned to the flow in selectedRecords.
 */
export default class SuggestionReviewTable extends LightningElement {
    @api records = [];
    @api selectedRecords = [];
    columns = COLUMNS;
    searchTerm = '';
    selectedIds = new Set();

    connectedCallback() {
        this.selectedIds = new Set((this.records || []).map((record) => record.Id));
        this.publishSelection();
    }

    get visibleRows() {
        const term = this.searchTerm.toLowerCase();
        if (!term) {
            return this.records || [];
        }
        return (this.records || []).filter((record) =>
            COLUMNS.some((column) => String(record[column.fieldName] ?? '').toLowerCase().includes(term)));
    }

    get visibleSelectedIds() {
        return this.visibleRows.filter((record) => this.selectedIds.has(record.Id)).map((record) => record.Id);
    }

    get summary() {
        return `${this.selectedIds.size} of ${(this.records || []).length} products checked`;
    }

    handleSearch(event) {
        this.searchTerm = event.target.value || '';
    }

    handleRowSelection(event) {
        // The table only reports the visible rows: rows hidden by the search keep their state.
        const checked = new Set(event.detail.selectedRows.map((row) => row.Id));
        const selectedIds = new Set(this.selectedIds);
        this.visibleRows.forEach((record) => (checked.has(record.Id) ? selectedIds.add(record.Id) : selectedIds.delete(record.Id)));
        this.selectedIds = selectedIds;
        this.publishSelection();
    }

    publishSelection() {
        this.selectedRecords = (this.records || []).filter((record) => this.selectedIds.has(record.Id));
        this.dispatchEvent(new FlowAttributeChangeEvent('selectedRecords', this.selectedRecords));
    }
}
