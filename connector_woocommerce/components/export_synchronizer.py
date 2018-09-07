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
import platform

from odoo.addons.component.core import AbstractComponent
from odoo.addons.connector.exception import IDMissingInBackend

from odoo import fields, _

_logger = logging.getLogger(__name__)


class WooExporter(AbstractComponent):
    """ Base exporter for WooCommerce """

    _name = 'woo.exporter'
    _inherit = ['base.exporter']
    _usage = 'record.exporter'

    def __init__(self, connector_env):
        """
        :param connector_env: current environment (backend, session, ...)
        :type connector_env: :class:`connector.connector.ConnectorEnvironment`
        """
        super(WooExporter, self).__init__(connector_env)
        self.odoo_id = None
        self.odoo_record = None

    def _get_odoo_data(self):
        """ Return the raw Odoo data for ``self.odoo_id`` """
        return self.model.openerp_id.browse([self.odoo_id])

    def _before_export(self):
        """ Hook called before the export, when we have the Odoo
        data"""

    def _is_uptodate(self, binding):
        """Not all Woo model data grab from Woo API have the modify date,
        so it's unnecessary to coding a common func in there."""
        return False

    def _export_dependency(self, odoo_id, binding_model,
                           exporter_class=None, always=False):
        """ Export a dependency.

        The exporter class is a class or subclass of
        :class:`WooExporter`. A specific class can be defined.

        :param odoo_id: id of the related binding to export
        :param binding_model: name of the binding model for the relation
        :type binding_model: str | unicode
        :param exporter_cls: :class:`openerp.addons.connector.\
                                     connector.ConnectorUnit`
                             class or parent class to use for the export.
                             By default: WooExporter
        :type exporter_cls: :class:`openerp.addons.connector.\
                                    connector.MetaConnectorUnit`
        :param always: if True, the record is updated even if it already
                       exists, note that it is still skipped if it has
                       not been modified on Odoo since the last update.
                       When False, it will export it only when it does not
                       yet exist.
        :type always: boolean
        """
        if not odoo_id:
            return
        if exporter_class is None:
            exporter_class = self._usage
        binder = self.binder_for(binding_model)
        if always or binder.to_backend(odoo_id, wrap=True) is None:
            exporter = self.component(usage=exporter_class, model_name=binding_model)
            exporter.run(odoo_id)

    def _export_dependencies(self):
        """ Export the dependencies for the record

        Export of dependencies can be done manually or by calling
        :meth:`_export_dependency` for each dependency.
        """
        return

    def _map_data(self):
        """ Returns an instance of
        :py:class:`~openerp.addons.connector.components.mapper.MapRecord`

        """
        return self.mapper.map_record(self.odoo_record)

    def _validate_data(self, data):
        """ Check if the values to export are correct

        Pro-actively check before the ``_create`` or
        ``_update`` if some fields are missing or invalid.

        Raise `InvalidDataError`
        """
        return

    def _must_skip(self):
        """ Hook called right after we read the data from the odoo.

        If the method returns a message giving a reason for the
        skipping, the export will be interrupted and the message
        recorded in the job (if the export is called directly by the
        job, not by dependencies).

        If it returns None, the export will continue normally.

        :returns: None | str | unicode
        """
        return

    def _get_woo_id(self):
        return self.binder.to_backend(self.odoo_id, wrap=True)

    def _create_data(self, map_record, **kwargs):
        return map_record.values(for_create=True, **kwargs)

    def _create(self, data):
        """ Create the Woo record """
        # special check on data before export
        self._validate_data(data)
        model = self.model.with_context(connector_no_export=True)
        model = str(model).split('()')[0]
        binding = self.env[model].create(data)
        _logger.debug('%d created from woo %s', binding, self.odoo_id)
        return binding

    def _update_data(self, map_record, **kwargs):
        return map_record.values(**kwargs)

    def _update(self, binding, data):
        """ Update an Woo record """
        # special check on data before export
        self._validate_data(data)
        json = self.backend_adapter.write(binding, data)
        _logger.debug('%d updated from odoo %s', binding, self.odoo_id)
        return

    def _after_export(self, binding):
        """ Hook called at the end of the export """
        return

    def run(self, odoo_id, force=False):
        """ Run the synchronization

        :param odoo_id: identifier of the record on odooCommerce
        """
        self.odoo_id = odoo_id
        try:
            self.odoo_record = self._get_odoo_data()
        except IDMissingInBackend:
            return _('Record does no longer exist in Odoo')

        skip = self._must_skip()
        if skip:
            return skip

        woo_id = self._get_woo_id()
        if not force and self._is_uptodate(woo_id):
            return _('Already up-to-date.')
        self._before_export()

        # export the missing linked resources
        self._export_dependencies()

        map_record = self._map_data()

        if woo_id:
            record = self._update_data(map_record)
            self._update(woo_id, record)
        else:
            record = self._create_data(map_record)
            woo_id = self.backend_adapter.create(record).get('id')
            self.binder.bind(woo_id, self._create(record))

        self._after_export(woo_id)


class BatchExporter(AbstractComponent):

    """ The role of a BatchExporter is to search for a list of
    items to export, then it can either export them directly or delay
    the export of each item separately.
    """
    
    _name = 'woo.batch.exporter'
    _usage = 'batch.exporter'
    _inherit = ['base.exporter']

    def run(self, filters=None):
        """ Run the synchronization """
        record_ids = self.backend_adapter.search(filters)
        for record_id in record_ids:
            self._export_record(record_id)

    def _export_record(self, record_id):
        """ Export a record directly or delay the Export of the record.

        Method to implement in sub-classes.
        """
        raise NotImplementedError


class DelayedBatchExporter(AbstractComponent):

    """ Delay export of the records """
    _inherit = 'woo.batch.exporter'
    _name = 'woo.delayed.batch.exporter'

    def _export_record(self, record_id, **kwargs):
        """ Delay the export of the records"""
        if platform.system() == 'Linux':
            self.model.with_delay().export_record(self.backend_record, record_id)
        else:
            self.model.export_record(self.backend_record, record_id)