import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_field

def execute():
    # Define the custom field properties
    custom_field_data = {
        "dt": "Company",
        "fieldname": "custom_default_sale_warehouse",
        "label": "Default Sale Warehouse",
        "fieldtype": "Link",
        "options": "Warehouse",
        "insert_after": "expenses_included_in_valuation",  # Positions it after the Domain field
        "reqd": 0                  # 0 means optional, change to 1 if mandatory
    }
    
    # Create the field if it does not already exist
    create_custom_field("Company", custom_field_data)
    

    if not frappe.db.exists("Property Setter", "Company-custom_default_sale_warehouse-link_filters"):
        property_setter = frappe.get_doc({
            "doctype": "Property Setter",
            "doctype_or_field": "DocField",
            "doc_type": "Company",
            "field_name": "custom_default_sale_warehouse",
            "property": "link_filters",
            "value": '[["Warehouse", "company", "=", "eval:doc.company_name"]]',
            "property_type": "Small Text"
        })
        property_setter.insert(ignore_permissions=True)
        frappe.db.commit()

