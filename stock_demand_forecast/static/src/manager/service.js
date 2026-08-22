/** @odoo-module **/
import { rpc } from "@web/core/network/rpc";
import { useService } from "@web/core/utils/hooks";

export async function refreshForecast(config) {
    try {
        return await rpc("/stock_demand_forecast/data", { config });
    } catch (e) {
        return { error: e?.message?.data?.message || e?.message || String(e) };
    }
}

export function exportConfig(config) {
    const form = document.createElement("form");
    form.method = "POST";
    form.action = "/stock_demand_forecast/export";
    const input = document.createElement("input");
    input.type = "hidden";
    input.name = "config_json";
    input.value = JSON.stringify(config);
    form.appendChild(input);
    document.body.appendChild(form);
    form.submit();
    form.remove();
}

export function useForecastService() {
    const notification = useService("notification");
    return {
        refresh: (config) => refreshForecast(config)
            .then((res) => {
                if (res?.error) {
                    notification.add(res.error, { type: "danger" });
                }
                return res;
            }),
        export: exportConfig,
    };
}
