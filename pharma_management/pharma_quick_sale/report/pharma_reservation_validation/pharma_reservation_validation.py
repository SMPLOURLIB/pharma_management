import frappe

def execute(filters=None):
    filters = filters or {}
    sales_order = filters.get("sales_order")

    conditions = ["1=1"]
    values = []

    if sales_order:
        conditions.append("sales_order = %s")
        values.append(sales_order)

    columns = [
        {"label": "Sales Order", "fieldname": "sales_order", "fieldtype": "Link", "options": "Sales Order", "width": 160},
        {"label": "Sales Invoice", "fieldname": "sales_invoice", "fieldtype": "Link", "options": "Sales Invoice", "width": 160},
        {"label": "Item", "fieldname": "item_code", "fieldtype": "Link", "options": "Item", "width": 140},
        {"label": "Warehouse", "fieldname": "warehouse", "fieldtype": "Link", "options": "Warehouse", "width": 140},
        {"label": "Batch", "fieldname": "batch_no", "fieldtype": "Link", "options": "Batch", "width": 140},
        {"label": "Original", "fieldname": "original_reserved_qty", "fieldtype": "Float", "width": 90},
        {"label": "Reserved", "fieldname": "reserved_qty", "fieldtype": "Float", "width": 90},
        {"label": "Consumed", "fieldname": "consumed_qty", "fieldtype": "Float", "width": 90},
        {"label": "Status", "fieldname": "status", "fieldtype": "Data", "width": 100}
    ]

    data = frappe.db.sql(f"""
        SELECT
            sales_order,
            sales_invoice,
            item_code,
            warehouse,
            batch_no,
            original_reserved_qty,
            reserved_qty,
            consumed_qty,
            status
        FROM `tabPharma Batch Reservation`
        WHERE {' AND '.join(conditions)}
        ORDER BY modified DESC
        LIMIT 500
    """, tuple(values), as_dict=True)

    return columns, data
