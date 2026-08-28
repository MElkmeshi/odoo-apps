import base64
import contextlib
import logging
import os
import tempfile

import requests
from werkzeug.urls import url_join

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

from odoo.addons.payment_onepay_ly import const


_logger = logging.getLogger(__name__)


class PaymentProvider(models.Model):
    _inherit = 'payment.provider'

    code = fields.Selection(
        selection_add=[(code, name) for code, name in const.ONEPAY_BRANDS.items()],
        ondelete={code: 'set default' for code in const.ONEPAY_CODES},
    )
    onepay_base_url = fields.Char(
        string="API Base URL",
        help="The root URL of the OnePay API. Test and production are different URLs.",
    )
    # The gateway expects these three as JSON numbers, not strings.
    onepay_user_id = fields.Integer(
        string="User ID",
        help="The sign-in user id provided by the gateway.",
    )
    onepay_pin = fields.Char(
        string="PIN",
        help="The sign-in PIN provided by the gateway.",
        groups='base.group_system',
    )
    onepay_provider_id = fields.Integer(
        string="Gateway Provider ID",
        help="The provider id to authenticate against, provided by the gateway.",
    )
    onepay_auth_user_type = fields.Integer(
        string="Auth User Type",
        help="The authentication user type expected by the gateway.",
        default=const.DEFAULT_AUTH_USER_TYPE,
    )
    onepay_signin_path = fields.Char(
        string="Sign-in Path", default=const.DEFAULT_SIGNIN_PATH,
    )
    onepay_init_path = fields.Char(
        string="Init Path", default=const.DEFAULT_INIT_PATH,
    )
    onepay_complete_path = fields.Char(
        string="Complete Path", default=const.DEFAULT_COMPLETE_PATH,
    )
    onepay_report_path = fields.Char(
        string="Report Path", default=const.DEFAULT_REPORT_PATH,
    )
    onepay_cert = fields.Binary(
        string="Client Certificate",
        help="PEM client certificate for mutual TLS. Only used when the provider is enabled "
             "(production); test transactions are sent over plain HTTPS. Stored in the database, "
             "so it is readable from a database dump or filestore backup.",
        groups='base.group_system',
    )
    onepay_cert_filename = fields.Char(groups='base.group_system')
    onepay_key = fields.Binary(
        string="Client Private Key",
        help="PEM private key matching the client certificate. Only used when the provider is "
             "enabled (production). Stored in the database, so it is readable from a database "
             "dump or filestore backup.",
        groups='base.group_system',
    )
    onepay_key_filename = fields.Char(groups='base.group_system')
    onepay_ca_bundle = fields.Binary(
        string="CA Bundle",
        help="PEM CA bundle used to verify the gateway's certificate. Only used when the "
             "provider is enabled (production).",
        groups='base.group_system',
    )
    onepay_ca_bundle_filename = fields.Char(groups='base.group_system')

    # === CONSTRAINT METHODS === #

    @api.constrains(
        'state', 'code', 'onepay_base_url', 'onepay_user_id', 'onepay_pin',
        'onepay_provider_id',
    )
    def _check_onepay_required_fields(self):
        """Require the gateway credentials on every OnePay brand.

        `payment`'s own `required_if_provider` compares against a single code,
        so it cannot cover the four brands this module registers. This does the
        same job for all of them.
        """
        # `onepay_auth_user_type` is absent on purpose: the gateway treats it as
        # 0 when unset, and 0 is falsy, so requiring it would reject a valid
        # configuration.
        required_fields = (
            'onepay_base_url', 'onepay_user_id', 'onepay_pin', 'onepay_provider_id',
        )
        for provider in self:
            if provider.code not in const.ONEPAY_CODES or provider.state not in ('enabled', 'test'):
                continue
            missing = [
                self.env['ir.model.fields']._get(self._name, name).field_description
                for name in required_fields
                if not provider.sudo()[name]
            ]
            if missing:
                raise ValidationError(
                    _("The following fields must be filled: %s", ", ".join(missing))
                )

    @api.constrains('onepay_cert', 'onepay_key', 'onepay_ca_bundle')
    def _check_onepay_pem_material(self):
        """Reject TLS material that is not PEM, at save time rather than at checkout."""
        for provider in self:
            if provider.code not in const.ONEPAY_CODES:
                continue
            for field_name, label in (
                ('onepay_cert', _("Client Certificate")),
                ('onepay_key', _("Client Private Key")),
                ('onepay_ca_bundle', _("CA Bundle")),
            ):
                blob = provider[field_name]
                if not blob:
                    continue
                try:
                    content = base64.b64decode(blob)
                except Exception:
                    raise ValidationError(
                        _("The %s could not be decoded.", label)
                    )
                if b'-----BEGIN' not in content:
                    raise ValidationError(
                        _("The %s is not in PEM format.", label)
                    )

    # === COMPUTE METHODS === #

    def _compute_feature_support_fields(self):
        """Override of `payment` to enable additional features."""
        super()._compute_feature_support_fields()
        self.filtered(lambda p: p.code in const.ONEPAY_CODES).update({
            'support_express_checkout': False,
            'support_manual_capture': False,
            'support_refund': False,
            'support_tokenization': False,
        })

    # === BUSINESS METHODS === #

    def _get_supported_currencies(self):
        """Override of `payment` to limit OnePay to the currencies it accepts."""
        supported_currencies = super()._get_supported_currencies()
        if self.code in const.ONEPAY_CODES:
            supported_currencies = supported_currencies.filtered(
                lambda c: c.name in const.SUPPORTED_CURRENCIES
            )
        return supported_currencies

    def _get_default_payment_method_codes(self):
        """Override of `payment` to return the default payment method codes."""
        default_codes = super()._get_default_payment_method_codes()
        if self.code not in const.ONEPAY_CODES:
            return default_codes
        return ['onepay_wallet']

    def _onepay_normalize_identity_card(self, identity_card):
        """Prepend the brand prefix to a short identity card number.

        Cards of 9 or more characters are already complete. Cards of exactly 7
        characters are missing the brand prefix. Anything else is passed
        through untouched and left for the gateway to reject.

        :param str identity_card: The identity card number as typed by the customer.
        :return: The normalized identity card number.
        :rtype: str
        """
        self.ensure_one()
        card = (identity_card or '').strip()
        if len(card) >= 9:
            return card
        if len(card) == 7:
            return const.BRAND_PREFIXES.get(self.code, '') + card
        return card

    @contextlib.contextmanager
    def _onepay_certificate_files(self):
        """Materialize the TLS material as temporary files for `requests`.

        The files are written with mode 0600 and removed in a `finally`, so no
        private key outlives a single request even if that request raises.

        Yields a ``(cert, verify)`` pair suitable for passing straight to
        `requests`. In any state other than `enabled` the TLS material is
        ignored entirely and ``(None, True)`` is yielded, so a test provider
        needs no certificate configured.

        :return: A context manager yielding the `cert` and `verify` arguments.
        """
        self.ensure_one()
        if self.state != 'enabled':
            yield None, True
            return

        paths = []

        def materialize(blob):
            if not blob:
                return None
            fd, path = tempfile.mkstemp(prefix='onepay-', suffix='.pem')
            try:
                os.write(fd, base64.b64decode(blob))
            finally:
                os.close(fd)
            os.chmod(path, 0o600)
            paths.append(path)
            return path

        try:
            provider_sudo = self.sudo()
            cert_path = materialize(provider_sudo.onepay_cert)
            key_path = materialize(provider_sudo.onepay_key)
            ca_path = materialize(provider_sudo.onepay_ca_bundle)

            if cert_path and key_path:
                cert = (cert_path, key_path)
            else:
                cert = cert_path  # None when no certificate is configured.
            yield cert, (ca_path or True)
        finally:
            for path in paths:
                try:
                    os.unlink(path)
                except OSError:
                    _logger.warning("Could not remove OnePay temporary file %s", path)

    def _onepay_make_request(self, path, payload=None, bearer=None):
        """Make a POST request to the OnePay API and return the parsed body.

        :param str path: The endpoint path, relative to the configured base URL.
        :param dict payload: The JSON request payload.
        :param str bearer: The bearer token to authenticate with, if any.
        :return: The parsed JSON response.
        :rtype: dict
        :raise ValidationError: If the gateway is unreachable or answers unusably.
        """
        self.ensure_one()

        url = url_join(self.onepay_base_url.rstrip('/') + '/', path.lstrip('/'))
        headers = {'Accept': 'application/json', 'Content-Type': 'application/json'}
        if bearer:
            headers['Authorization'] = f'Bearer {bearer}'

        try:
            with self._onepay_certificate_files() as (cert, verify):
                response = requests.post(
                    url, json=payload or {}, headers=headers, timeout=30,
                    cert=cert, verify=verify,
                )
            response.raise_for_status()
        except requests.exceptions.ConnectionError:
            _logger.exception("Unable to reach the OnePay API at %s", url)
            raise ValidationError(_("Could not establish a connection to the OnePay API."))
        except requests.exceptions.HTTPError:
            # The body can echo merchant credentials, so it is logged but never shown.
            _logger.exception("Invalid OnePay API request at %s", url)
            raise ValidationError(_("An error occurred when communicating with the OnePay API."))

        try:
            data = response.json()
        except ValueError:
            _logger.exception("OnePay response at %s was not JSON", url)
            raise ValidationError(_("The OnePay API returned an unreadable response."))

        if not isinstance(data, dict):
            raise ValidationError(_("The OnePay API returned an unreadable response."))
        return data

    def _onepay_get_error_message(self, data, default_message):
        """Extract the gateway's error text from a response, if it carries one.

        :param dict data: The parsed response.
        :param str default_message: The message to fall back on.
        :return: The error message to show the customer.
        :rtype: str
        """
        messages = data.get('messages')
        if isinstance(messages, list) and messages and isinstance(messages[0], str):
            return messages[0]
        return default_message

    def _onepay_sign_in(self):
        """Authenticate against the gateway and return a bearer token.

        :return: The bearer token.
        :rtype: str
        :raise ValidationError: If the gateway does not return a usable token.
        """
        self.ensure_one()

        provider_sudo = self.sudo()
        data = self._onepay_make_request(self.onepay_signin_path, {
            'userId': provider_sudo.onepay_user_id,
            'pin': provider_sudo.onepay_pin,
            'providerId': provider_sudo.onepay_provider_id,
            'authUserType': provider_sudo.onepay_auth_user_type,
        })

        content = data.get('content')
        if not isinstance(content, dict) or not content.get('value') or not content.get('validTo'):
            _logger.error("OnePay sign-in returned no token for provider %s", self.name)
            raise ValidationError(
                _("Could not authenticate with the OnePay API. Please contact support.")
            )
        return content['value']
