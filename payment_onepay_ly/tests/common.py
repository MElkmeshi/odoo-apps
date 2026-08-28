from odoo.addons.payment.tests.common import PaymentCommon


class OnePayCommon(PaymentCommon):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()

        cls.onepay = cls._prepare_provider('onepay', update_values={
            'onepay_base_url': 'https://gateway.test/YusorOnline',
            'onepay_user_id': 100589,
            'onepay_pin': '1234',
            'onepay_provider_id': 2050,
            'onepay_auth_user_type': 0,
        })
        cls.provider = cls.onepay
        cls.currency = cls._prepare_currency('LYD')

    @staticmethod
    def signin_response():
        return {'content': {'value': 'signin-bearer', 'validTo': '2030-01-01T00:00:00Z'}}

    @staticmethod
    def init_response():
        return {'content': {'value': 'session-bearer', 'validTo': '2030-01-01T00:00:00Z'}}
