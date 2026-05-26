import frappe
from pharma_management.pharma_quick_sale.doctype.pharma_quick_sale.pharma_quick_sale import run_go_live_preflight

def execute(filters=None):
    filters = filters or {}
    result = run_go_live_preflight(
        company=filters.get("company"),
        warehouse=filters.get("warehouse")
    )

    columns = [
        {"label": "Level", "fieldname": "level", "fieldtype": "Data", "width": 120},
        {"label": "Message", "fieldname": "message", "fieldtype": "Data", "width": 700}
    ]

    data = [{"level": "STATUS", "message": result.get("status")}]

    for section in ["master_data", "transactions"]:
        for msg in result[section].get("errors", []):
            data.append({"level": "ERROR", "message": msg})
        for msg in result[section].get("warnings", []):
            data.append({"level": "WARNING", "message": msg})
        for msg in result[section].get("checks", []):
            data.append({"level": "OK", "message": msg})

    return columns, data
