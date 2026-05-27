import frappe
from frappe.model.document import Document
from frappe.utils import flt, getdate, nowdate
from erpnext.stock.get_item_details import get_item_details


class PharmaQuickSale(Document):
    def validate(self):
        self.set_item_totals()
        self.validate_items_and_batches()

    def set_item_totals(self):
        allocations_by_row = {}
        for alloc in self.batch_allocations:
            allocations_by_row.setdefault(alloc.item_row_id, {"qty": 0, "free_qty": 0})
            allocations_by_row[alloc.item_row_id]["qty"] += flt(alloc.qty)
            allocations_by_row[alloc.item_row_id]["free_qty"] += flt(alloc.free_qty)

        for row in self.items:
            totals = allocations_by_row.get(row.row_id, {"qty": 0, "free_qty": 0})
            row.total_qty = totals["qty"]
            row.total_free_qty = totals["free_qty"]

    def validate_items_and_batches(self):
        if not self.items:
            frappe.throw("Please add at least one item.")
        if not self.batch_allocations:
            frappe.throw("Please add batch allocations.")

        item_by_row = {row.row_id: row for row in self.items}

        for row in self.items:
            if not row.row_id:
                frappe.throw("Each item row must have a row_id.")
            if not row.item_code:
                frappe.throw("Item is required.")
            item = frappe.get_doc("Item", row.item_code)
            row.item_name = item.item_name
            row.uom = row.uom or item.stock_uom
            row.conversion_factor = flt(row.conversion_factor) or 1

        for alloc in self.batch_allocations:
            if alloc.item_row_id not in item_by_row:
                frappe.throw(f"Invalid item_row_id in batch allocation: {alloc.item_row_id}")
            item_row = item_by_row[alloc.item_row_id]

            if alloc.item_code != item_row.item_code:
                frappe.throw(f"Batch allocation item {alloc.item_code} does not match item row {item_row.item_code}.")

            requested = flt(alloc.qty) + flt(alloc.free_qty)
            if requested <= 0:
                continue

            if not alloc.batch_no:
                frappe.throw(f"Batch is required for item {alloc.item_code}.")

            batch = frappe.get_doc("Batch", alloc.batch_no)
            if batch.item != alloc.item_code:
                frappe.throw(f"Batch {alloc.batch_no} does not belong to item {alloc.item_code}.")

            alloc.expiry_date = batch.expiry_date

            if batch.expiry_date and getdate(batch.expiry_date) < getdate(self.posting_date or nowdate()):
                frappe.throw(f"Expired batch: {alloc.batch_no}")

            physical_qty = get_batch_qty(alloc.item_code, alloc.batch_no, self.warehouse)
            reserved_qty = get_reserved_batch_qty(alloc.item_code, alloc.batch_no, self.warehouse)
            available_qty = max(physical_qty - reserved_qty, 0)
            alloc.available_qty = available_qty

            if available_qty < requested:
                frappe.throw(
                    f"Insufficient stock for {alloc.item_code}, batch {alloc.batch_no}. "
                    f"Available: {available_qty}, Required: {requested}"
                )

    def _get_item_details(self, item_code, doctype):
        currency = frappe.db.get_value("Company", self.company, "default_currency") or "INR"
        args = {
            "doctype": doctype,
            "item_code": item_code,
            "company": self.company,
            "customer": self.customer,
            "selling_price_list": self.price_list or "Standard Selling",
            "currency": currency,
            "conversion_rate": 1,
            "price_list_currency": currency,
            "plc_conversion_rate": 1,
            "transaction_date": self.posting_date or nowdate()
        }
        return get_item_details(args)

    def _append_items(self, target_doc, target_doctype):
        item_by_row = {row.row_id: row for row in self.items}

        def append_row(qty, rate, row, alloc, item_details, description=None):
            values = {
                "item_code": row.item_code,
                "qty": qty,
                "rate": rate,
                "warehouse": self.warehouse,
                "uom": row.uom or item_details.get("uom"),
                "conversion_factor": flt(row.conversion_factor) or item_details.get("conversion_factor") or 1,
                "item_tax_template": (
                item_details.get("item_tax_template")
                or row.get("item_tax_template")
                or _get_item_tax_template_from_item(
                    item_code,
                    tax_category=tax_category,
                    posting_date=data.get("posting_date") or nowdate()
                )
            ),
                "income_account": item_details.get("income_account"),
                "cost_center": item_details.get("cost_center"),
                "description": description or item_details.get("description") or row.item_name
            }

            if rate:
                values["discount_percentage"] = flt(row.discount_percentage)

            # Sales Invoice needs standard batch_no for stock posting.
            # Sales Order Item may not have batch_no in ERPNext v14/v15.
            if target_doctype == "Sales Invoice":
                values["batch_no"] = alloc.batch_no

            # Custom fields shipped as fixtures for SO/SI traceability.
            values["pharma_batch_no"] = alloc.batch_no
            values["pharma_quick_sale"] = self.name

            target_doc.append("items", values)

        for alloc in self.batch_allocations:
            row = item_by_row[alloc.item_row_id]
            item_details = self._get_item_details(row.item_code, target_doctype)

            if flt(alloc.qty) > 0:
                append_row(flt(alloc.qty), flt(row.rate), row, alloc, item_details)

            if flt(alloc.free_qty) > 0:
                append_row(
                    flt(alloc.free_qty),
                    0,
                    row,
                    alloc,
                    item_details,
                    description=f"Free Sample - {row.item_name or row.item_code}"
                )

    def create_sales_invoice(self):
        if self.sales_invoice:
            return frappe.get_doc("Sales Invoice", self.sales_invoice)

        invoice = frappe.new_doc("Sales Invoice")
        invoice.customer = self.customer
        invoice.company = self.company
        invoice.posting_date = self.posting_date or nowdate()
        invoice.set_posting_time = 1
        invoice.update_stock = 1
        invoice.selling_price_list = self.price_list or "Standard Selling"

        self._append_items(invoice, "Sales Invoice")

        if flt(self.bill_discount_amount) > 0:
            invoice.apply_discount_on = "Grand Total"
            invoice.discount_amount = flt(self.bill_discount_amount)

        invoice.run_method("set_missing_values")
        invoice.calculate_taxes_and_totals()
        invoice.insert(ignore_permissions=True)
        invoice.submit()

        self.db_set("sales_invoice", invoice.name)
        return invoice

    def create_sales_order(self):
        if self.sales_order:
            return frappe.get_doc("Sales Order", self.sales_order)

        sales_order = frappe.new_doc("Sales Order")
        sales_order.customer = self.customer
        sales_order.company = self.company
        sales_order.transaction_date = self.posting_date or nowdate()
        sales_order.delivery_date = self.posting_date or nowdate()
        sales_order.selling_price_list = self.price_list or "Standard Selling"

        self._append_items(sales_order, "Sales Order")

        if flt(self.bill_discount_amount) > 0:
            sales_order.apply_discount_on = "Grand Total"
            sales_order.discount_amount = flt(self.bill_discount_amount)

        sales_order.run_method("set_missing_values")
        sales_order.calculate_taxes_and_totals()
        sales_order.insert(ignore_permissions=True)
        sales_order.submit()

        self.db_set("sales_order", sales_order.name)
        reserve_batches_for_sales_order(sales_order.name)
        return sales_order


@frappe.whitelist()
def create_quick_sale(data, action="invoice"):
    if isinstance(data, str):
        data = frappe.parse_json(data)

    doc = frappe.new_doc("Pharma Quick Sale")
    doc.customer = data.get("customer")
    doc.company = data.get("company")
    doc.warehouse = data.get("warehouse")
    tax_category = data.get("tax_category")
    doc.posting_date = data.get("posting_date") or nowdate()
    doc.price_list = data.get("price_list") or "Standard Selling"
    doc.bill_discount_amount = flt(data.get("bill_discount_amount"))

    for item in data.get("items", []):
        doc.append("items", {
            "row_id": item.get("row_id"),
            "item_code": item.get("item_code"),
            "item_name": item.get("item_name"),
            "packing": item.get("packing"),
            "uom": item.get("uom"),
            "conversion_factor": flt(item.get("conversion_factor")) or 1,
            "rate": flt(item.get("rate")),
            "discount_percentage": flt(item.get("discount_percentage"))
        })

    for alloc in data.get("batch_allocations", []):
        doc.append("batch_allocations", {
            "item_row_id": alloc.get("item_row_id"),
            "item_code": alloc.get("item_code"),
            "batch_no": alloc.get("batch_no"),
            "expiry_date": alloc.get("expiry_date"),
            "available_qty": flt(alloc.get("available_qty")),
            "qty": flt(alloc.get("qty")),
            "free_qty": flt(alloc.get("free_qty"))
        })

    doc.insert(ignore_permissions=True)
    doc.submit()

    result = {"quick_sale": doc.name, "sales_invoice": None, "sales_order": None}

    if action == "invoice":
        si = doc.create_sales_invoice()
        result["sales_invoice"] = si.name
    elif action == "sales_order":
        so = doc.create_sales_order()
        result["sales_order"] = so.name
    else:
        frappe.throw("Invalid action. Use invoice or sales_order.")

    return result


@frappe.whitelist()
def get_batch_qty(item_code, batch_no, warehouse):
    return flt(frappe.db.sql("""
        SELECT SUM(actual_qty)
        FROM `tabStock Ledger Entry`
        WHERE item_code = %s
          AND batch_no = %s
          AND warehouse = %s
          AND is_cancelled = 0
    """, (item_code, batch_no, warehouse))[0][0] or 0)


@frappe.whitelist()
def get_item_price_lookup(item_code, customer=None, warehouse=None, price_list="Standard Selling"):
    item = frappe.get_doc("Item", item_code)

    price = frappe.db.get_value(
        "Item Price",
        {"item_code": item_code, "price_list": price_list, "selling": 1},
        "price_list_rate"
    ) or 0

    last_sale = []
    if customer:
        last_sale = frappe.db.sql("""
            SELECT
                sii.parent,
                si.posting_date,
                sii.qty,
                sii.rate,
                sii.discount_percentage
            FROM `tabSales Invoice Item` sii
            INNER JOIN `tabSales Invoice` si ON si.name = sii.parent
            WHERE si.docstatus = 1
              AND si.customer = %s
              AND sii.item_code = %s
            ORDER BY si.posting_date DESC, si.creation DESC
            LIMIT 5
        """, (customer, item_code), as_dict=True)

    stock_qty = 0
    if warehouse:
        stock_qty = flt(frappe.db.get_value("Bin", {"item_code": item_code, "warehouse": warehouse}, "actual_qty") or 0)

    return {
        "item_code": item_code,
        "item_name": item.item_name,
        "stock_uom": item.stock_uom,
        "price": price,
        "stock_qty": stock_qty,
        "last_sale": last_sale
    }


@frappe.whitelist()
def get_last_sales(customer, item_code=None, limit=10):
    conditions = ["si.docstatus = 1", "si.customer = %s"]
    values = [customer]

    if item_code:
        conditions.append("sii.item_code = %s")
        values.append(item_code)

    values.append(int(limit))

    return frappe.db.sql(f"""
        SELECT
            si.name AS invoice,
            si.posting_date,
            sii.item_code,
            sii.item_name,
            sii.qty,
            sii.rate,
            sii.discount_percentage,
            sii.amount
        FROM `tabSales Invoice Item` sii
        INNER JOIN `tabSales Invoice` si ON si.name = sii.parent
        WHERE {' AND '.join(conditions)}
        ORDER BY si.posting_date DESC, si.creation DESC
        LIMIT %s
    """, tuple(values), as_dict=True)


@frappe.whitelist()
def get_reserved_batch_qty(item_code, batch_no, warehouse):
    """Return app-level active reservation quantity.

    This is not a DB row lock. It is an application-level reservation helper.
    """
    if not frappe.db.table_exists("Pharma Batch Reservation"):
        return 0

    return flt(frappe.db.sql("""
        SELECT SUM(reserved_qty)
        FROM `tabPharma Batch Reservation`
        WHERE docstatus = 1
          AND status = 'Active'
          AND item_code = %s
          AND batch_no = %s
          AND warehouse = %s
    """, (item_code, batch_no, warehouse))[0][0] or 0)


@frappe.whitelist()
def allocate_fefo(item_code, warehouse, qty):
    requested_qty = flt(qty)
    if requested_qty <= 0:
        return []

    batches = frappe.db.sql("""
        SELECT
            sle.batch_no,
            b.expiry_date,
            SUM(sle.actual_qty) AS available_qty
        FROM `tabStock Ledger Entry` sle
        LEFT JOIN `tabBatch` b ON b.name = sle.batch_no
        WHERE sle.item_code = %s
          AND sle.warehouse = %s
          AND sle.batch_no IS NOT NULL
          AND sle.is_cancelled = 0
          AND (b.expiry_date IS NULL OR b.expiry_date >= CURDATE())
        GROUP BY sle.batch_no, b.expiry_date
        HAVING available_qty > 0
        ORDER BY b.expiry_date ASC
    """, (item_code, warehouse), as_dict=True)

    remaining = requested_qty
    allocations = []

    for batch in batches:
        if remaining <= 0:
            break

        reserved_qty = get_reserved_batch_qty(item_code, batch.batch_no, warehouse)
        net_available = max(flt(batch.available_qty) - flt(reserved_qty), 0)
        if net_available <= 0:
            continue

        alloc_qty = min(net_available, remaining)
        allocations.append({
            "batch_no": batch.batch_no,
            "expiry_date": batch.expiry_date,
            "available_qty": net_available,
            "reserved_qty": reserved_qty,
            "qty": alloc_qty,
            "free_qty": 0
        })
        remaining -= alloc_qty

    if remaining > 0:
        frappe.throw(f"Insufficient stock for {item_code}. Short by {remaining}")

    return allocations


@frappe.whitelist()
def get_item_by_barcode(barcode, warehouse=None, customer=None, price_list="Standard Selling"):
    """Resolve barcode safely across ERPNext v14 variants.

    Lookup order:
    1. Item Barcode child table
    2. Item.name exactly equals scanned value
    3. Item.item_code exactly equals scanned value, where field exists
    """
    if not barcode:
        frappe.throw("Barcode is required.")

    item_code = frappe.db.get_value("Item Barcode", {"barcode": barcode}, "parent")

    if not item_code and frappe.db.exists("Item", barcode):
        item_code = barcode

    if not item_code:
        try:
            item_code = frappe.db.get_value("Item", {"item_code": barcode}, "name")
        except Exception:
            item_code = None

    if not item_code:
        frappe.throw(f"No item found for barcode {barcode}")

    return get_item_price_lookup(item_code, customer=customer, warehouse=warehouse, price_list=price_list)


@frappe.whitelist()
def create_batch(item_code, expiry_date, batch_id=None):
    """Create or return a Batch idempotently.

    If batch_id is supplied and already exists for the same item, it is returned.
    If it exists for another item, the function blocks to prevent traceability errors.
    """
    if not item_code or not expiry_date:
        frappe.throw("Item and expiry date are required.")

    requested_batch = batch_id

    if requested_batch and frappe.db.exists("Batch", requested_batch):
        existing_item = frappe.db.get_value("Batch", requested_batch, "item")
        if existing_item != item_code:
            frappe.throw(f"Batch {requested_batch} already exists for item {existing_item}.")
        return requested_batch

    batch = frappe.new_doc("Batch")
    batch.batch_id = requested_batch or frappe.generate_hash(length=8).upper()
    batch.item = item_code
    batch.expiry_date = expiry_date
    batch.insert(ignore_permissions=True)
    return batch.name


@frappe.whitelist()
def create_fast_grn(data):
    """Create Purchase Receipt from fast pharma inward screen.

    Important valuation rule:
    - Paid qty is added at supplier rate.
    - Free qty is added as a separate row at rate 0.
    This avoids overstating purchase value.
    """
    if isinstance(data, str):
        data = frappe.parse_json(data)

    pr = frappe.new_doc("Purchase Receipt")
    pr.supplier = data.get("supplier")
    pr.company = data.get("company")
    pr.posting_date = data.get("posting_date") or nowdate()
    pr.set_posting_time = 1

    for item in data.get("items", []):
        item_code = item.get("item_code")
        batch_no = item.get("batch_no") or item.get("supplier_batch")

        if batch_no:
            if not frappe.db.exists("Batch", batch_no):
                batch_no = create_batch(item_code, item.get("expiry_date"), batch_no)
            else:
                existing_item = frappe.db.get_value("Batch", batch_no, "item")
                if existing_item != item_code:
                    frappe.throw(f"Batch {batch_no} belongs to {existing_item}, not {item_code}.")
        else:
            batch_no = create_batch(item_code, item.get("expiry_date"), item.get("supplier_batch"))

        warehouse = item.get("warehouse") or data.get("warehouse")
        paid_qty = flt(item.get("qty"))
        free_qty = flt(item.get("free_qty"))
        rate = flt(item.get("rate"))

        if paid_qty > 0:
            pr.append("items", {
                "item_code": item_code,
                "qty": paid_qty,
                "rate": rate,
                "warehouse": warehouse,
                "batch_no": batch_no
            })

        if free_qty > 0:
            pr.append("items", {
                "item_code": item_code,
                "qty": free_qty,
                "rate": 0,
                "warehouse": warehouse,
                "batch_no": batch_no,
                "description": f"Free Qty - {item_code}"
            })

    pr.run_method("set_missing_values")
    pr.calculate_taxes_and_totals()
    pr.insert(ignore_permissions=True)
    pr.submit()
    return pr.name


@frappe.whitelist()
def get_expiry_dashboard(days=180, warehouse=None):
    """Return batch expiry dashboard rows.

    Compatible with ERPNext v14/v15. Uses one warehouse placeholder only when
    warehouse is supplied, and one days placeholder for HAVING clause.
    """
    conditions = [
        "sle.batch_no IS NOT NULL",
        "sle.is_cancelled = 0",
        "b.expiry_date IS NOT NULL"
    ]
    values = []

    if warehouse:
        conditions.append("sle.warehouse = %s")
        values.append(warehouse)

    values.append(int(days))

    return frappe.db.sql(f"""
        SELECT
            sle.item_code,
            b.name AS batch_no,
            b.expiry_date,
            SUM(sle.actual_qty) AS qty,
            DATEDIFF(b.expiry_date, CURDATE()) AS days_to_expiry
        FROM `tabStock Ledger Entry` sle
        INNER JOIN `tabBatch` b ON b.name = sle.batch_no
        WHERE {' AND '.join(conditions)}
        GROUP BY sle.item_code, b.name, b.expiry_date
        HAVING qty > 0 AND days_to_expiry <= %s
        ORDER BY b.expiry_date ASC
    """, tuple(values), as_dict=True)



@frappe.whitelist()
def copy_pharma_fields_to_sales_invoice(doc, method=None):
    """Copy pharma custom fields from Sales Order Item to Sales Invoice Item.

    ERPNext usually maps same-name custom fields, but this hook makes the
    behavior explicit across v14/v15 and custom mapping paths.
    """
    invoice = doc if hasattr(doc, "items") else frappe.get_doc("Sales Invoice", doc)

    for row in invoice.items:
        if getattr(row, "pharma_batch_no", None):
            continue

        so_detail = getattr(row, "so_detail", None)
        sales_order = getattr(row, "sales_order", None) or getattr(row, "against_sales_order", None)

        if so_detail:
            so_row = frappe.db.get_value(
                "Sales Order Item",
                so_detail,
                ["pharma_batch_no", "pharma_quick_sale"],
                as_dict=True
            )
            if so_row:
                if so_row.get("pharma_batch_no"):
                    row.pharma_batch_no = so_row.get("pharma_batch_no")
                if so_row.get("pharma_quick_sale"):
                    row.pharma_quick_sale = so_row.get("pharma_quick_sale")
                continue

        if sales_order and row.item_code and row.warehouse:
            so_row = frappe.db.sql("""
                SELECT pharma_batch_no, pharma_quick_sale
                FROM `tabSales Order Item`
                WHERE parent = %s
                  AND item_code = %s
                  AND warehouse = %s
                  AND IFNULL(pharma_batch_no, '') != ''
                ORDER BY idx ASC
                LIMIT 1
            """, (sales_order, row.item_code, row.warehouse), as_dict=True)

            if so_row:
                row.pharma_batch_no = so_row[0].pharma_batch_no
                row.pharma_quick_sale = so_row[0].pharma_quick_sale

    return invoice


@frappe.whitelist()
def get_reservation_validation(sales_order=None):
    """Return reservation status rows for audit/UAT."""
    conditions = ["1=1"]
    values = []

    if sales_order:
        conditions.append("sales_order = %s")
        values.append(sales_order)

    return frappe.db.sql(f"""
        SELECT
            sales_order,
            sales_invoice,
            item_code,
            warehouse,
            batch_no,
            original_reserved_qty,
            reserved_qty,
            consumed_qty,
            status,
            docstatus
        FROM `tabPharma Batch Reservation`
        WHERE {' AND '.join(conditions)}
        ORDER BY modified DESC
        LIMIT 200
    """, tuple(values), as_dict=True)

def _get_batch_from_sales_row(row):
    return getattr(row, "pharma_batch_no", None) or getattr(row, "batch_no", None)


def _get_quick_sale_from_sales_row(row):
    return getattr(row, "pharma_quick_sale", None)


def _reservation_key(sales_order, item_code, batch_no, warehouse):
    return (sales_order or "", item_code or "", batch_no or "", warehouse or "")


def _get_sales_order_from_invoice_row(row):
    return (
        getattr(row, "sales_order", None)
        or getattr(row, "against_sales_order", None)
        or getattr(row, "so_detail", None)
    )


@frappe.whitelist()
def reserve_batches_for_sales_order(sales_order):
    """Aggregate and reserve Sales Order quantities by SO + item + batch + warehouse.

    This fixes split-row cases where the same item/batch appears more than once
    for billable and free quantities.
    """
    so = frappe.get_doc("Sales Order", sales_order)

    aggregate = {}

    for item in so.items:
        batch_no = _get_batch_from_sales_row(item)
        warehouse = item.warehouse

        if not batch_no or not warehouse:
            continue

        key = _reservation_key(so.name, item.item_code, batch_no, warehouse)
        aggregate.setdefault(key, 0)
        aggregate[key] += flt(item.qty)

    created_or_updated = []

    for key, required_qty in aggregate.items():
        sales_order_name, item_code, batch_no, warehouse = key

        existing = frappe.db.get_value(
            "Pharma Batch Reservation",
            {
                "sales_order": sales_order_name,
                "item_code": item_code,
                "warehouse": warehouse,
                "batch_no": batch_no,
                "status": "Active",
                "docstatus": 1
            },
            ["name", "reserved_qty"],
            as_dict=True
        )

        physical_qty = get_batch_qty(item_code, batch_no, warehouse)
        active_reserved = get_reserved_batch_qty(item_code, batch_no, warehouse)
        existing_qty = flt(existing.reserved_qty) if existing else 0
        net_available = physical_qty - active_reserved + existing_qty

        if net_available < required_qty:
            frappe.throw(
                f"Cannot reserve {required_qty} of {item_code}, batch {batch_no}. "
                f"Net available after active reservations: {net_available}"
            )

        if existing:
            res = frappe.get_doc("Pharma Batch Reservation", existing.name)
            if flt(res.reserved_qty) != flt(required_qty):
                res.db_set("reserved_qty", required_qty)
            created_or_updated.append(res.name)
        else:
            res = frappe.new_doc("Pharma Batch Reservation")
            res.sales_order = sales_order_name
            res.item_code = item_code
            res.warehouse = warehouse
            res.batch_no = batch_no
            res.reserved_qty = required_qty
            res.original_reserved_qty = required_qty
            res.status = "Active"
            res.insert(ignore_permissions=True)
            res.submit()
            created_or_updated.append(res.name)

    return created_or_updated


@frappe.whitelist()
def release_reservations_for_sales_order(doc, method=None):
    """Release active reservations when Sales Order is cancelled."""
    sales_order = doc.name if hasattr(doc, "name") else doc

    reservations = frappe.get_all(
        "Pharma Batch Reservation",
        filters={
            "sales_order": sales_order,
            "status": "Active",
            "docstatus": 1
        },
        pluck="name"
    )

    released = []
    for name in reservations:
        res = frappe.get_doc("Pharma Batch Reservation", name)
        res.db_set("status", "Released")
        released.append(name)

    return released


def _reservation_candidates_for_invoice(invoice):
    """Aggregate invoice rows against sales orders by SO + item + batch + warehouse."""
    aggregate = {}

    for row in invoice.items:
        sales_order = _get_sales_order_from_invoice_row(row)
        batch_no = _get_batch_from_sales_row(row)
        warehouse = row.warehouse

        if not sales_order or not batch_no or not warehouse:
            continue

        key = _reservation_key(sales_order, row.item_code, batch_no, warehouse)
        aggregate.setdefault(key, 0)
        aggregate[key] += flt(row.qty)

    return aggregate


@frappe.whitelist()
def consume_reservations_for_sales_invoice(doc, method=None):
    """Consume matching reservations when a Sales Invoice is submitted.

    v9 behavior:
    - Aggregates invoice rows by SO + item + batch + warehouse.
    - Supports full and partial consumption.
    - Tracks consumed_qty and last_sales_invoice for safer reversal.
    """
    invoice = doc if hasattr(doc, "items") else frappe.get_doc("Sales Invoice", doc)
    consumed = []

    for key, invoice_qty in _reservation_candidates_for_invoice(invoice).items():
        sales_order, item_code, batch_no, warehouse = key

        res_name = frappe.db.get_value(
            "Pharma Batch Reservation",
            {
                "sales_order": sales_order,
                "item_code": item_code,
                "batch_no": batch_no,
                "warehouse": warehouse,
                "status": "Active",
                "docstatus": 1
            },
            "name"
        )

        if not res_name:
            continue

        res = frappe.get_doc("Pharma Batch Reservation", res_name)

        remaining_after_invoice = flt(res.reserved_qty) - flt(invoice_qty)
        consumed_qty = flt(res.consumed_qty) + flt(invoice_qty)

        res.db_set("last_sales_invoice", invoice.name)
        if hasattr(res, "sales_invoice"):
            res.db_set("sales_invoice", invoice.name)
        res.db_set("consumed_qty", consumed_qty)

        if remaining_after_invoice <= 0:
            res.db_set("reserved_qty", 0)
            res.db_set("status", "Consumed")
        else:
            res.db_set("reserved_qty", remaining_after_invoice)

        consumed.append(res_name)

    return consumed


@frappe.whitelist()
def release_reservations_for_sales_invoice(doc, method=None):
    """On Sales Invoice cancellation, restore matching consumed reservation qty.

    v9 behavior:
    - Uses aggregate invoice qty.
    - Restores reserved_qty by the cancelled invoice quantity.
    - Reactivates reservation if status was Consumed.
    """
    invoice = doc if hasattr(doc, "items") else frappe.get_doc("Sales Invoice", doc)
    restored = []

    for key, invoice_qty in _reservation_candidates_for_invoice(invoice).items():
        sales_order, item_code, batch_no, warehouse = key

        # Prefer reservation linked to this invoice.
        res_name = frappe.db.get_value(
            "Pharma Batch Reservation",
            {
                "sales_order": sales_order,
                "item_code": item_code,
                "batch_no": batch_no,
                "warehouse": warehouse,
                "last_sales_invoice": invoice.name,
                "docstatus": 1
            },
            "name"
        )

        if not res_name:
            # Fallback for earlier records without last_sales_invoice.
            res_name = frappe.db.get_value(
                "Pharma Batch Reservation",
                {
                    "sales_order": sales_order,
                    "item_code": item_code,
                    "batch_no": batch_no,
                    "warehouse": warehouse,
                    "status": "Consumed",
                    "docstatus": 1
                },
                "name"
            )

        if not res_name:
            continue

        res = frappe.get_doc("Pharma Batch Reservation", res_name)
        new_reserved = flt(res.reserved_qty) + flt(invoice_qty)
        new_consumed = max(flt(res.consumed_qty) - flt(invoice_qty), 0)

        res.db_set("reserved_qty", new_reserved)
        res.db_set("consumed_qty", new_consumed)
        res.db_set("status", "Active")
        restored.append(res_name)

    return restored


@frappe.whitelist()
def validate_pharma_master_data(company=None, warehouse=None):
    """Go-live preflight master-data validation.

    Returns warnings/errors without changing data.
    """
    results = {
        "errors": [],
        "warnings": [],
        "checks": []
    }

    def ok(msg):
        results["checks"].append(msg)

    if company:
        if not frappe.db.exists("Company", company):
            results["errors"].append(f"Company not found: {company}")
        else:
            ok(f"Company exists: {company}")
    else:
        results["warnings"].append("Company not supplied for preflight.")

    if warehouse:
        if not frappe.db.exists("Warehouse", warehouse):
            results["errors"].append(f"Warehouse not found: {warehouse}")
        else:
            ok(f"Warehouse exists: {warehouse}")
    else:
        results["warnings"].append("Warehouse not supplied for preflight.")

    # Check required DocTypes exist.
    required_doctypes = [
        "Pharma Quick Sale",
        "Pharma Quick Sale Item",
        "Pharma Quick Sale Batch Allocation",
        "Pharma Batch Reservation",
        "Sales Invoice",
        "Sales Order",
        "Purchase Receipt",
        "Batch",
        "Item"
    ]

    for dt in required_doctypes:
        if not frappe.db.exists("DocType", dt):
            results["errors"].append(f"Required DocType missing: {dt}")
        else:
            ok(f"DocType available: {dt}")

    # Custom fields.
    required_custom_fields = [
        "Sales Order Item-pharma_batch_no",
        "Sales Order Item-pharma_quick_sale",
        "Sales Invoice Item-pharma_batch_no",
        "Sales Invoice Item-pharma_quick_sale"
    ]

    for cf in required_custom_fields:
        if not frappe.db.exists("Custom Field", cf):
            results["errors"].append(f"Required Custom Field missing: {cf}")
        else:
            ok(f"Custom Field available: {cf}")

    # Check stock settings negative stock.
    try:
        allow_negative_stock = frappe.db.get_single_value("Stock Settings", "allow_negative_stock")
        if allow_negative_stock:
            results["warnings"].append("Allow Negative Stock is enabled. Recommended: disable for pharma go-live.")
        else:
            ok("Allow Negative Stock is disabled.")
    except Exception as exc:
        results["warnings"].append(f"Could not verify Stock Settings: {exc}")

    return results


@frappe.whitelist()
def validate_pharma_transactions(company=None, warehouse=None, limit=20):
    """Go-live transaction validation for existing pharma/batch data.

    Returns warnings/errors without changing data.
    """
    results = {
        "errors": [],
        "warnings": [],
        "checks": []
    }

    def ok(msg):
        results["checks"].append(msg)

    # Check batch-enabled items with stock.
    batch_stock = frappe.db.sql("""
        SELECT
            sle.item_code,
            sle.batch_no,
            SUM(sle.actual_qty) AS qty
        FROM `tabStock Ledger Entry` sle
        WHERE sle.batch_no IS NOT NULL
          AND sle.is_cancelled = 0
        GROUP BY sle.item_code, sle.batch_no
        HAVING qty > 0
        LIMIT %s
    """, int(limit), as_dict=True)

    if batch_stock:
        ok(f"Batch stock found: {len(batch_stock)} sample rows.")
    else:
        results["warnings"].append("No positive batch stock found. Quick Sale FEFO cannot be tested without batch stock.")

    # Check item prices.
    prices = frappe.db.count("Item Price", {"selling": 1})
    if prices:
        ok(f"Selling Item Prices found: {prices}")
    else:
        results["warnings"].append("No selling Item Price records found. Quick Sale will default rates to zero.")

    # Check submitted Sales Invoices exist for last-sale lookup.
    sinv_count = frappe.db.count("Sales Invoice", {"docstatus": 1})
    if sinv_count:
        ok(f"Submitted Sales Invoices found: {sinv_count}")
    else:
        results["warnings"].append("No submitted Sales Invoices found. Last Sale Lookup will be empty until transactions exist.")

    return results


@frappe.whitelist()
def run_go_live_preflight(company=None, warehouse=None):
    """Run consolidated go-live preflight checks."""
    master = validate_pharma_master_data(company=company, warehouse=warehouse)
    transactions = validate_pharma_transactions(company=company, warehouse=warehouse)

    status = "PASS"
    if master["errors"] or transactions["errors"]:
        status = "FAIL"
    elif master["warnings"] or transactions["warnings"]:
        status = "PASS_WITH_WARNINGS"

    return {
        "status": status,
        "master_data": master,
        "transactions": transactions
    }



def _doctype_has_field(doctype, fieldname):
    """Safe field existence check for ERPNext v14/v15/customized sites."""
    try:
        return frappe.get_meta(doctype).has_field(fieldname)
    except Exception:
        return False


def _safe_get_value_if_field_exists(doctype, name_or_filters, fieldname):
    """Read a field only when the field exists to avoid runtime SQL errors."""
    if not _doctype_has_field(doctype, fieldname):
        return None
    try:
        return frappe.db.get_value(doctype, name_or_filters, fieldname)
    except Exception:
        return None


def _apply_sales_taxes_template_for_live_calc(invoice, customer=None):
    """Apply Sales Taxes and Charges Template to an unsaved invoice.

    Hardened for ERPNext v14/v15:
    - Does not assume Customer has taxes_and_charges.
    - Does not assume Company has default_sales_taxes_and_charges_template.
    - Falls back to default/first enabled Sales Taxes and Charges Template.
    - Returns None cleanly if no template exists.
    """
    template = None

    # 1. Customer-specific tax template, only if field exists.
    if customer:
        template = _safe_get_value_if_field_exists("Customer", customer, "taxes_and_charges")

    # 2. Company default Sales Taxes and Charges Template, only if field exists.
    if not template and invoice.company:
        template = _safe_get_value_if_field_exists(
            "Company",
            invoice.company,
            "default_sales_taxes_and_charges_template"
        )

    # 3. Default enabled company template.
    if not template and invoice.company:
        template = frappe.db.get_value(
            "Sales Taxes and Charges Template",
            {
                "company": invoice.company,
                "is_default": 1,
                "disabled": 0
            },
            "name"
        )

    # 4. First enabled company template.
    if not template and invoice.company:
        template = frappe.db.get_value(
            "Sales Taxes and Charges Template",
            {
                "company": invoice.company,
                "disabled": 0
            },
            "name"
        )

    # 5. Last fallback: first enabled template regardless of company.
    # Useful for early UAT where company may not be tagged on templates.
    if not template:
        template = frappe.db.get_value(
            "Sales Taxes and Charges Template",
            {
                "disabled": 0
            },
            "name"
        )

    if not template:
        return None

    invoice.taxes_and_charges = template

    tax_rows = frappe.get_all(
        "Sales Taxes and Charges",
        filters={
            "parent": template,
            "parenttype": "Sales Taxes and Charges Template"
        },
        fields=[
            "charge_type",
            "row_id",
            "account_head",
            "description",
            "included_in_print_rate",
            "included_in_paid_amount",
            "cost_center",
            "rate",
            "tax_amount",
            "total",
            "tax_amount_after_discount_amount",
            "base_tax_amount",
            "base_total",
            "base_tax_amount_after_discount_amount",
            "item_wise_tax_detail",
            "dont_recompute_tax",
        ],
        order_by="idx asc"
    )

    invoice.set("taxes", [])

    for tax in tax_rows:
        row = invoice.append("taxes", {})
        for key, value in tax.items():
            if key not in ("name", "parent", "parenttype", "parentfield", "idx", "doctype"):
                row.set(key, value)

    return template


def _get_item_tax_template_from_item(item_code, tax_category=None, posting_date=None):
    """Resolve Item Tax Template directly from Item -> Taxes child table.

    Works across ERPNext v14/v15 field variants by inspecting Item Tax metadata.
    """
    if not item_code:
        return None

    try:
        meta = frappe.get_meta("Item Tax")
    except Exception:
        return None

    fields = [df.fieldname for df in meta.fields]
    if "item_tax_template" not in fields:
        return None

    conditions = ["parent = %s", "parenttype = 'Item'", "IFNULL(item_tax_template, '') != ''"]
    values = [item_code]

    if tax_category and "tax_category" in fields:
        conditions.append("(tax_category = %s OR IFNULL(tax_category, '') = '')")
        values.append(tax_category)

    if posting_date and "valid_from" in fields:
        conditions.append("(valid_from IS NULL OR valid_from <= %s)")
        values.append(posting_date)

    order_by = "idx ASC"
    if "valid_from" in fields:
        order_by = "valid_from DESC, idx ASC"

    rows = frappe.db.sql(f"""
        SELECT item_tax_template
        FROM `tabItem Tax`
        WHERE {' AND '.join(conditions)}
        ORDER BY {order_by}
        LIMIT 1
    """, tuple(values), as_dict=True)

    return rows[0].item_tax_template if rows else None


def _get_item_tax_template_accounts(item_tax_template):
    """Return account/rate rows from Item Tax Template Detail."""
    if not item_tax_template:
        return []

    try:
        meta = frappe.get_meta("Item Tax Template Detail")
    except Exception:
        return []

    fields = [df.fieldname for df in meta.fields]

    account_field = "tax_type" if "tax_type" in fields else None
    rate_field = "tax_rate" if "tax_rate" in fields else None

    if not account_field or not rate_field:
        return []

    return frappe.db.sql(f"""
        SELECT {account_field} AS account_head, {rate_field} AS rate
        FROM `tabItem Tax Template Detail`
        WHERE parent = %s
        ORDER BY idx ASC
    """, item_tax_template, as_dict=True)


def _ensure_tax_rows_for_live_item_tax_templates(invoice):
    """Ensure tax rows exist for item-wise tax calculation and explicitly
    assigns rates to matching tax accounts from Item Tax templates.
    """
    account_rates = {}

    # 1. Map out all required accounts and rates from the items' templates
    for item in invoice.items:
        item_tax_template = getattr(item, "item_tax_template", None)
        if not item_tax_template:
            continue

        for row in _get_item_tax_template_accounts(item_tax_template):
            account_head = row.get("account_head")
            if not account_head:
                continue

            # Keep the rate defined in the item tax template
            account_rates[account_head] = flt(row.get("rate"))

    # 2. Update rates for rows that ALREADY exist in invoice.taxes
    updated_accounts = set()
    for tax in invoice.taxes:
        if tax.account_head in account_rates:
            tax.rate = account_rates[tax.account_head]
            updated_accounts.add(tax.account_head)

    # 3. Only append if the account doesn't exist in the tax table at all
    for account_head, rate in account_rates.items():
        if account_head in updated_accounts:
            continue

        invoice.append("taxes", {
            "charge_type": "On Net Total",
            "account_head": account_head,
            "description": account_head,
            "rate": rate
        })

@frappe.whitelist()
def get_live_sales_totals(data):
    """Return live ERPNext-calculated totals for Quick Sale.

    v19 behavior:
    - Reads Item Tax Template directly from Item master when get_item_details()
      does not return it.
    - Assigns item_tax_template to every live Sales Invoice row.
    - Ensures required tax account rows exist.
    - Allows different items to carry different item tax templates.
    - Does not insert or submit any document.
    """
    if isinstance(data, str):
        data = frappe.parse_json(data)

    customer = data.get("customer")
    company = data.get("company")
    warehouse = data.get("warehouse")
    tax_category = data.get("tax_category")
    posting_date = data.get("posting_date") or nowdate()

    if not customer or not company:
        return {
            "ready": False,
            "message": "Customer and Company are required for live tax calculation.",
            "net_total": 0,
            "total_taxes_and_charges": 0,
            "grand_total": 0,
            "taxes": [],
            "tax_template": None,
            "items": []
        }

    invoice = frappe.new_doc("Sales Invoice")
    invoice.customer = customer
    invoice.company = company
    invoice.posting_date = posting_date
    invoice.set_posting_time = 1
    invoice.update_stock = 1
    invoice.selling_price_list = data.get("price_list") or "Standard Selling"

    item_by_row = {}
    allocations_by_row = {}

    for item in data.get("items", []):
        row_id = item.get("row_id")
        if row_id and item.get("item_code"):
            item_by_row[row_id] = item

    for alloc in data.get("batch_allocations", []):
        row_id = alloc.get("item_row_id")
        if row_id:
            allocations_by_row.setdefault(row_id, [])
            allocations_by_row[row_id].append(alloc)

    def get_item_details_for(item_code):
        currency = frappe.db.get_value("Company", company, "default_currency") or "INR"
        args = {
            "doctype": "Sales Invoice",
            "item_code": item_code,
            "company": company,
            "customer": customer,
            "selling_price_list": data.get("price_list") or "Standard Selling",
            "currency": currency,
            "conversion_rate": 1,
            "price_list_currency": currency,
            "plc_conversion_rate": 1,
            "transaction_date": posting_date,
            "warehouse": warehouse
        }
        return get_item_details(args)

    def resolve_item_tax_template(row, item_details):
        item_code = row.get("item_code")
        return (
            item_details.get("item_tax_template")
            or row.get("item_tax_template")
            or _get_item_tax_template_from_item(
                item_code,
                tax_category=tax_category,
                posting_date=posting_date
            )
        )

    def append_invoice_row(row, qty, rate, item_details, batch_no=None, description=None):
        if flt(qty) <= 0:
            return

        item_code = row.get("item_code")
        item_tax_template = resolve_item_tax_template(row, item_details)

        values = {
            "item_code": item_code,
            "qty": flt(qty),
            "rate": flt(rate),
            "warehouse": warehouse,
            "uom": row.get("uom") or item_details.get("uom"),
            "conversion_factor": flt(row.get("conversion_factor")) or item_details.get("conversion_factor") or 1,
            "discount_percentage": flt(row.get("discount_percentage")),
            "item_tax_template": item_tax_template,
            "income_account": item_details.get("income_account"),
            "cost_center": item_details.get("cost_center"),
            "description": description or item_details.get("description") or row.get("item_name") or item_code
        }

        if batch_no:
            values["batch_no"] = batch_no

        invoice.append("items", values)

    for row_id, row in item_by_row.items():
        item_code = row.get("item_code")
        if not item_code:
            continue

        item_details = get_item_details_for(item_code)
        row_allocations = allocations_by_row.get(row_id) or []

        if row_allocations:
            for alloc in row_allocations:
                append_invoice_row(
                    row,
                    alloc.get("qty"),
                    row.get("rate"),
                    item_details,
                    batch_no=alloc.get("batch_no")
                )
                append_invoice_row(
                    row,
                    alloc.get("free_qty"),
                    0,
                    item_details,
                    batch_no=alloc.get("batch_no"),
                    description=f"Free Sample - {item_code}"
                )
        else:
            append_invoice_row(row, row.get("qty"), row.get("rate"), item_details)
            append_invoice_row(
                row,
                row.get("free_qty"),
                0,
                item_details,
                description=f"Free Sample - {item_code}"
            )

    if not invoice.items:
        return {
            "ready": False,
            "message": "Add item and quantity for live calculation.",
            "net_total": 0,
            "total_taxes_and_charges": 0,
            "grand_total": 0,
            "taxes": [],
            "tax_template": None,
            "items": []
        }

    if flt(data.get("bill_discount_amount")) > 0:
        invoice.apply_discount_on = "Grand Total"
        invoice.discount_amount = flt(data.get("bill_discount_amount"))

    tax_template = _apply_sales_taxes_template_for_live_calc(invoice, customer=customer)

    invoice.run_method("set_missing_values")

    if tax_template and not invoice.taxes:
        _apply_sales_taxes_template_for_live_calc(invoice, customer=customer)

    _ensure_tax_rows_for_live_item_tax_templates(invoice)

    invoice.calculate_taxes_and_totals()

    return {
        "ready": True,
        "message": "",
        "tax_template": tax_template,
        "net_total": flt(invoice.net_total),
        "total_taxes_and_charges": flt(invoice.total_taxes_and_charges),
        "grand_total": flt(invoice.grand_total),
        "rounded_total": flt(getattr(invoice, "rounded_total", 0)),
        "discount_amount": flt(getattr(invoice, "discount_amount", 0)),
        "taxes": [
            {
                "description": tax.description,
                "account_head": tax.account_head,
                "charge_type": tax.charge_type,
                "rate": flt(tax.rate),
                "tax_amount": flt(tax.tax_amount),
                "total": flt(tax.total),
                "item_wise_tax_detail": tax.item_wise_tax_detail
            }
            for tax in invoice.taxes
        ],
        "items": [
            {
                "item_code": item.item_code,
                "item_tax_template": item.item_tax_template,
                "net_amount": flt(item.net_amount),
                "amount": flt(item.amount)
            }
            for item in invoice.items
        ]
    }
