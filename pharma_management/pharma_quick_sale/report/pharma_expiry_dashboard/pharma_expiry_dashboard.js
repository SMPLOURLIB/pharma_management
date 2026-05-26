frappe.query_reports["Pharma Expiry Dashboard"] = {
    filters: [
        {
            fieldname: "days",
            label: "Days",
            fieldtype: "Int",
            default: 180
        }
    ]
};
