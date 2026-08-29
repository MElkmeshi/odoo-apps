/** @odoo-module */

import { _t } from '@web/core/l10n/translation';
import { rpc } from '@web/core/network/rpc';

import paymentForm from '@payment/js/payment_form';

// Adfali and Sadad are settled over the API rather than by sending the customer
// to Plutu, so they run the direct flow. The other three stay on redirect.
const PLUTU_OTP_GATEWAYS = ['edfali', 'sadadapi'];

paymentForm.include({

    // #=== DOM MANIPULATION ===#

    /**
     * Show the code form for the gateways that need it, and pick the flow.
     *
     * @override method from @payment/js/payment_form
     * @private
     * @param {number} providerId - The id of the selected payment option's provider.
     * @param {string} providerCode - The code of the selected payment option's provider.
     * @param {number} paymentOptionId - The id of the selected payment option.
     * @param {string} paymentMethodCode - The code of the selected payment method, if any.
     * @param {string} flow - The online payment flow of the selected payment option.
     * @return {void}
     */
    async _prepareInlineForm(providerId, providerCode, paymentOptionId, paymentMethodCode, flow) {
        if (providerCode !== 'plutu') {
            this._super(...arguments);
            return;
        }
        if (flow === 'token') {
            return;
        }

        const form = this._plutuGetForm();
        const isOtp = PLUTU_OTP_GATEWAYS.includes(paymentMethodCode);
        if (form) {
            // One inline form serves the whole provider, so it has to be hidden
            // again when the customer switches to a redirect gateway.
            form.classList.toggle('d-none', !isOtp);
            this._plutuReset(form);
        }
        if (isOtp) {
            this._setPaymentFlow('direct');
        }
    },

    /**
     * @private
     * @return {HTMLElement|null} The Plutu code form, if it is on the page.
     */
    _plutuGetForm() {
        const radio = document.querySelector('input[name="o_payment_radio"]:checked');
        const inlineForm = radio && this._getInlineForm(radio);
        return inlineForm?.querySelector('[name="o_plutu_otp_form"]') ?? null;
    },

    /**
     * Put the form back to its first step.
     *
     * @private
     * @param {HTMLElement} form - The Plutu code form.
     * @return {void}
     */
    _plutuReset(form) {
        form.querySelector('[name="o_plutu_code_step"]').classList.add('d-none');
        form.querySelector('[name="o_plutu_mobile_step"]').classList.remove('d-none');
        this._plutuHideError(form);
    },

    _plutuShowError(form, message) {
        const el = form.querySelector('[name="o_plutu_error"]');
        el.textContent = message;
        el.classList.remove('d-none');
    },

    _plutuHideError(form) {
        form.querySelector('[name="o_plutu_error"]').classList.add('d-none');
    },

    // #=== PAYMENT FLOW ===#

    /**
     * Run the two-step code exchange.
     *
     * The transaction already exists by this point. Step one asks Plutu to text
     * the customer; step two spends the code. Nothing is charged until step two.
     *
     * @override method from @payment/js/payment_form
     * @private
     * @param {string} providerCode - The code of the selected payment option's provider.
     * @param {number} paymentOptionId - The id of the selected payment option.
     * @param {string} paymentMethodCode - The code of the selected payment method, if any.
     * @param {object} processingValues - The processing values of the transaction.
     * @return {void}
     */
    async _processDirectFlow(providerCode, paymentOptionId, paymentMethodCode, processingValues) {
        if (providerCode !== 'plutu' || !PLUTU_OTP_GATEWAYS.includes(paymentMethodCode)) {
            await this._super(...arguments);
            return;
        }

        const form = this._plutuGetForm();
        if (!form) {
            this._displayErrorDialog(_t("Payment processing failed"));
            return;
        }

        // The hint and the birth-year field are driven by the server, so the
        // rules live in exactly one place.
        form.querySelector('[name="o_plutu_mobile_hint"]').textContent = _t(
            "Format: %s", processingValues.plutu_mobile_hint
        );
        const birthYearGroup = form.querySelector('[name="o_plutu_birth_year_group"]');
        birthYearGroup.classList.toggle('d-none', !processingValues.plutu_requires_birth_year);

        const mobile = form.querySelector('[name="o_plutu_mobile"]').value.trim();
        if (!mobile) {
            this._plutuShowError(form, _t("Please enter your mobile number."));
            this._enableButton();
            return;
        }
        const birthYear = processingValues.plutu_requires_birth_year
            ? form.querySelector('[name="o_plutu_birth_year"]').value.trim()
            : null;

        this._plutuHideError(form);
        const result = await rpc('/payment/plutu/otp/send', {
            reference: processingValues.reference,
            access_token: processingValues.plutu_access_token,
            mobile_number: mobile,
            birth_year: birthYear,
        });

        if (result.error) {
            // Nothing has been charged, so the customer can fix a typo and retry.
            this._plutuShowError(form, result.error);
            this._enableButton();
            return;
        }

        this._plutuShowCodeStep(form, result.code_length, processingValues);
    },

    /**
     * Swap to the code step and wire its confirm button.
     *
     * @private
     * @param {HTMLElement} form - The Plutu code form.
     * @param {number} codeLength - How many digits the code has.
     * @param {object} processingValues - The processing values of the transaction.
     * @return {void}
     */
    _plutuShowCodeStep(form, codeLength, processingValues) {
        form.querySelector('[name="o_plutu_mobile_step"]').classList.add('d-none');
        const codeStep = form.querySelector('[name="o_plutu_code_step"]');
        codeStep.classList.remove('d-none');

        const codeInput = form.querySelector('[name="o_plutu_code"]');
        codeInput.setAttribute('maxlength', String(codeLength));
        codeInput.value = '';
        codeInput.focus();

        const button = form.querySelector('[name="o_plutu_confirm_button"]');
        // Replaced rather than added to: switching gateways and coming back
        // would otherwise stack a second handler and confirm twice.
        const fresh = button.cloneNode(true);
        button.replaceWith(fresh);
        fresh.addEventListener('click', async () => {
            fresh.disabled = true;
            this._plutuHideError(form);
            const result = await rpc('/payment/plutu/otp/confirm', {
                reference: processingValues.reference,
                access_token: processingValues.plutu_access_token,
                code: codeInput.value.trim(),
            });
            if (result.error) {
                this._plutuShowError(form, result.error);
                fresh.disabled = false;
                return;
            }
            window.location = result.redirect_url || '/payment/status';
        });
    },

});
