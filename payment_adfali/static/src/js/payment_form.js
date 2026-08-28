/** @odoo-module **/

import { _t } from '@web/core/l10n/translation';
import { rpc } from '@web/core/network/rpc';
import paymentForm from '@payment/js/payment_form';

paymentForm.include({

    /**
     * Force the direct flow so the PIN exchange runs on this page.
     *
     * @override
     */
    async _prepareInlineForm(providerId, providerCode, paymentOptionId, paymentMethodCode, flow) {
        if (providerCode !== 'adfali') {
            return this._super(...arguments);
        }
        this._setPaymentFlow('direct');
    },

    /**
     * Run the two-phase PIN exchange.
     *
     * The transaction already exists at this point; phase one asks the gateway
     * to send the PIN, phase two spends it.
     *
     * @override
     */
    async _processDirectFlow(providerCode, paymentOptionId, paymentMethodCode, processingValues) {
        if (providerCode !== 'adfali') {
            return this._super(...arguments);
        }

        const form = this._adfaliGetForm();
        if (!form) {
            this._displayErrorDialog(_t("Payment processing failed"));
            return;
        }

        const mobile = form.querySelector('[name="o_adfali_mobile"]').value.trim();
        if (!mobile) {
            this._adfaliShowError(form, _t("Please enter your mobile number."));
            this._enableButton();
            return;
        }

        this._adfaliHideError(form);
        const result = await rpc('/payment/adfali/init', {
            reference: processingValues.reference,
            mobile: mobile,
        });

        if (result.error) {
            // The transaction is still draft, so the customer can correct and retry.
            this._adfaliShowError(form, result.error);
            this._enableButton();
            return;
        }

        this._adfaliShowOtpStep(form, result.otp_length, processingValues.reference);
    },

    /**
     * Swap the inline form to the PIN step and wire its confirm button.
     *
     * @private
     * @param {HTMLElement} form - The Adfali inline form.
     * @param {number} otpLength - The expected length of the PIN.
     * @param {string} reference - The transaction reference.
     * @return {void}
     */
    _adfaliShowOtpStep(form, otpLength, reference) {
        form.querySelector('[name="o_adfali_mobile_step"]').classList.add('d-none');

        const otpStep = form.querySelector('[name="o_adfali_otp_step"]');
        otpStep.classList.remove('d-none');

        const otpInput = otpStep.querySelector('[name="o_adfali_otp"]');
        otpInput.setAttribute('maxlength', otpLength);
        otpInput.focus();

        // The generic submit button no longer applies: this step has its own.
        this._hideInputs();

        const confirmButton = otpStep.querySelector('[name="o_adfali_confirm_button"]');
        confirmButton.addEventListener('click', async () => {
            const otp = otpInput.value.trim();
            if (!otp) {
                this._adfaliShowError(form, _t("Please enter the PIN sent to your mobile number."));
                return;
            }

            confirmButton.disabled = true;
            this._adfaliHideError(form);
            const result = await rpc('/payment/adfali/confirm', { reference, otp });

            if (result.error) {
                this._adfaliShowError(form, result.error);
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
    _adfaliGetForm() {
        const checkedRadio = this.el.querySelector('input[name="o_payment_radio"]:checked');
        if (!checkedRadio) {
            return null;
        }
        return this._getInlineForm(checkedRadio)?.querySelector('[name="o_adfali_form"]') ?? null;
    },

    /**
     * @private
     * @param {HTMLElement} form - The Adfali inline form.
     * @param {string} message - The message to display.
     * @return {void}
     */
    _adfaliShowError(form, message) {
        const errorEl = form.querySelector('[name="o_adfali_error"]');
        errorEl.textContent = message;
        errorEl.classList.remove('d-none');
    },

    /**
     * @private
     * @param {HTMLElement} form - The Adfali inline form.
     * @return {void}
     */
    _adfaliHideError(form) {
        form.querySelector('[name="o_adfali_error"]').classList.add('d-none');
    },

});
