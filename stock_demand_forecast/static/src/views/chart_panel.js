/** @odoo-module **/
import { Component, onWillStart, useRef, useEffect } from "@odoo/owl";
import { loadBundle } from "@web/core/assets";

const HISTORY_COLOR = "#9ec5fe";
const FORECAST_COLORS = ["#1a73e8", "#017e84", "#e8710a", "#9334e6",
    "#dc3545", "#198754"];

export class ChartPanel extends Component {
    static template = "stock_demand_forecast.ChartPanel";
    static props = ["result", "mode"];

    setup() {
        this.canvasRef = useRef("canvas");
        this.chart = null;
        onWillStart(() => loadBundle("web.chartjs_lib"));
        useEffect(
            (result, mode) => {
                if (!result || !this.canvasRef.el) {
                    return;
                }
                this.renderChart(result, mode);
                return () => this.destroyChart();
            },
            () => [this.props.result, this.props.mode],
        );
    }

    destroyChart() {
        if (this.chart) {
            this.chart.destroy();
            this.chart = null;
        }
    }

    get datasets() {
        const r = this.props.result;
        const datasets = [];
        let colorIdx = 0;
        for (const s of r.series) {
            const color = FORECAST_COLORS[colorIdx % FORECAST_COLORS.length];
            colorIdx += 1;
            const histData =
                [...(s.history_pre || []), ...(s.history || [])];
            datasets.push({
                label: s.label,
                data: histData,
                borderColor: HISTORY_COLOR,
                backgroundColor: HISTORY_COLOR,
                borderWidth: 2,
                pointRadius: 0,
                tension: 0.3,
                order: 2,
            });
            // forecast aligned to the end of the displayed history
            const padLen = Math.max(histData.length - 1, 0);
            const pad = Array(padLen).fill(null);
            const fc = (s.forecast || []).map((v) =>
                v == null ? null : Math.round(v * 100) / 100);
            datasets.push({
                label: s.label + " (forecast)",
                data: [...pad, ...fc],
                borderColor: color,
                backgroundColor: color,
                borderWidth: 2,
                borderDash: [6, 4],
                pointRadius: 0,
                tension: 0.3,
                order: 1,
            });
            if (r.meta.hypothesis && s.actuals?.length) {
                const hypPad = Array((s.history_pre || []).length).fill(null);
                datasets.push({
                    label: s.label + " (actual)",
                    data: [...hypPad, ...(s.actuals || [])],
                    borderColor: "#22262b",
                    backgroundColor: "#22262b",
                    borderWidth: 1,
                    pointRadius: 3,
                    showLine: false,
                    order: 0,
                });
            }
        }
        return datasets;
    }

    get labels() {
        const r = this.props.result;
        return [...r.labels, ...r.forecast_labels].slice(-60);
    }

    renderChart(result, mode) {
        const Chart = window.Chart;
        if (!Chart) {
            return;
        }
        this.destroyChart();
        this.chart = new Chart(this.canvasRef.el, {
            type: mode === "bar" ? "bar" : "line",
            data: { labels: this.labels, datasets: this.datasets },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                interaction: { intersect: false, mode: "index" },
                plugins: { legend: { position: "top" } },
                scales: {
                    y: { beginAtZero: true },
                    x: { ticks: { maxRotation: 90, minRotation: 45 } },
                },
            },
        });
    }
}
