/** @odoo-module **/
import { reactive } from "@odoo/owl";

export const INTERVALS = [
    ["day", "Daily"], ["week", "Weekly"], ["month", "Monthly"],
    ["quarter", "Quarterly"], ["year", "Yearly"],
];

export const GROUP_BYS = [
    ["variant", "Variant"], ["template", "Product Template"],
    ["category", "Category"], ["uom", "Unit of Measure"],
    ["src_location", "Source Location"],
    ["dst_location", "Destination Location"],
    ["warehouse", "Warehouse"], ["operation_type", "Operation Type"],
    ["rule", "Stock Rule"], ["company", "Company"], ["none", "No Grouping"],
];

export const STATES = [
    ["done", "Done"], ["assigned", "Partially Available"],
    ["waiting", "Waiting Availability"],
    ["confirmed", "Waiting Another Move"], ["draft", "New"],
    ["cancel", "Cancelled"],
];

export const FILTER_DEFS = [
    { key: "product_ids", label: "Products", model: "product.product" },
    { key: "template_ids", label: "Product templates", model: "product.template" },
    { key: "category_ids", label: "Product categories", model: "product.category" },
    { key: "uom_ids", label: "Units of measure", model: "uom.uom" },
    { key: "location_src_ids", label: "Source locations", model: "stock.location",
      domain: [["usage", "=", "internal"]] },
    { key: "location_dst_ids", label: "Destination locations", model: "stock.location",
      domain: [["usage", "=", "internal"]] },
    { key: "warehouse_ids", label: "Warehouses", model: "stock.warehouse" },
    { key: "picking_type_ids", label: "Operation types", model: "stock.picking.type" },
    { key: "rule_ids", label: "Stock rules", model: "stock.rule" },
    { key: "company_ids", label: "Companies", model: "res.company" },
];

export function createInitialState() {
    return {
        reports: [],
        currentReportId: null,
        dirty: false,
        loading: false,
        viewMode: "table",
        config: {
            name: "Delivery stats",
            interval: "month",
            period_start: null,
            period_end: null,
            horizon: 3,
            state_flags: { done: true },
            product_ids: [], template_ids: [], category_ids: [], uom_ids: [],
            location_src_ids: [], location_dst_ids: [],
            warehouse_ids: [], picking_type_ids: [], rule_ids: [],
            company_ids: [],
            extra_domain: [],
            group_by_field: "variant",
            model_ids: [],
            show_stats_info: true,
            hypothesis_testing: false,
            shorten_figures: true,
        },
        result: null,
    };
}

export const store = reactive(createInitialState());

export function markDirty() {
    store.dirty = true;
}

export function loadConfigIntoStore(config, recordId) {
    store.currentReportId = recordId || null;
    Object.assign(store.config, createInitialState().config, config);
    store.result = null;
    store.dirty = false;
}
