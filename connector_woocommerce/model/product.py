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
import base64
import logging

import requests
from odoo.addons.component.core import Component
from odoo.addons.connector.components.mapper import mapping
from odoo.addons.connector.exception import MappingError

from odoo import models, fields

_logger = logging.getLogger(__name__)


class WooProductProduct(models.Model):
    _name = 'woo.product.product'
    _inherit = 'woo.binding'
    _inherits = {'product.product': 'openerp_id'}
    _description = 'woo product product'

    _rec_name = 'name'
    openerp_id = fields.Many2one(comodel_name='product.product',
                                 string='product',
                                 required=True,
                                 ondelete='cascade')
    backend_id = fields.Many2one(
        comodel_name='wc.backend',
        string='Woo Backend',
        store=True,
        readonly=False,
        required=True,
    )

    slug = fields.Char('Slung Name')
    credated_at = fields.Date('created_at')
    weight = fields.Float('weight')


class ProductProduct(models.Model):
    _inherit = 'product.product'

    woo_categ_ids = fields.Many2many(
        comodel_name='product.category',
        string='Woo product category',
    )
    in_stock = fields.Boolean('In Stock')


class ProductProductAdapter(Component):
    _apply_on = 'woo.product.product'
    _inherit = ['woo.adapter']
    _name = 'woo.pruduct.adapter'
    _woo_model = 'products'

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
                for product in r.json():
                    ids += [product.get('id')]
            else:
                break
        return ids

    def read_image(self, id, image_name, storeview_id=None):
        return self._call('products',
                          [int(id), image_name, storeview_id, 'id'])


class ProductBatchImporter(Component):
    """ Import the WooCommerce Partners.

    For every partner in the list, a delayed job is created.
    """
    _apply_on = ['woo.product.product']
    _inherit = ['woo.delayed.batch.importer']
    _name = 'woo.product.batch.importer'

    def run(self, filters=None):
        """ Run the synchronization """
        from_date = filters.pop('from_date', None)
        to_date = filters.pop('to_date', None)
        record_ids = self.backend_adapter.search(
            filters,
            from_date=from_date,
            to_date=to_date,
        )
        _logger.info('search for woo Products %s returned %s',
                     filters, record_ids)
        for record_id in record_ids:
            self._import_record(record_id, priority=30)


class ProductProductImporter(Component):
    _name = 'woo.product.product.importer'
    _inherit = ['woo.importer']
    _apply_on = ['woo.product.product']

    def _import_dependencies(self):
        """ Import the dependencies for the record"""
        record = self.woo_record
        for woo_category in record['categories']:
            self._import_dependency(woo_category.get('id'), 'woo.product.category')

    def _after_import(self, binding):
        """ Hook called at the end of the import """
        # image_importer = self.unit_for(ProductImageImporter)
        # image_importer.run(self.woo_id, binding.id)
        self.component(usage='image.importer').run(self.woo_record, binding.id)
        return


class ProductImageImporter(Component):
    """ Import images for a record.

    Usually called from importers, in ``_after_import``.
    For instance from the products importer.
    """
    _name = 'woo.product.image.importer'
    _inherit = ['base.importer']
    _usage = 'image.importer'

    def _sort_images(self, images):
        """ Returns a list of images sorted by their priority.
        An image with the 'image' type is the the primary one.
        The other images are sorted by their position.

        The returned list is reversed, the items at the end
        of the list have the higher priority.
        """
        if not images:
            return {}
        # place the images where the type is 'image' first then
        # sort them by the reverse priority (last item of the list has
        # the the higher priority)

    def _get_binary_image(self, image_data):
        url = image_data['src']
        return requests.get(url).content

    def run(self, woo_record, binding_id):
        images = woo_record.get('images')
        binary = None
        while not binary and images:
            binary = self._get_binary_image(images.pop())
        if not binary:
            return
        model = self.model.with_context(connector_no_export=True)
        binding = model.browse(binding_id)
        binding.write({'image': base64.b64encode(binary)})


class ProductProductImportMapper(Component):
    _name = 'woo.product.import.mapper'
    _inherit = ['base.import.mapper']
    _apply_on = 'woo.product.product'

    direct = [
        ('description', 'description'),
        ('weight', 'weight'),
    ]

    @mapping
    def in_stock(self, record):
        if record:
            return {'in_stock': record['in_stock']}

    @mapping
    def name(self, record):
        if record:
            return {'name': record['name']}

    @mapping
    def type(self, record):
        if record:
            if record['type'] == 'simple':
                return {'type': 'product'}

    @mapping
    def categories(self, record):
        if record:
            woo_categories = record['categories']
            binder = self.binder_for('woo.product.category')
            category_ids = []
            main_categ_id = None
            for woo_category in woo_categories:
                woo_category_id = woo_category.get('id')
                cat_id = binder.to_openerp(woo_category_id, unwrap=True)
                if cat_id is None:
                    raise MappingError("The product category with "
                                       "woo id %s is not imported." %
                                       woo_category_id)
                category_ids.append(cat_id)
            if category_ids:
                main_categ_id = category_ids.pop(0)
            result = {'woo_categ_ids': [(6, 0, category_ids)]}
            if main_categ_id:  # OpenERP assign 'All Products' if not specified
                result['categ_id'] = main_categ_id
            return result

    @mapping
    def price(self, record):
        """ The price is imported at the creation of
        the product, then it is only modified and exported
        from OpenERP """
        if record:
            return {'list_price': record and record['price'] or 0.0}

    @mapping
    def sale_price(self, record):
        """ The price is imported at the creation of
        the product, then it is only modified and exported
        from OpenERP """
        if record:
            return {'standard_price': record and record['sale_price'] or 0.0}

    @mapping
    def backend_id(self, record):
        return {'backend_id': self.backend_record.id}


class ProductBatchExporter(Component):
    """ Export the Odoo Products.

    For every Product in the list, a delayed job is created.
    """
    _apply_on = ['woo.product.product']
    _inherit = ['woo.delayed.batch.exporter']
    _name = 'woo.product.batch.exporter'

    def run(self, filters=None):
        """ Run the synchronization """
        from_date = filters.pop('from_date', None)
        to_date = filters.pop('to_date', None)
        if not filters:
            filters = []

        record_ids = self.model.openerp_id.search(filters).ids
        _logger.info('search for woo Products %s returned %s',
                     filters, record_ids)
        for record_id in record_ids:
            self._export_record(record_id, priority=30)


class ProductProductExporter(Component):
    _name = 'woo.product.product.exporter'
    _inherit = ['woo.exporter']
    _apply_on = ['woo.product.product']

    def _export_dependencies(self):
        """ Export the dependencies for the record"""
        record = self.odoo_record
        for odoo_category in record.categ_id:
            self._export_dependency(odoo_category.id, 'woo.product.category')


class ProductProductExportMapper(Component):
    _name = 'woo.product.export.mapper'
    _inherit = ['base.export.mapper']
    _apply_on = 'woo.product.product'

    @mapping
    def in_stock(self, record):
        if record:
            return {'in_stock': record.in_stock}

    @mapping
    def name(self, record):
        if record:
            return {'name': record.name}

    @mapping
    def categories(self, record):
        if record:
            odoo_categories = record.woo_categ_ids

            need_append = True
            for odoo_category in odoo_categories:
                if odoo_category.id == record.categ_id.id:
                    need_append = False
            if need_append:
                odoo_categories += record.categ_id

            binder = self.binder_for('woo.product.category')
            woo_category_ids = []
            for odoo_category in odoo_categories:
                odoo_category_id = odoo_category.id
                woo_category_id = binder.to_backend(odoo_category_id, wrap=True)
                if woo_category_id is None:
                    raise MappingError("The product category with "
                                       "odoo id %s is not exported." %
                                       odoo_category_id)
                woo_category_ids.append({'id': woo_category_id})

            result = {'categories': woo_category_ids}
            return result

    @mapping
    def price(self, record):
        """ The price is exported at the creation of
        the product, then it is only modified and imported
        to OpenERP """
        if record:
            return {'price': record and record.list_price or 0.0}

    @mapping
    def sale_price(self, record):
        """ The price is exported at the creation of
        the product, then it is only modified and exported
        from OpenERP """
        if record:
            return {'sale_price': record and str(record.standard_price) or '0.0'}

    @mapping
    def backend_id(self, record):
        return {'backend_id': self.backend_record.id}

    @mapping
    def openerp_id(self, rec):
        return {'openerp_id': rec.id}

    @mapping
    def image(self, record):
        """Todo"""
        return