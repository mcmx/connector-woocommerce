Odoo Connector WooCommerce Module
=================================
*Odoo WooCommerce Connector (also known as connector_woocommerce) is a bi-directional connector, compatible with the Odoo 11.0 and WooCommerce 2.6+).*

Forked from OCA/connector-woocommerce, which is unworkable after the **Odoo Connector** have been rewriter in the end of 2017.
I have no idea why the original module is inactive since March 28 2017.

Anyway, I modify the codes and this updated one is working now.

What's New
----------
#. Have been migrated to the new `Connector API <http://odoo-connector.com/guides/migration_guide.html#migration-guide-to-the-new-connector-api>`_
#. Have been migrated to the new `WooCommerce REST API <http://woocommerce.github.io/woocommerce-rest-api-docs>`_

   To use the latest version of the REST API you must be using:

   * WooCommerce 2.6+.
   * WordPress 4.4+.

Known Issues
------------
Can't Delay the *job* on Windows OS. Any asynchronous queue job will be executed synchronously, the monitor is unworkable as well.
Please refer to the maintainer's `statement <https://github.com/OCA/queue/issues/65#issuecomment-379763511>`_ of 'Odoo Queue Module'.