{
    "name": "Stock Demand Trends & Forecast",
    "version": "19.0.1.0.0",
    "category": "Inventory/Inventory",
    "summary": "Statistical demand forecasts based on stock moves",
    "description": """Turn stock-move history into statistical demand forecasts
with AutoReg, ARDL, ARIMA, SARIMAX, Holt-Winters and SES (statsmodels).
Reusable reports, hypothesis testing, table/chart views, Excel export.""",
    "author": "test-addons",
    "license": "OPL-1",
    "depends": ["stock"],
    "external_dependencies": {
        "python": ["pandas", "numpy", "statsmodels", "scipy", "xlsxwriter", "pydantic"],
    },
    "data": [
        "security/security.xml",
        "security/ir.model.access.csv",
        "views/stats_model_views.xml",
        "views/client_action.xml",
        "views/menus.xml",
    ],
    "demo": ["demo/demo_data.xml"],
    "assets": {
        "web.assets_backend": [
            "stock_demand_forecast/static/src/**/*.js",
            "stock_demand_forecast/static/src/**/*.xml",
            "stock_demand_forecast/static/src/**/*.scss",
        ],
    },
    "application": False,
    "installable": True,
}
