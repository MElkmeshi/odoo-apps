import { _t } from '@web/core/l10n/translation';
import { rpc } from '@web/core/network/rpc';
import { patch } from '@web/core/utils/patch';

import { PaymentForm } from '@payment/interactions/payment_form';

const ONEPAY_CODES = ['onepay', 'musrefy_pay', 'yussor_online', 'sahara_pay'];

patch(PaymentForm.prototype, {

    // #=== DOM MANIPULATION ===#

    /**
     * Force the direct flow so the OTP exchange runs on this page.
     *
     * @override method from @payment/interactions/payment_form
     * @private
     * @param {number} providerId - The id of the selected payment option's provider.
     * @param {string} providerCode - The code of the selected payment option's provider.
     * @param {number} paymentOptionId - The id of the selected payment option.
     * @param {string} paymentMethodCode - The code of the selected payment method, if any.
     * @param {string} flow - The online payment flow of the selected payment option.
     * @return {void}
     */
    async _prepareInlineForm(providerId, providerCode, paymentOptionId, paymentMethodCode, flow) {
        if (!ONEPAY_CODES.includes(providerCode)) {
            await super._prepareInlineForm(...arguments);
            return;
        }
        this._setPaymentFlow('direct');
    },

    // #=== PAYMENT FLOW ===#

    /**
     * Run the two-phase OTP exchange.
     *
     * The transaction already exists at this point; phase one asks the gateway
     * to send the OTP, phase two spends it.
     *
     * @override method from @payment/interactions/payment_form
     * @private
     * @param {string} providerCode - The code of the selected payment option's provider.
     * @param {number} paymentOptionId - The id of the selected payment option.
     * @param {string} paymentMethodCode - The code of the selected payment method, if any.
     * @param {object} processingValues - The processing values of the transaction.
     * @return {void}
     */
    async _processDirectFlow(providerCode, paymentOptionId, paymentMethodCode, processingValues) {
        if (!ONEPAY_CODES.includes(providerCode)) {
            await super._processDirectFlow(...arguments);
            return;
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
        const result = await rpc('/payment/onepay_ly/init', {
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
        if (confirmButton.dataset.onepayBound) {
            return; // The step is already wired; a second binding would double-submit the OTP.
        }
        confirmButton.dataset.onepayBound = '1';
        // `addListener` is the Interaction's own binder, so the handler is
        // removed when the interaction is destroyed.
        this.addListener(confirmButton, 'click', async () => {
            const otp = otpInput.value.trim();
            if (!otp) {
                this._onepayShowError(form, _t("Please enter the one-time password."));
                return;
            }

            confirmButton.disabled = true;
            this._onepayHideError(form);
            const result = await rpc('/payment/onepay_ly/confirm', { reference, otp });

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
