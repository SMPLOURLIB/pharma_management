frappe.pages['pharma-fast-grn'].on_page_load = function(wrapper) {
    new PharmaFastGRNPage(wrapper);
};

class PharmaFastGRNPage {
    constructor(wrapper) {
        this.page = frappe.ui.make_app_page({
            parent: wrapper,
            title: 'Pharma Fast GRN',
            single_column: true
        });
        this.make();
    }

    make() {
        this.page.body.html(`
            <div class="pfg-container" style="padding:12px;">
                <div style="display:grid;grid-template-columns:repeat(4,1fr);gap:8px;margin-bottom:10px;">
                    <div id="pfg-supplier"></div>
                    <div id="pfg-company"></div>
                    <div id="pfg-warehouse"></div>
                    <input type="date" id="pfg-posting-date" class="form-control">
                </div>

                <div style="margin-bottom:10px;">
                    <button class="btn btn-sm btn-default" id="pfg-add-row">Add Row</button>
                    <button class="btn btn-sm btn-primary" id="pfg-create">Create Purchase Receipt</button>
                    <button class="btn btn-sm btn-danger" id="pfg-clear">Clear</button>
                </div>

                <table class="table table-bordered">
                    <thead>
                        <tr>
                            <th>Item</th><th>Batch</th><th>Expiry</th><th>Qty</th><th>Free</th><th>Rate</th><th>Remove</th>
                        </tr>
                    </thead>
                    <tbody id="pfg-items"></tbody>
                </table>
            </div>
        `);

        this.supplier = frappe.ui.form.make_control({
            parent: $('#pfg-supplier'),
            df: {fieldtype:'Link', options:'Supplier', fieldname:'supplier', label:'Supplier', reqd:1},
            render_input: true
        });
        this.company = frappe.ui.form.make_control({
            parent: $('#pfg-company'),
            df: {fieldtype:'Link', options:'Company', fieldname:'company', label:'Company', reqd:1},
            render_input: true
        });
        this.company.set_value(frappe.defaults.get_default('company'));
        this.warehouse = frappe.ui.form.make_control({
            parent: $('#pfg-warehouse'),
            df: {fieldtype:'Link', options:'Warehouse', fieldname:'warehouse', label:'Warehouse', reqd:1},
            render_input: true
        });
        $('#pfg-posting-date').val(frappe.datetime.get_today());

        $('#pfg-add-row').on('click', () => this.add_row());
        $('#pfg-create').on('click', () => this.create_grn());
        $('#pfg-clear').on('click', () => { $('#pfg-items').empty(); this.add_row(); });

        this.add_row();
    }

    add_row() {
        const row = $(`
            <tr>
                <td><div class="item-control"></div></td>
                <td><input class="form-control batch-no" placeholder="Batch"></td>
                <td><input type="date" class="form-control expiry-date"></td>
                <td><input type="number" class="form-control qty" value="0"></td>
                <td><input type="number" class="form-control free-qty" value="0"></td>
                <td><input type="number" class="form-control rate" value="0"></td>
                <td><button class="btn btn-xs btn-danger remove">X</button></td>
            </tr>
        `);
        $('#pfg-items').append(row);

        const item_control = frappe.ui.form.make_control({
            parent: row.find('.item-control'),
            df: {fieldtype:'Link', options:'Item', fieldname:'item_code'},
            render_input: true
        });
        row.data('item_control', item_control);
        row.find('.remove').on('click', () => row.remove());
    }

    collect_data() {
        let items = [];
        $('#pfg-items tr').each((i, el) => {
            const row = $(el);
            const item_code = row.data('item_control').get_value();
            if (!item_code) return;
            items.push({
                item_code,
                batch_no: row.find('.batch-no').val(),
                supplier_batch: row.find('.batch-no').val(),
                expiry_date: row.find('.expiry-date').val(),
                qty: flt(row.find('.qty').val()),
                free_qty: flt(row.find('.free-qty').val()),
                rate: flt(row.find('.rate').val()),
                warehouse: this.warehouse.get_value()
            });
        });
        return {
            supplier: this.supplier.get_value(),
            company: this.company.get_value(),
            warehouse: this.warehouse.get_value(),
            posting_date: $('#pfg-posting-date').val(),
            items
        };
    }

    create_grn() {
        const data = this.collect_data();
        if (!data.supplier || !data.company || !data.warehouse || !data.items.length) {
            frappe.msgprint('Supplier, Company, Warehouse, and items are required.');
            return;
        }
        frappe.call({
            method: 'pharma_quick_sale.pharma_quick_sale.doctype.pharma_quick_sale.pharma_quick_sale.create_fast_grn',
            args: {data},
            freeze: true,
            freeze_message: 'Creating Purchase Receipt...',
            callback: (r) => {
                frappe.msgprint(`Purchase Receipt Created: ${r.message}`);
                frappe.set_route('Form', 'Purchase Receipt', r.message);
            }
        });
    }
}
