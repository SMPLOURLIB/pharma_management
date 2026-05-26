app_name = "pharma_management"
app_title = "Pharma Quick Management"
app_publisher = "SMPL"
app_description = "Pharma Quick sales and purhcase"
app_email = "support@ourlib.in"
app_license = "mit"




fixtures = ["Custom Field"]
# Open pharma_pos/pharma_pos/hooks.py

fixtures = [
    # Captures your custom fields (barcode, free_qty)
    {"dt": "Custom Field", "filters": [["dt", "in", ["Sales Invoice", "Sales Invoice Item"]]]},
    
    # NEW: Captures all hidden/modified field settings you just changed in Customize Form
    {"dt": "Property Setter", "filters": [["doc_type", "in", ["Sales Invoice", "Sales Invoice Item"]]]},

    {"dt": "Client Script","filters": [["dt", "in", ["Sales Invoice"]]]},

    {"dt": "Server Script","filters": [["reference_doctype", "in", ["Sales Invoice"]]]},
]

doc_events = {
    "Sales Invoice": {
        "validate": "pharma_management.pharma_quick_sale.doctype.pharma_quick_sale.pharma_quick_sale.copy_pharma_fields_to_sales_invoice",
        "on_submit": "pharma_management.pharma_quick_sale.doctype.pharma_quick_sale.pharma_quick_sale.consume_reservations_for_sales_invoice",
        "on_cancel": "pharma_management.pharma_quick_sale.doctype.pharma_quick_sale.pharma_quick_sale.release_reservations_for_sales_invoice"
    },
    "Sales Order": {
        "on_cancel": "pharma_management.pharma_quick_sale.doctype.pharma_quick_sale.pharma_quick_sale.release_reservations_for_sales_order"
    }
}




# Apps
# ------------------

# required_apps = []

# Each item in the list will be shown as an app in the apps page
# add_to_apps_screen = [
# 	{
# 		"name": "pharma_management",
# 		"logo": "/assets/pharma_management/logo.png",
# 		"title": "Pharma Quick Management",
# 		"route": "/pharma_management",
# 		"has_permission": "pharma_management.api.permission.has_app_permission"
# 	}
# ]

# Includes in <head>
# ------------------

# include js, css files in header of desk.html
# app_include_css = "/assets/pharma_management/css/pharma_management.css"
# app_include_js = "/assets/pharma_management/js/pharma_management.js"

# include js, css files in header of web template
# web_include_css = "/assets/pharma_management/css/pharma_management.css"
# web_include_js = "/assets/pharma_management/js/pharma_management.js"

# include custom scss in every website theme (without file extension ".scss")
# website_theme_scss = "pharma_management/public/scss/website"

# include js, css files in header of web form
# webform_include_js = {"doctype": "public/js/doctype.js"}
# webform_include_css = {"doctype": "public/css/doctype.css"}

# include js in page
# page_js = {"page" : "public/js/file.js"}

# include js in doctype views
# doctype_js = {"doctype" : "public/js/doctype.js"}
# doctype_list_js = {"doctype" : "public/js/doctype_list.js"}
# doctype_tree_js = {"doctype" : "public/js/doctype_tree.js"}
# doctype_calendar_js = {"doctype" : "public/js/doctype_calendar.js"}

# Svg Icons
# ------------------
# include app icons in desk
# app_include_icons = "pharma_management/public/icons.svg"

# Home Pages
# ----------

# application home page (will override Website Settings)
# home_page = "login"

# website user home page (by Role)
# role_home_page = {
# 	"Role": "home_page"
# }

# Generators
# ----------

# automatically create page for each record of this doctype
# website_generators = ["Web Page"]

# Jinja
# ----------

# add methods and filters to jinja environment
# jinja = {
# 	"methods": "pharma_management.utils.jinja_methods",
# 	"filters": "pharma_management.utils.jinja_filters"
# }

# Installation
# ------------

# before_install = "pharma_management.install.before_install"
# after_install = "pharma_management.install.after_install"

# Uninstallation
# ------------

# before_uninstall = "pharma_management.uninstall.before_uninstall"
# after_uninstall = "pharma_management.uninstall.after_uninstall"

# Integration Setup
# ------------------
# To set up dependencies/integrations with other apps
# Name of the app being installed is passed as an argument

# before_app_install = "pharma_management.utils.before_app_install"
# after_app_install = "pharma_management.utils.after_app_install"

# Integration Cleanup
# -------------------
# To clean up dependencies/integrations with other apps
# Name of the app being uninstalled is passed as an argument

# before_app_uninstall = "pharma_management.utils.before_app_uninstall"
# after_app_uninstall = "pharma_management.utils.after_app_uninstall"

# Desk Notifications
# ------------------
# See frappe.core.notifications.get_notification_config

# notification_config = "pharma_management.notifications.get_notification_config"

# Permissions
# -----------
# Permissions evaluated in scripted ways

# permission_query_conditions = {
# 	"Event": "frappe.desk.doctype.event.event.get_permission_query_conditions",
# }
#
# has_permission = {
# 	"Event": "frappe.desk.doctype.event.event.has_permission",
# }

# DocType Class
# ---------------
# Override standard doctype classes

# override_doctype_class = {
# 	"ToDo": "custom_app.overrides.CustomToDo"
# }

# Document Events
# ---------------
# Hook on document methods and events

# doc_events = {
# 	"*": {
# 		"on_update": "method",
# 		"on_cancel": "method",
# 		"on_trash": "method"
# 	}
# }

# Scheduled Tasks
# ---------------

# scheduler_events = {
# 	"all": [
# 		"pharma_management.tasks.all"
# 	],
# 	"daily": [
# 		"pharma_management.tasks.daily"
# 	],
# 	"hourly": [
# 		"pharma_management.tasks.hourly"
# 	],
# 	"weekly": [
# 		"pharma_management.tasks.weekly"
# 	],
# 	"monthly": [
# 		"pharma_management.tasks.monthly"
# 	],
# }

# Testing
# -------

# before_tests = "pharma_management.install.before_tests"

# Overriding Methods
# ------------------------------
#
# override_whitelisted_methods = {
# 	"frappe.desk.doctype.event.event.get_events": "pharma_management.event.get_events"
# }
#
# each overriding function accepts a `data` argument;
# generated from the base implementation of the doctype dashboard,
# along with any modifications made in other Frappe apps
# override_doctype_dashboards = {
# 	"Task": "pharma_management.task.get_dashboard_data"
# }

# exempt linked doctypes from being automatically cancelled
#
# auto_cancel_exempted_doctypes = ["Auto Repeat"]

# Ignore links to specified DocTypes when deleting documents
# -----------------------------------------------------------

# ignore_links_on_delete = ["Communication", "ToDo"]

# Request Events
# ----------------
# before_request = ["pharma_management.utils.before_request"]
# after_request = ["pharma_management.utils.after_request"]

# Job Events
# ----------
# before_job = ["pharma_management.utils.before_job"]
# after_job = ["pharma_management.utils.after_job"]

# User Data Protection
# --------------------

# user_data_fields = [
# 	{
# 		"doctype": "{doctype_1}",
# 		"filter_by": "{filter_by}",
# 		"redact_fields": ["{field_1}", "{field_2}"],
# 		"partial": 1,
# 	},
# 	{
# 		"doctype": "{doctype_2}",
# 		"filter_by": "{filter_by}",
# 		"partial": 1,
# 	},
# 	{
# 		"doctype": "{doctype_3}",
# 		"strict": False,
# 	},
# 	{
# 		"doctype": "{doctype_4}"
# 	}
# ]

# Authentication and authorization
# --------------------------------

# auth_hooks = [
# 	"pharma_management.auth.validate"
# ]

# Automatically update python controller files with type annotations for this app.
# export_python_type_annotations = True

# default_log_clearing_doctypes = {
# 	"Logging DocType Name": 30  # days to retain logs
# }

# Translation
# ------------
# List of apps whose translatable strings should be excluded from this app's translations.
# ignore_translatable_strings_from = []

