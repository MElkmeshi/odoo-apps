/** @odoo-module **/
import { registry } from "@web/core/registry";
import { ForecastManager } from "./manager";

registry.category("actions").add("stock_demand_forecast.manager", ForecastManager);
