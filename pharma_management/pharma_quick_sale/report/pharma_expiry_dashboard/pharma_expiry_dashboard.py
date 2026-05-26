import frappe

def execute(filters=None):
    filters = filters or {}
    days = int(filters.get("days") or 180)

    columns = [
        {"label": "Item", "fieldname": "item_code", "fieldtype": "Link", "options": "Item", "width": 160},
        {"label": "Batch", "fieldname": "batch_no", "fieldtype": "Link", "options": "Batch", "width": 160},
        {"label": "Expiry Date", "fieldname": "expiry_date", "fieldtype": "Date", "width": 120},
        {"label": "Qty", "fieldname": "qty", "fieldtype": "Float", "width": 100},
        {"label": "Days to Expiry", "fieldname": "days_to_expiry", "fieldtype": "Int", "width": 120}
    ]

    data = frappe.db.sql("""
        SELECT
            sle.item_code,
            b.name AS batch_no,
            b.expiry_date,
            SUM(sle.actual_qty) AS qty,
            DATEDIFF(b.expiry_date, CURDATE()) AS days_to_expiry
        FROM `tabStock Ledger Entry` sle
        INNER JOIN `tabBatch` b ON b.name = sle.batch_no
        WHERE sle.batch_no IS NOT NULL
          AND sle.is_cancelled = 0
          AND b.expiry_date IS NOT NULL
        GROUP BY sle.item_code, b.name, b.expiry_date
        HAVING qty > 0 AND days_to_expiry <= %s
        ORDER BY b.expiry_date ASC
    """, days, as_dict=True)

    return columns, data
