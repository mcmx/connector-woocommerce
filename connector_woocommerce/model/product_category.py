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
from odoo.addons.connector.exception import MappingError

from odoo import models, fields

_logger = logging.getLogger(__name__)


class WooProductCategory(models.Model):
    _name = 'woo.product.category'
    _inherit = 'woo.binding'
    _inherits = {'product.category': 'openerp_id'}
    _description = 'woo product category'

    _rec_name = 'name'

    openerp_id = fields.Many2one(comodel_name='product.category',
                                 string='category',
                                 required=True,
                                 ondelete='cascade')
    backend_id = fields.Many2one(
        comodel_name='wc.backend',
        string='Woo Backend',
        store=True,
        readonly=False,
    )

    slug = fields.Char('Slung Name')
    woo_parent_id = fields.Many2one(
        comodel_name='woo.product.category',
        string='Woo Parent Category',
        ondelete='cascade',)
    description = fields.Char('Description')
    count = fields.Integer('count')


class CategoryAdapter(Component):
    _inherit = ['woo.adapter']
    _name = 'woo.category.adapter'
    _woo_model = 'products/categories'
    _apply_on = 'woo.product.category'

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
            filters.setdefault('updated_at', {})
            filters['updated_at']['from'] = from_date.strftime(dt_fmt)
        if to_date is not None:
            filters.setdefault('updated_at', {})
            filters['updated_at']['to'] = to_date.strftime(dt_fmt)

        ids = []
        res = self._call(method='GET', endpoint=self._woo_model)
        for category in res:
            ids += [category.get('id')]
        return ids


class CategoryBatchImporter(Component):

    """ Import the WooCommerce Partners.

    For every partner in the list, a delayed job is created.
    """
    _inherit = ['woo.delayed.batch.importer']
    _name = 'woo.category.batch.importer'
    _apply_on = ['woo.product.category']

    def run(self, filters=None):
        """ Run the synchronization """
        from_date = filters.pop('from_date', None)
        to_date = filters.pop('to_date', None)
        record_ids = self.backend_adapter.search(
            filters,
            from_date=from_date,
            to_date=to_date,
        )
        _logger.info('search for woo Product Category %s returned %s',
                     filters, record_ids)
        for record_id in record_ids:
            self._import_record(record_id)


class ProductCategoryImporter(Component):
    _apply_on = ['woo.product.category']
    _name = 'woo.product.category.importer'
    _inherit = ['woo.importer']

    def _import_dependencies(self):
        """ Import the dependencies for the record"""
        record = self.woo_record
        # import parent category
        # the root category has a 0 parent_id
        if record['parent']:
            parent_id = record['parent']
            if self.binder.to_openerp(parent_id) is None:
                self.component(usage='record.importer').run(parent_id, force=False)
        return


class ProductCategoryImportMapper(Component):
    _apply_on = 'woo.product.category'
    _name = 'woo.category.import.mapper'
    _inherit = ['base.import.mapper']

    @mapping
    def name(self, rec):
        if rec:
            return {'name': rec['name']}

    @mapping
    def backend_id(self, record):
        return {'backend_id': self.backend_record.id}

    @mapping
    def parent_id(self, rec):
        if rec:
            if not rec['parent']:
                return
            binder = self.binder_for()
            category_id = binder.to_openerp(rec['parent'], unwrap=True)
            woo_cat_id = binder.to_openerp(rec['parent'])
            if category_id is None:
                raise MappingError("The product category with "
                                   "woo id %s is not imported." %
                                   rec['parent'])
            return {'parent_id': category_id, 'woo_parent_id': woo_cat_id}


class CategoryBatchExporter(Component):

    """ Import the WooCommerce Partners.

    For every partner in the list, a delayed job is created.
    """
    _inherit = ['woo.delayed.batch.exporter']
    _name = 'woo.category.batch.exporter'
    _apply_on = ['woo.product.category']

    def run(self, filters=None):
        """ Run the synchronization """
        from_date = filters.pop('from_date', None)
        to_date = filters.pop('to_date', None)
        if not filters:
            filters = []

        record_ids = self.model.openerp_id.search(filters).ids
        _logger.info('search for odoo Product Category %s returned %s',
                     filters, record_ids)
        for record_id in record_ids:
            self._export_record(record_id)


class ProductCategoryExporter(Component):
    _apply_on = ['woo.product.category']
    _name = 'woo.product.category.exporter'
    _inherit = ['woo.exporter']

    def _export_dependencies(self):
        """ Import the dependencies for the record"""
        record = self.odoo_record
        # export parent category
        # the root category has a 0 parent_id
        if record.parent_id:
            parent_id = record.parent_id.id
            if self.binder.to_openerp(parent_id) is None:
                # self.run(parent_id)
                self.component(usage='record.exporter').run(parent_id, force=False)
        return


class ProductCategoryExportMapper(Component):
    _apply_on = 'woo.product.category'
    _name = 'woo.category.export.mapper'
    _inherit = ['base.export.mapper']

    @mapping
    def name(self, rec):
        if rec:
            return {'name': rec['name']}

    @mapping
    def backend_id(self, record):
        return {'backend_id': self.backend_record.id}

    @mapping
    def parent_id(self, rec):
        if rec:
            if not rec.parent_id:
                return
            binder = self.binder_for()
            woo_id_parent = binder.to_backend(rec.parent_id.id, wrap=True).woo_id
            woo_parent_id = binder.to_openerp(external_id=woo_id_parent)

            return {'woo_id_parent': woo_id_parent, 'woo_parent_id': woo_parent_id}

    @mapping
    def openerp_id(self, rec):
        return {'openerp_id': rec.id}
