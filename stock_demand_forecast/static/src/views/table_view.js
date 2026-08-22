/** @odoo-module **/
import { Component, useState } from "@odoo/owl";

export class TableView extends Component {
    static template = "stock_demand_forecast.TableView";
    static props = ["result"];

    setup() {
        this.expanded = useState({ keys: [] });
        this.result = this.props.result;
    }

    get rows() {
        const r = this.props.result;
        const histLabels = [...r.labels].reverse();
        return { histLabels, forecastLabels: r.forecast_labels };
    }

    get columns() {
        return this.props.result.series;
    }

    histValue(series, i) {
        const vals = [...(series.history || [])].reverse();
        return vals[i] ?? "";
    }

    fmt(v) {
        if (v === "" || v == null) {
            return "";
        }
        const shorten = this.props.result.meta?.shorten;
        const num = Number(v);
        if (!Number.isFinite(num)) {
            return String(v);
        }
        if (!shorten || Math.abs(num) < 1000) {
            return num.toLocaleString("en-US",
                { maximumFractionDigits: 1 });
        }
        const units = [["b", 1e9], ["m", 1e6], ["k", 1e3]];
        for (const [suffix, size] of units) {
            if (Math.abs(num) >= size) {
                return Math.round((num / size) * 10) / 10 + suffix;
            }
        }
        return String(Math.round(num));
    }

    toggleStats(key) {
        const i = this.expanded.keys.indexOf(key);
        if (i >= 0) {
            this.expanded.keys.splice(i, 1);
        } else {
            this.expanded.keys.push(key);
        }
    }

    statsText(key) {
        // rendered per column when expanded
        return this.props.result.series.find((s) => s.key === key)?.stats || {};
    }

    statLine(label, value) {
        return `${label}: ${this.fmt(value)}\n`;
    }
}
