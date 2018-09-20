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
import socket

from odoo.addons.component.core import AbstractComponent
from odoo.addons.connector.exception import NetworkRetryableError, RetryableJobError
from woocommerce import API

try:
    from xmlrpc import client as xmlrpclib
except ImportError:
    import xmlrpclib

_logger = logging.getLogger(__name__)

recorder = {}


def call_to_key(method, arguments):
    """ Used to 'freeze' the method and arguments of a call to WooCommerce
    so they can be hashable; they will be stored in a dict.

    Used in both the recorder and the tests.
    """
    def freeze(arg):
        if isinstance(arg, dict):
            items = dict((key, freeze(value)) for key, value
                         in arg.iteritems())
            return frozenset(items.iteritems())
        elif isinstance(arg, list):
            return tuple([freeze(item) for item in arg])
        else:
            return arg

    new_args = []
    for arg in arguments:
        new_args.append(freeze(arg))
    return (method, tuple(new_args))


def record(method, arguments, result):
    """ Utility function which can be used to record test data
    during synchronisations. Call it from WooCRUDAdapter._call

    Then ``output_recorder`` can be used to write the data recorded
    to a file.
    """
    recorder[call_to_key(method, arguments)] = result


def output_recorder(filename):
    import pprint
    with open(filename, 'w') as f:
        pprint.pprint(recorder, f)
    _logger.debug('recorder written to file %s', filename)


class WooLocation(object):

    def __init__(self, location, consumer_key, consumre_secret, version):
        self._location = location
        self.consumer_key = consumer_key
        self.consumer_secret = consumre_secret
        self.version = version

    @property
    def location(self):
        location = self._location
        return location


class WooCRUDAdapter(AbstractComponent):
    """ External Records Adapter for woo """

    _name = 'woo.crud.adapter'
    _inherit = ['base.backend.adapter']
    _usage = 'backend.adapter'

    def __init__(self, connector_env):
        """

        :param connector_env: current environment (backend, session, ...)
        :type connector_env: :class:`connector.connector.ConnectorEnvironment`
        """
        super(WooCRUDAdapter, self).__init__(connector_env)
        backend = self.backend_record
        woo = WooLocation(
            backend.location,
            backend.consumer_key,
            backend.consumer_secret,
            backend.version
        )
        self.woo = woo

    def search(self, filters=None):
        """ Search records according to some criterias
        and returns a list of ids """
        raise NotImplementedError

    def read(self, id, attributes=None):
        """ Returns the information of a record """
        raise NotImplementedError

    def search_read(self, filters=None):
        """ Search records according to some criterias
        and returns their information"""
        raise NotImplementedError

    def create(self, data):
        """ Create a record on the external system """
        raise NotImplementedError

    def write(self, id, data):
        """ Update records on the external system """
        raise NotImplementedError

    def delete(self, id):
        """ Delete a record on the external system """
        raise NotImplementedError

    def _call(self, method, endpoint, data=None):
        try:
            api = API(
                url=self.woo.location,
                consumer_key=self.woo.consumer_key,
                consumer_secret=self.woo.consumer_secret,
                version=self.woo.version,
                wp_api=True,
                timeout=None,
            )
            if api:
                if method == 'GET':
                    r = api.get(endpoint)
                elif method == 'POST':
                    r = api.post(endpoint, data)
                elif method == 'PUT':
                    r = api.put(endpoint, data)

                if r.status_code in [200, 201]:
                    res = r.json()
                    _logger.info('%s: %s' % (endpoint, res))
                    return r.json()
                else:
                    code = r.json().get('code')
                    message = r.json().get('message')
                    _logger.info('%s: %s, %s' % (endpoint, code, message))
                    err_res = {'id': None}
                    if 'customers' in endpoint:
                        if code == 'registration-error-email-exists' and method == 'POST':
                            return self._call(method='GET', endpoint='customers?search=%s' % data.get('email'))[0]
                        elif code == 'registration-error-invalid-email':
                            return err_res
                        elif code == 'rest_missing_callback_param':
                            return err_res
                        elif code == 'woocommerce_rest_invalid_id':
                            return err_res
                    elif 'products/categories' in endpoint:
                        if code == 'term_exists' and method == 'POST':
                            items = []
                            for item in self._call(method='GET', endpoint='products/categories?search=%s' % data.get('name')):
                                if item.get('name') == data.get('name') and data.get('parent', 0) == item.get('parent'):
                                    items.append(item)

                            return items[0]
                        elif code == 'woocommerce_rest_term_invalid' and message == 'Resource does not exist.':
                            return err_res
                    elif 'products' in endpoint:
                        if code == 'woocommerce_rest_product_invalid_id':
                            return err_res
                    elif 'orders' in endpoint:
                        if code == 'woocommerce_rest_shop_order_invalid_id':
                            return err_res


        except (socket.gaierror, socket.error, socket.timeout) as err:
            raise NetworkRetryableError(
                'A network error caused the failure of the job: '
                '%s' % err)
        except xmlrpclib.ProtocolError as err:
            if err.errcode in [502,   # Bad gateway
                               503,   # Service unavailable
                               504]:  # Gateway timeout
                raise RetryableJobError(
                    'A protocol error caused the failure of the job:\n'
                    'URL: %s\n'
                    'HTTP/HTTPS headers: %s\n'
                    'Error code: %d\n'
                    'Error message: %s\n' %
                    (err.url, err.headers, err.errcode, err.errmsg))
            else:
                raise


class GenericAdapter(AbstractComponent):
    _name = 'woo.adapter'
    _inherit = ['woo.crud.adapter']

    def search(self, filters=None):
        """ Search records according to some criterias
        and returns a list of ids

        :rtype: list
        """
        _logger.info(u'如果调用，肯定报错。')
        return self._call('%s.search' % self._woo_model,
                          [filters] if filters else [{}])

    def read(self, id, attributes=None):
        """ Returns the information of a record

        :rtype: dict
        """
        arguments = []
        if attributes:
            # Avoid to pass Null values in attributes. Workaround for
            # is not installed, calling info() with None in attributes
            # would return a wrong result (almost empty list of
            # attributes). The right correction is to install the
            # compatibility patch on WooCommerce.
            arguments.append(attributes)
        res = self._call(method='GET', endpoint='%s/' % self._woo_model + str(id))
        return res

    def search_read(self, filters=None):
        """ Search records according to some criterias
        and returns their information"""
        return self._call('%s.list' % self._woo_model, [filters])

    def create(self, data):
        """ Create a record on the external system """
        if data.get('woo_id_parent', None):
            data['parent'] = data.get('woo_id_parent')
            del data['woo_id_parent']

        res = self._call(method='POST', endpoint='%s' % self._woo_model, data=data)
        return res

    def write(self, id, data):
        """ Update records on the external system """
        res = self._call(method='PUT', endpoint='%s/%s' % (self._woo_model, int(id)), data=data)
        return res

    def delete(self, id):
        """ Delete a record on the external system """
        return self._call('%s.delete' % self._woo_model, [int(id)])
