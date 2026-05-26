frappe.query_reports["Pharma Reservation Validation"] = {
    filters: [
        {
            fieldname: "sales_order",
            label: "Sales Order",
            fieldtype: "Link",
            options: "Sales Order"
        }
    ]
};
