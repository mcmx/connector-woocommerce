# -*- coding: utf-8 -*-
#
#
#    Tech-Receptives Solutions Pvt. Ltd.
#    Copyright (C) 2009-TODAY Tech-Receptives(<http://www.techreceptives.com>).
#
#    This program is free software: you can redistribute it and/or modify
#    it under the terms of the GNU Affero General Public License as
#    published by the Free Software Foundation, either version 3 of the
#    License, or (at your option) any later version.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU Affero General Public License for more details.
#
#    You should have received a copy of the GNU Affero General Public License
#    along with this program.  If not, see <http://www.gnu.org/licenses/>.
#
#

import logging

from odoo.addons.component.core import Component
from odoo.addons.connector.components.mapper import mapping

from odoo import models, fields, api

_logger = logging.getLogger(__name__)


class woo_sale_order_status(models.Model):
    _name = 'woo.sale.order.status'
    _description = 'WooCommerce Sale Order Status'

    name = fields.Char('Name')
    desc = fields.Text('Description')


class SaleOrder(models.Model):

    _inherit = 'sale.order'
    status_id = fields.Many2one('woo.sale.order.status',
                                'WooCommerce Order Status')


class WooSaleOrder(models.Model):
    _name = 'woo.sale.order'
    _inherit = 'woo.binding'
    _inherits = {'sale.order': 'openerp_id'}
    _description = 'Woo Sale Order'

    _rec_name = 'name'

    status_id = fields.Many2one('woo.sale.order.status',
                                'WooCommerce Order Status')

    openerp_id = fields.Many2one(comodel_name='sale.order',
                                 string='Sale Order',
                                 required=True,
                                 ondelete='cascade')
    woo_order_line_ids = fields.One2many(
        comodel_name='woo.sale.order.line',
        inverse_name='woo_order_id',
        string='Woo Order Lines'
    )
    backend_id = fields.Many2one(
        comodel_name='wc.backend',
        string='Woo Backend',
        store=True,
        readonly=False,
        required=True,
    )


class WooSaleOrderLine(models.Model):
    _name = 'woo.sale.order.line'
    _inherits = {'sale.order.line': 'openerp_id'}

    woo_order_id = fields.Many2one(comodel_name='woo.sale.order',
                                   string='Woo Sale Order',
                                   required=True,
                                   ondelete='cascade',
                                   select=True)

    openerp_id = fields.Many2one(comodel_name='sale.order.line',
                                 string='Sale Order Line',
                                 required=True,
                                 ondelete='cascade')

    backend_id = fields.Many2one(
        related='woo_order_id.backend_id',
        string='Woo Backend',
        readonly=True,
        store=True,
        required=False,
    )

    @api.model
    def create(self, vals):
        woo_order_id = vals['woo_order_id']
        binding = self.env['woo.sale.order'].browse(woo_order_id)
        vals['order_id'] = binding.openerp_id.id
        binding = super(WooSaleOrderLine, self).create(vals)
        return binding


class SaleOrderLine(models.Model):
    _inherit = 'sale.order.line'

    woo_bind_ids = fields.One2many(
        comodel_name='woo.sale.order.line',
        inverse_name='openerp_id',
        string="WooCommerce Bindings",
    )


class SaleOrderLineImportMapper(Component):
    _name = 'woo.sale.line.import.mapper'
    _inherit = ['base.import.mapper']
    _apply_on = 'woo.sale.order.line'

    direct = [('quantity', 'product_uom_qty'),
              # ('quantity', 'product_uos_qty'),
              ('name', 'name'),
              ('price', 'price_unit')
              ]

    @mapping
    def product_id(self, record):
        binder = self.binder_for('woo.product.product')
        product_id = binder.to_openerp(record['product_id'], unwrap=True)
        assert product_id is not None, (
            "product_id %s should have been imported in "
            "SaleOrderImporter._import_dependencies" % record['product_id'])
        return {'product_id': product_id}


class SaleOrderAdapter(Component):
    _name = 'woo.sale.adapter'
    _inherit = ['woo.adapter']
    _apply_on = 'woo.sale.order'
    _woo_model = 'orders'

    def search(self, filters=None, from_date=None, to_date=None):
        """ Search records according to some criteria and return a
        list of ids

        :rtype: list
        """
        if filters is None:
            filters = {}
        WOO_DATETIME_FORMAT = '%Y/%m/%d %H:%M:%S'
        dt_fmt = WOO_DATETIME_FORMAT
        if from_date is not None:
            # updated_at include the created records
            filters.setdefault('updated_at', {})
            filters['updated_at']['from'] = from_date.strftime(dt_fmt)
        if to_date is not None:
            filters.setdefault('updated_at', {})
            filters['updated_at']['to'] = to_date.strftime(dt_fmt)

        page = 0
        ids = []
        while True:
            page += 1
            r = self._call().get('%s?page=%s' % (self._woo_model, page))
            if r.json():
                for saleorder in r.json():
                    ids += [saleorder.get('id')]
            else:
                break
        return ids


class SaleOrderBatchImporter(Component):

    """ Import the WooCommerce Partners.

    For every partner in the list, a delayed job is created.
    """
    _inherit = ['woo.delayed.batch.importer']
    _name = 'woo.sale.batch.importer'
    _apply_on = ['woo.sale.order']

    def update_existing_order(self, woo_sale_order, record_id):
        """ Enter Your logic for Existing Sale Order """
        return True

    def run(self, filters=None):
        """ Run the synchronization """
        from_date = filters.pop('from_date', None)
        to_date = filters.pop('to_date', None)
        record_ids = self.backend_adapter.search(
            filters,
            from_date=from_date,
            to_date=to_date,
        )
        order_ids = []
        for record_id in record_ids:
            woo_sale_order = self.env['woo.sale.order'].search(
                [('woo_id', '=', record_id)])
            if woo_sale_order:
                self.update_existing_order(woo_sale_order[0], record_id)
            else:
                order_ids.append(record_id)
        _logger.info('search for woo partners %s returned %s',
                     filters, record_ids)
        for record_id in order_ids:
            self._import_record(record_id, priority=50)


class SaleOrderImporter(Component):
    _name = 'woo.sale.importer'
    _inherit = ['woo.importer']
    _apply_on = ['woo.sale.order']

    def _import_addresses(self):
        record = self.woo_record
        self._import_dependency(record['customer_id'],
                                'woo.res.partner')

    def _import_dependencies(self):
        """ Import the dependencies for the record"""
        record = self.woo_record

        self._import_addresses()
        record = record['items']
        for line in record:
            _logger.debug('line: %s', line)
            if 'product_id' in line:
                self._import_dependency(line['product_id'],
                                        'woo.product.product')

    def _clean_woo_items(self, resource):
        """
        Method that clean the sale order line given by WooCommerce before
        importing it

        This method has to stay here because it allow to customize the
        behavior of the sale order.

        """
        child_items = {}  # key is the parent item id
        top_items = []

        # Group the childs with their parent
        for item in resource['line_items']:
            if item.get('parent_item_id'):
                child_items.setdefault(item['parent_item_id'], []).append(item)
            else:
                top_items.append(item)

        all_items = []
        for top_item in top_items:
            all_items.append(top_item)
        resource['items'] = all_items
        return resource

    def _get_woo_data(self):
        """ Return the raw WooCommerce data for ``self.woo_id`` """
        record = super(SaleOrderImporter, self)._get_woo_data()
        # sometimes we need to clean woo items (ex : configurable
        # product in a sale)
        record = self._clean_woo_items(record)
        return record


class SaleOrderImportMapper(Component):
    _name = 'woo.sale.import.mapper'
    _inherit = ['base.import.mapper']
    _apply_on = 'woo.sale.order'

    children = [('items', 'woo_order_line_ids', 'woo.sale.order.line'),
                ]

    @mapping
    def status(self, rec):
        if rec:
            if rec['status']:
                status_id = self.env['woo.sale.order.status'].search(
                    [('name', '=', rec['status'])])
                if status_id:
                    return {'status_id': status_id[0].id}
                else:
                    status_id = self.env['woo.sale.order.status'].create({
                        'name': rec['status']
                    })
                    return {'status_id': status_id.id}
            else:
                return {'status_id': False}

    @mapping
    def customer_id(self, rec):
        if rec:
            binder = self.binder_for('woo.res.partner')
            if rec['customer_id']:
                partner_id = binder.to_openerp(rec['customer_id'],
                                               unwrap=True) or False
                assert partner_id, ("Please Check Customer Role in WooCommerce")
                result = {'partner_id': partner_id}
                onchange_val = self.env['sale.order'].onchange_partner_id(
                    partner_id)
                result.update(onchange_val['value'])
            else:
                customer = rec['billing']
                country_id = False
                state_id = False
                if customer['country']:
                    country_id = self.env['res.country'].search(
                        [('code', '=', customer['country'])])
                    if country_id:
                        country_id = country_id.id
                if customer['state']:
                    state_id = self.env['res.country.state'].search(
                        [('code', '=', customer['state'])])
                    if state_id:
                        state_id = state_id.ids[0]  # Todo: 可能是个隐患。
                name = customer['first_name'] + ' ' + customer['last_name']
                partner_dict = {
                    'name': name,
                    'city': customer['city'],
                    'phone': customer['phone'],
                    'zip': customer['postcode'],
                    'state_id': state_id,
                    'country_id': country_id
                }
                partner_id = self.env['res.partner'].create(partner_dict)
                partner_dict.update({
                    'backend_id': self.backend_record.id,
                    'openerp_id': partner_id.id,
                })
                result = {'partner_id': partner_id.id}
                # Todo: 可能是个隐患。
                # onchange_val = self.env['sale.order'].onchange_partner_id(partner_id.id)
                # result.update(onchange_val['value'])
            return result

    @mapping
    def backend_id(self, record):
        return {'backend_id': self.backend_record.id}


class SaleOrderLineExportMapper(Component):
    _name = 'woo.sale.line.export.mapper'
    _inherit = ['base.export.mapper']
    _apply_on = 'woo.sale.order.line'

    direct = [('quantity', 'product_uom_qty'),
              # ('quantity', 'product_uos_qty'),
              ('name', 'name'),
              ('price', 'price_unit')
              ]

    @mapping
    def product_id(self, record):
        binder = self.binder_for('woo.product.product')
        product_id = binder.to_openerp(record['product_id'], unwrap=True)
        assert product_id is not None, (
            "product_id %s should have been exported in "
            "SaleOrderExporter._export_dependencies" % record['product_id'])
        return {'product_id': product_id}


class SaleOrderBatchExporter(Component):

    """ export the WooCommerce Partners.

    For every partner in the list, a delayed job is created.
    """
    _inherit = ['woo.delayed.batch.exporter']
    _name = 'woo.sale.batch.exporter'
    _apply_on = ['woo.sale.order']

    def update_existing_order(self, woo_sale_order, record_id):
        """ Enter Your logic for Existing Sale Order """
        return True

    def run(self, filters=None):
        """ Run the synchronization """
        from_date = filters.pop('from_date', None)
        to_date = filters.pop('to_date', None)
        filters = []
        record_ids = self.model.openerp_id.search(filters).ids
        _logger.info('search for woo partners %s returned %s',
                     filters, record_ids)
        for record_id in record_ids:
            self._export_record(record_id, priority=50)


class SaleOrderExporter(Component):
    _name = 'woo.sale.exporter'
    _inherit = ['woo.exporter']
    _apply_on = ['woo.sale.order']

    def _export_addresses(self):
        record = self.odoo_record
        self._export_dependency(record.partner_id.id, 'woo.res.partner')

    def _export_dependencies(self):
        """ Export the dependencies for the record"""
        record = self.odoo_record

        self._export_addresses()
        record = record.order_line
        for line in record:
            _logger.debug('line: %s', line)
            if line.product_id:
                self._export_dependency(line.product_id.id, 'woo.product.product')

    def _clean_woo_items(self, resource):
        """
        Method that clean the sale order line given by WooCommerce before
        exporting it

        This method has to stay here because it allow to customize the
        behavior of the sale order.

        """
        child_items = {}  # key is the parent item id
        top_items = []

        # Group the childs with their parent
        for item in resource['line_items']:
            if item.get('parent_item_id'):
                child_items.setdefault(item['parent_item_id'], []).append(item)
            else:
                top_items.append(item)

        all_items = []
        for top_item in top_items:
            all_items.append(top_item)
        resource['items'] = all_items
        return resource

    def _get_woo_data(self):
        """ Return the raw WooCommerce data for ``self.woo_id`` """
        record = super(SaleOrderExporter, self)._get_woo_data()
        # sometimes we need to clean woo items (ex : configurable
        # product in a sale)
        record = self._clean_woo_items(record)
        return record


class SaleOrderExportMapper(Component):
    _name = 'woo.sale.export.mapper'
    _inherit = ['base.export.mapper']
    _apply_on = 'woo.sale.order'

    @mapping
    def line_items(self, rec):
        if rec:
            line_items = []
            binder = self.binder_for('woo.product.product')
            for line in rec.order_line:
                pass
                line_items.append({
                    'product_id': binder.to_backend(line.product_id.id, wrap=True),
                    'quantity': line.product_qty,
                    'total': str(line.price_subtotal),
                })

            return {'line_items': line_items}

    @mapping
    def customer_id(self, rec):
        if rec:
            binder = self.binder_for('woo.res.partner')
            if rec.partner_id:
                partner_id = binder.to_backend(rec.partner_id.id, wrap=True) or False
                assert partner_id, ("Please Check Customer Role in WooCommerce")
                return {'customer_id': partner_id}

    @mapping
    def backend_id(self, record):
        return {'backend_id': self.backend_record.id}

    @mapping
    def openerp_id(self, rec):
        return {'openerp_id': rec.id}