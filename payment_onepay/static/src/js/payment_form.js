/** @odoo-module **/

import { _t } from '@web/core/l10n/translation';
import { rpc } from '@web/core/network/rpc';
import paymentForm from '@payment/js/payment_form';

const ONEPAY_CODES = ['onepay', 'musrefy_pay', 'yussor_online', 'sahara_pay'];

paymentForm.include({

    /**
     * Force the direct flow so the OTP exchange runs on this page.
     *
     * @override
     */
    async _prepareInlineForm(providerId, providerCode, paymentOptionId, paymentMethodCode, flow) {
        if (!ONEPAY_CODES.includes(providerCode)) {
            return this._super(...arguments);
        }
        this._setPaymentFlow('direct');
    },

    /**
     * Run the two-phase OTP exchange.
     *
     * The transaction already exists at this point; phase one asks the gateway
     * to send the OTP, phase two spends it.
     *
     * @override
     */
    async _processDirectFlow(providerCode, paymentOptionId, paymentMethodCode, processingValues) {
        if (!ONEPAY_CODES.includes(providerCode)) {
            return this._super(...arguments);
        }

        const form = this._onepayGetForm();
        if (!form) {
            this._displayErrorDialog(_t("Payment processing failed"));
            return;
        }

        const identityCard = form.querySelector('[name="o_onepay_identity_card"]').value.trim();
        if (!identityCard) {
            this._onepayShowError(form, _t("Please enter your identity card number."));
            this._enableButton();
            return;
        }

        this._onepayHideError(form);
        const result = await rpc('/payment/onepay/init', {
            reference: processingValues.reference,
            identity_card: identityCard,
        });

        if (result.error) {
            // The transaction is still draft, so the customer can correct and retry.
            this._onepayShowError(form, result.error);
            this._enableButton();
            return;
        }

        this._onepayShowOtpStep(form, result.otp_length, processingValues.reference);
    },

    /**
     * Swap the inline form to the OTP step and wire its confirm button.
     *
     * @private
     * @param {HTMLElement} form - The OnePay inline form.
     * @param {number} otpLength - The expected length of the OTP.
     * @param {string} reference - The transaction reference.
     * @return {void}
     */
    _onepayShowOtpStep(form, otpLength, reference) {
        form.querySelector('[name="o_onepay_identity_step"]').classList.add('d-none');

        const otpStep = form.querySelector('[name="o_onepay_otp_step"]');
        otpStep.classList.remove('d-none');

        const otpInput = otpStep.querySelector('[name="o_onepay_otp"]');
        otpInput.setAttribute('maxlength', otpLength);
        otpInput.focus();

        // The generic submit button no longer applies: this step has its own.
        this._hideInputs();

        const confirmButton = otpStep.querySelector('[name="o_onepay_confirm_button"]');
        confirmButton.addEventListener('click', async () => {
            const otp = otpInput.value.trim();
            if (!otp) {
                this._onepayShowError(form, _t("Please enter the one-time password."));
                return;
            }

            confirmButton.disabled = true;
            this._onepayHideError(form);
            const result = await rpc('/payment/onepay/confirm', { reference, otp });

            if (result.error) {
                this._onepayShowError(form, result.error);
                confirmButton.disabled = false;
                return;
            }
            window.location = result.redirect_url;
        });
    },

    /**
     * @private
     * @return {HTMLElement|null} The inline form of the selected payment option.
     */
    _onepayGetForm() {
        const checkedRadio = this.el.querySelector('input[name="o_payment_radio"]:checked');
        if (!checkedRadio) {
            return null;
        }
        return this._getInlineForm(checkedRadio)?.querySelector('[name="o_onepay_form"]') ?? null;
    },

    /**
     * @private
     * @param {HTMLElement} form - The OnePay inline form.
     * @param {string} message - The message to display.
     * @return {void}
     */
    _onepayShowError(form, message) {
        const errorEl = form.querySelector('[name="o_onepay_error"]');
        errorEl.textContent = message;
        errorEl.classList.remove('d-none');
    },

    /**
     * @private
     * @param {HTMLElement} form - The OnePay inline form.
     * @return {void}
     */
    _onepayHideError(form) {
        form.querySelector('[name="o_onepay_error"]').classList.add('d-none');
    },

});
