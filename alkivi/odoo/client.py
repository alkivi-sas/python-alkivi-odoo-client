"""
OpenERP wrapper that use clientlib
"""

import io
import odoorpc
import logging
import re
import uuid

import email.generator
import email.mime.multipart
import email.message

from .config import config

TAX_DIFFERENCE_WARNING = 0.80


class Client(object):
    """Simple wrapper that use clientlib."""

    def __init__(self, endpoint=None, protocol=None, port=None, url=None,
                 version=None, db=None, user=None, password=None,
                 config_file=None, logger=None):
        """
        Creates a new Client.

        If any of ``endpoint``, ``protocol``, ``port``
        or ``url`` is not provided, this client will attempt to locate
        from them from environment, ~/.odoo.cfg or /etc/odoo.cfg.
        """
        # Create logger
        if logger:
            self.logger = logger
        else:
            self.logger = logging.getLogger(__name__)

        # Load a custom config file if requested
        if config_file is not None:
            config.read(config_file)

        # load endpoint
        if endpoint is None:
            endpoint = config.get('default', 'endpoint')

        # load data
        if protocol is None:
            protocol = config.get(endpoint, 'protocol')

        if port is None:
            port = config.get(endpoint, 'port')

        if url is None:
            url = config.get(endpoint, 'url')

        if db is None:
            db = config.get(endpoint, 'db')
        self.db = db

        if user is None:
            user = config.get(endpoint, 'user')
        self.user = user

        if password is None:
            password = config.get(endpoint, 'password')
        self.password = password

        # First login and keep uid
        self.logger.debug('Attempting to connect to {0} using {1}'.format(
            url,
            protocol))
        self.client = odoorpc.ODOO(url, port=port, protocol=protocol)
        self.initialized = False

        # Create cache for product and taxes
        self.products_cache = {}
        self.taxes_cache = {}

    def login(self):
        """Login."""
        self.client.login(self.db, self.user, self.password)
        self.initialized = True

    def execute(self, *args, **kwargs):
        """Wrapper for clientlib call."""
        if not self.initialized:
            self.login()
        return self.client.execute(*args, **kwargs)

    def get(self, model):
        """Wrapper for clientlib call."""
        if not self.initialized:
            self.login()
        return self.client.env[model]

    def read(self, *args, **kwargs):
        """Wrapper for clientlib call."""
        if not self.initialized:
            self.login()
        return self.client.read(*args, **kwargs)

    def search(self, model, data):
        """Wrapper for clientlib call."""
        if not self.initialized:
            self.login()

        env = self.client.env[model]
        return env.search(data)

    def create(self, model, data):
        """Wrapper for clientlib call."""
        if not self.initialized:
            self.login()

        env = self.client.env[model]
        return env.create(data)

    def browse(self, model, ids):
        """Wrapper for clientlib call."""
        if not self.initialized:
            self.login()

        env = self.client.env[model]
        return env.browse(ids)

    def exec_workflow(self, model, signal, record_id):
        """Wrapper for clientlib call."""
        if not self.initialized:
            self.login()
        return self.client.exec_workflow(model, record_id, signal)

    def upload_attachment(self, data):
        """Wrapper to upload some data to odoo."""

        # Remove data from the payload creation
        db_datas = data['db_datas']
        del data['db_datas']

        # Create env
        #@env = self.client.env['ir.attachment']
        #import_id = env.create(data)

        # Upload file
        login_data = self.client.json(
                '/web/session/authenticate',
                {'db': self.db,
                 'login': self.user,
                 'password': self.password})
        session_id = login_data['result']['session_id']

        boundary = '----odoo-import-{}'.format(uuid.uuid4())
        mime_msg = email.mime.multipart.MIMEMultipart(boundary=boundary)

        sess_id_msg = email.message.Message()
        sess_id_msg.set_payload(str(session_id))
        sess_id_msg.add_header('Content-Disposition', 'form-data',
                            name='session_id')
        mime_msg.attach(sess_id_msg)

        import_id_msg = email.message.Message()
        import_id_msg.set_payload(str(data['res_model']))
        import_id_msg.add_header('Content-Disposition', 'form-data',
                                name='model')
        mime_msg.attach(import_id_msg)

        import_id_msg = email.message.Message()
        import_id_msg.set_payload(str(data['res_id']))
        import_id_msg.add_header('Content-Disposition', 'form-data',
                                name='id')
        mime_msg.attach(import_id_msg)

        import_id_msg = email.message.Message()
        import_id_msg.set_payload('oe_fileupload31')
        import_id_msg.add_header('Content-Disposition', 'form-data',
                                name='callback')
        mime_msg.attach(import_id_msg)


        file_msg = email.message.Message()
        file_msg.set_payload(db_datas)
        file_msg.add_header('Content-Disposition', 'form-data', name='ufile',
                            filename=data['name'])
        file_msg.add_header('Content-Type', data['file_type'])
        mime_msg.attach(file_msg)

        outio = io.StringIO()
        generator = email.generator.Generator(outio)
        generator.flatten(mime_msg)

        msg = outio.getvalue()
        msg = '\n\n'.join(msg.split('\n\n')[1:])  # Remove headers

        headers = {
            'Content-Type': 'multipart/form-data; boundary="{}"'.format(boundary),
            'MIME-Version': '1.0',
        }
        #self.client.http('web/binary/upload_attachment', data=msg.encode('utf-8'),
        self.client.http('web/binary/upload_attachment', data=msg,
                headers=headers)


    def fetch_product(self, vat_index):
        """Fetch product object in openerp and store into cash to avoid repetition

        Fetch product with name Produits et Services %s (20 19,6 ...)
        """

        # Do we have cache ?
        if vat_index in self.products_cache:
            return self.products_cache[vat_index]

        # Fetch associated tax
        tax = self.fetch_tax(vat_index)

        if tax is None:
            text = '0'
        else:
            text = tax.amount * 100
            if text == int(text):
                text = '%2d' % int(text)
            else:
                text = '%2.1f' % text

        description = 'Produits et Services %s' % text
        description = ','.join(re.split('\.', description))

        search_args = [('name_template', 'ilike', description)]
        product_ids = self.search('product.product', search_args)

        if not product_ids:
            raise Exception('%s is missing in product.product' % description)
        elif len(product_ids) > 1:
            self.logger.warning('Got several ids', product_ids)
            raise Exception('More than one product %s' % description)

        product_id = product_ids[0]
        product = self.browse('product.product', product_id)

        # Update cache
        self.products_cache[vat_index] = product

        return product

    def fetch_tax(self, vat_index):
        """Fetch tax object in openerp and store into cash to avoid repetition

        default is fetch from openerp configuration
        other tax 19.6, 20, are fetch using ACH-20 ...
        0 mean no tax so return None
        """

        # Do we have cache ?
        if vat_index in self.taxes_cache:
            return self.taxes_cache[vat_index]

        # Fetch default value in openerp
        tax_id = None

        if vat_index == 'default':
            tax_ids = self.execute('ir.values',
                                   'get_default',
                                   'product.product',
                                   'supplier_taxes_id',
                                   True,
                                   1,
                                   False)
            tax_id = tax_ids[0]
        elif float(vat_index) == float(0):
            return None
        else:
            search_args = [('description', '=', 'ACH-%s' % vat_index)]
            tax_ids = self.search('account.tax', search_args)
            if not tax_ids:
                raise Exception('tax %s is missing in account.tax' % vat_index)
            elif len(tax_ids) > 1:
                self.logger.warning('Got several ids', tax_ids)
                raise Exception('More than one tax with description ' +
                                '{0}'.format(vat_index))
            tax_id = tax_ids[0]

        # Check that configuration is correct
        if tax_id is None:
            raise Exception('We should have tax_id here')

        tax = self.browse('account.tax', tax_id)

        # Update cache
        self.taxes_cache[vat_index] = tax

        return tax

    def fetch_account(self, code):
        """Return openerp account.account using code to search

        """

        search_args = [('code', '=', code)]
        account_ids = self.search('account.account', search_args)

        if not account_ids:
            raise Exception('Account %s not found' % code)
        elif len(account_ids) > 1:
            raise Exception('Found multiple accounts with code' +
                            '{0}'.format(code))

        return self.browse('account.account', account_ids[0])

    def fetch_partner(self, name, customer=False, supplier=False):
        """Return openerp res.partner using name to search it

        First try exact name, if no match then like
        """

        search_args = [('name', '=', name)]

        if customer:
            search_args.append(('customer', '=', 1))

        if supplier:
            search_args.append(('supplier', '=', 1))

        customer_ids = self.search('res.partner', search_args)
        if not customer_ids:
            search_args.pop(0)
            search_args.append(('name', 'ilike', name))
            customer_ids = self.search('res.partner', search_args)

        if not customer_ids:
            raise Exception('Supplier %s not found' % name)
        elif len(customer_ids) > 1:
            raise Exception('Found multiple customers with name %s' % name)

        return self.browse('res.partner', customer_ids[0])

    def fetch_customer(self, name):
        """Return openerp res.partner using name to search it

        First try exact name, if no match then like
        """
        return self.fetch_partner(name=name, customer=True)

    def fetch_supplier(self, name):
        """Return openerp res.partner using name to search it

        First try exact name, if no match then like
        """
        return self.fetch_partner(name=name, supplier=True)

    def create_invoice(self, invoice_data, lines_data, attachment_data=None,
                       state='draft', tax_amount=None):
        """Global method that create an invoice and add lines to ir

        invoice_data : dict with  necessary information to create invoice
        lines_data : array with all lines data
        state : draft or open
        tax_check : TODO
        """

        if not invoice_data:
            raise Exception('Missing invoice_data')
        if not lines_data:
            raise Exception('Missing lines_data')
        if state not in ('draft', 'open'):
            raise Exception('State %s is not valid' % state)

        # Create invoice
        self.logger.debug('going to create invoice with', invoice_data)
        invoice_id = self.create('account.invoice', invoice_data)
        self.logger.debug('created invoice %d' % invoice_id)

        # Create invoice_line
        for line_data in lines_data:
            line_data['invoice_id'] = invoice_id
            self.logger.debug('going to create invoice_line with', line_data)
            invoice_line_id = self.create('account.invoice.line', line_data)
            self.logger.debug('created invoice.line %d' % invoice_line_id)

        # Compute taxes
        result = self.execute('account.invoice',
                              'button_reset_taxes',
                              [invoice_id])
        if not result:
            raise Exception('Unable to compute taxes, WTF')

        # If tax_amount, check that taxes match
        if tax_amount:
            invoice = self.browse('account.invoice', invoice_id)
            tax_lines = invoice.tax_line

            # Check that we have only one tax line
            number_of_tax_lines = 0

            for tax_line in tax_lines:
                number_of_tax_lines += 1
                self.logger.debug('tax_line data', tax_line._values)

            if number_of_tax_lines == 0:
                raise Exception('No tax yet, we should have')

            if number_of_tax_lines != 1:
                # If vat_amount is present in ALL lines_data
                # fix amount if necessary
                should_fix_vat = True
                vat_data_to_fix = {}
                for line_data in lines_data:
                    if 'vat_amount' not in line_data:
                        should_fix_vat = False
                        break
                    else:
                        tax_test = line_data['invoice_line_tax_id']
                        if len(tax_test) != 1:
                            self.logger.debug('I wont check tax, this is weird',
                                          tax_test)
                            should_fix_vat = False
                            break
                        # Weird tuple due to fields.Many2many in openerp
                        t1, t2, t3 = tax_test[0]
                        if len(t3) != 1:
                            self.logger.debug('I wont check tax, this is weird2',
                                          t3)
                            should_fix_vat = False
                            break
                        tax_id = t3[0]
                        # With this tax_id, fetch the tax_code_id
                        tax = self.browse('account.tax', tax_id)
                        if not tax:
                            self.logger.warning('Unable to fetch account.tax ' +
                                            '{0}'.format(tax_id))
                            should_fix_vat = False
                            break
                        tax_code = tax.tax_code_id
                        vat_data_to_fix[tax_code.id] = line_data['vat_amount']

                if should_fix_vat:
                    self.logger.debug('Checking vat with', vat_data_to_fix)
                    all_is_correct = True
                    for tax_line in invoice.tax_line:
                        tax_code_id = tax_line.tax_code_id.id
                        if tax_code_id not in vat_data_to_fix:
                            self.logger.warning('Trying to fix tax not OK ????',
                                            tax_code_id,
                                            vat_data_to_fix)
                            all_is_correct = False
                            break
                    if all_is_correct:
                        for tax_line in invoice.tax_line:
                            tax_code_id = tax_line.tax_code_id.id
                            correct_amount = vat_data_to_fix[tax_code_id]
                            if tax_line.amount != correct_amount:
                                message = 'Fix tax_line amount ' +\
                                          'from {0}'.format(tax_line.amount) +\
                                          ' to {0}'.format(correct_amount)
                                abs_amount = abs(tax_line.amount -
                                                 correct_amount)
                                if abs_amount > TAX_DIFFERENCE_WARNING:
                                    self.logger.warning(message)
                                else:
                                    self.logger.info(message)
                                tax_line.amount = correct_amount

                else:
                    self.logger.info('We have multiple lines with tax, ' +
                                 'skipping integrity check')
                    if state != 'draft':
                        self.logger.warning('But forcing state draft')
                        state = 'draft'
            else:
                # Fix amount, might be wrong usually one cents wrong
                if tax_line.amount != tax_amount:
                    message = 'Fix tax_line amount ' +\
                              'from {0} '.format(tax_line.amount) +\
                              'to {0}'.format(tax_amount)
                    abs_amount = abs(tax_line.amount -
                                     tax_amount)
                    if abs_amount > TAX_DIFFERENCE_WARNING:
                        self.logger.warning(message)
                    else:
                        self.logger.info(message)

                    # Update invoice : need to check parameters
                    tax_line.amount = tax_amount
                    self.logger.info('tax_line updated')

        if state == 'open':
            self.logger.debug('going to execute workflow invoice_open')
            self.exec_workflow('account.invoice', 'invoice_open', invoice_id)

        if attachment_data:
            self.logger.debug('going to attach some data to invoice')

            invoice = self.browse('account.invoice', invoice_id)
            attachment_data['res_id'] = invoice.id
            if invoice.number:
                attachment_data['res_name'] = invoice.number

            attachment_id = self.create('ir.attachment', attachment_data)
            self.logger.debug('attached file ' +
                              '{0}'.format(attachment_data['name']) +
                              ' to invoice, id={0}'.format(attachment_id))

        return invoice_id
