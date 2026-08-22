/** @odoo-module **/
import { Component, useState, onWillStart } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";
import { DomainSelector } from "@web/core/domain_selector/domain_selector";
import { TableView } from "../views/table_view";
import { ChartPanel } from "../views/chart_panel";
import {
    INTERVALS, GROUP_BYS, STATES, FILTER_DEFS, createInitialState,
} from "./store";
import { refreshForecast, exportConfig } from "./service";

export class ForecastManager extends Component {
    static template = "stock_demand_forecast.Manager";
    static components = { TableView, ChartPanel, DomainSelector };

    setup() {
        this.orm = useService("orm");
        this.notification = useService("notification");
        this.state = useState({
            reports: [],
            currentReportId: null,
            dirty: false,
            loading: false,
            viewMode: "table",
            config: createInitialState().config,
        });
        this.search = useState({ openFilter: null, options: [], term: "" });
        this.modelSearch = useState({ open: false, options: [] });
        this.intervals = INTERVALS;
        this.groupBys = GROUP_BYS;
        this.statesList = STATES;
        this.filterDefs = FILTER_DEFS;
        onWillStart(() => this.onLoadReports());
    }

    get config() {
        return this.state.config;
    }

    get hasResult() {
        return !!(this.state.result && this.state.result.series);
    }

    get extraDomainStr() {
        const d = this.config.extra_domain;
        return JSON.stringify(Array.isArray(d) ? d : []);
    }

    /* ---------- filters ---------- */

    async onFilterClick(def) {
        if (this.search.openFilter === def.key) {
            this.search.openFilter = null;
            return;
        }
        this.search.openFilter = def.key;
        await this.onFilterSearch(def, "");
    }

    async onFilterSearch(def, ev) {
        const term = typeof ev === "string" ? ev : (ev?.target?.value ?? "");
        const domain = [...(def.domain || []), ["name", "ilike", term]];
        try {
            const records = await this.orm.searchRead(
                def.model, domain, ["display_name"], { limit: 8 });
            const selected = new Set(this.config[def.key].map((r) => r.id));
            this.search.options = records
                .filter((r) => !selected.has(r.id))
                .slice(0, 6);
        } catch (_e) {
            this.search.options = [];
        }
    }

    onSelectOption(def, res) {
        if (!this.config[def.key].some((r) => r.id === res.id)) {
            this.config[def.key].push({
                id: res.id, display_name: res.display_name });
            this.state.dirty = true;
        }
        this.search.openFilter = null;
        this.search.options = [];
    }

    onRemoveTag(defKey, id) {
        const ids = this.config[defKey];
        const i = ids.findIndex((r) => r.id === id);
        if (i >= 0) {
            ids.splice(i, 1);
            this.state.dirty = true;
        }
    }

    /* ---------- extra domain ---------- */

    onExtraDomainChange(domain) {
        this.config.extra_domain = domain;
        this.state.dirty = true;
    }

    /* ---------- states & toggles & plain fields ---------- */

    toggleState(key, val) {
        this.config.state_flags[key] = val;
        this.state.dirty = true;
    }

    setField(field, value) {
        this.config[field] = value;
        this.state.dirty = true;
    }

    /* ---------- stats models ---------- */

    async onModelClick() {
        this.modelSearch.open = !this.modelSearch.open;
        await this.onModelSearch("");
    }

    async onModelSearch(term) {
        try {
            const records = await this.orm.searchRead(
                "stats.model", [["reference", "ilike", term]],
                ["display_name"], { limit: 8 });
            const selected = new Set(this.config.model_ids.map((r) => r.id));
            this.modelSearch.options = records
                .filter((r) => !selected.has(r.id));
        } catch (_e) {
            this.modelSearch.options = [];
        }
    }

    onSelectModel(res) {
        this.config.model_ids.push({
            id: res.id, display_name: res.display_name });
        this.state.dirty = true;
        this.modelSearch.open = false;
    }

    onRemoveModel(id) {
        const i = this.config.model_ids.findIndex((r) => r.id === id);
        if (i >= 0) {
            this.config.model_ids.splice(i, 1);
            this.state.dirty = true;
        }
    }

    /* ---------- action bar ---------- */

    async onLoadReports() {
        try {
            this.state.reports = await this.orm.searchRead(
                "forecast.report", [["active", "=", true]], ["name"],
                { order: "name ASC" });
        } catch (_e) {
            this.state.reports = [];
        }
    }

    async onRefresh() {
        this.state.loading = true;
        // deep copy so reactive proxies serialize cleanly over jsonrpc
        const config = JSON.parse(JSON.stringify(this.config));
        const res = await refreshForecast(config);
        this.state.loading = false;
        if (res && !res.error) {
            this.state.result = res;
            this.state.dirty = false;
        } else if (res?.error) {
            this.notification.add(res.error, { type: "danger" });
        }
    }

    onSave() {
        const vals = JSON.parse(JSON.stringify(this.config));
        delete vals.report_id;
        const done = (id) => {
            this.state.dirty = false;
            this.notification.add("Report saved", { type: "success" });
            this.onLoadReports();
        };
        if (this.state.currentReportId) {
            this.orm.write("forecast.report",
                [this.state.currentReportId], vals).then(() =>
                done(this.state.currentReportId));
        } else {
            this.orm.create("forecast.report", [vals]).then((ids) => {
                this.state.currentReportId = ids[0];
                done(ids[0]);
            });
        }
    }

    async onSelectReport(ev) {
        const id = parseInt(ev.target.value, 10);
        if (!id) { return; }
        const recs = await this.orm.read(
            "forecast.report", [id],
            ["name", "interval", "period_start", "period_end", "horizon",
             "state_flags", "extra_domain", "group_by_field",
             "show_stats_info", "hypothesis_testing", "shorten_figures",
             "product_ids", "template_ids", "category_ids", "uom_ids",
             "location_src_ids", "location_dst_ids", "warehouse_ids",
             "picking_type_ids", "rule_ids", "company_ids", "model_ids"]);
        const rec = recs[0];
        if (!rec) { return; }
        const cfg = this.config;
        cfg.name = rec.name;
        cfg.interval = rec.interval;
        cfg.period_start = rec.period_start;
        cfg.period_end = rec.period_end;
        cfg.horizon = rec.horizon;
        cfg.state_flags = rec.state_flags || { done: true };
        cfg.extra_domain = rec.extra_domain || [];
        cfg.group_by_field = rec.group_by_field;
        cfg.show_stats_info = rec.show_stats_info;
        cfg.hypothesis_testing = rec.hypothesis_testing;
        cfg.shorten_figures = rec.shorten_figures;
        for (const key of ["product_ids", "template_ids", "category_ids",
            "uom_ids", "location_src_ids", "location_dst_ids",
            "warehouse_ids", "picking_type_ids", "rule_ids",
            "company_ids"]) {
            cfg[key] = (rec[key] || []).map((i) => ({
                id: i, display_name: "#" + i }));
        }
        const models = rec.model_ids || [];
        const modelRecs = models.length
            ? await this.orm.read("stats.model", models, ["display_name"])
            : [];
        cfg.model_ids = modelRecs.map((m) => ({
            id: m.id, display_name: m.display_name }));
        this.state.result = null;
        this.state.currentReportId = id;
        this.state.dirty = false;
    }

    onNewReport() {
        window.location.hash = "";
        window.location.reload();
    }

    onExport() {
        exportConfig(JSON.parse(JSON.stringify(this.config)));
    }
}
