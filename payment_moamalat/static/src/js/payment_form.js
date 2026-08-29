/** @odoo-module */
/* global Lightbox */

import { _t } from '@web/core/l10n/translation';
import { rpc } from '@web/core/network/rpc';

import paymentForm from '@payment/js/payment_form';


paymentForm.include({

    // #=== DOM MANIPULATION ===#

    /**
     * Prepare the inline form of Moamalat for direct payment.
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
        if (providerCode !== 'moamalat') {
            this._super(...arguments);
            return;
        }
        if (flow === 'token') {
            return;
        }

        this._setPaymentFlow('direct');

        const radio = document.querySelector('input[name="o_payment_radio"]:checked');
        const inlineForm = this._getInlineForm(radio);
        const container = inlineForm?.querySelector('[name="o_moamalat_element_container"]');
        if (!container) {
            return;
        }

        this.moamalatFormValues = JSON.parse(container.dataset['moamalatInlineFormValues']);
        await this._loadMoamalatLightbox(this.moamalatFormValues['lightbox_url']);
    },

    /**
     * Load the Moamalat Lightbox script.
     *
     * The URL depends on whether the provider is in test or production, so the
     * script is fetched when Moamalat is picked rather than declared as an
     * asset. Resolves immediately if it is already on the page.
     *
     * @private
     * @param {string} lightboxUrl - The URL of the Lightbox script.
     * @return {Promise}
     */
    _loadMoamalatLightbox(lightboxUrl) {
        if (typeof Lightbox !== 'undefined') {
            return Promise.resolve();
        }
        this.moamalatLightboxPromise ??= new Promise((resolve, reject) => {
            const script = document.createElement('script');
            script.src = lightboxUrl;
            script.onload = resolve;
            script.onerror = () => reject(new Error(_t("Could not load the Moamalat Lightbox.")));
            document.head.appendChild(script);
        });
        return this.moamalatLightboxPromise;
    },

    // #=== PAYMENT FLOW ===#

    /**
     * Process the direct payment flow.
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
        if (providerCode !== 'moamalat') {
            await this._super(...arguments);
            return;
        }

        const loadingEl = document.getElementById('o_moamalat_loading');
        const errorEl = document.getElementById('o_moamalat_error');
        if (loadingEl) {
            loadingEl.style.display = 'block';
        }
        if (errorEl) {
            errorEl.style.display = 'none';
        }

        try {
            if (typeof Lightbox === 'undefined') {
                throw new Error(_t("Payment system not loaded. Please refresh the page."));
            }
            await this._showMoamalatLightbox(processingValues);
        } catch (error) {
            if (loadingEl) {
                loadingEl.style.display = 'none';
            }
            this._displayErrorDialog(_t("Payment Error"), error.message);
            this._enableButton();
        }
    },

    /**
     * Open the Lightbox and report its outcome.
     *
     * Whatever the Lightbox reports is only ever a hint: the transaction is
     * settled server-side from Moamalat's signed webhook. This tells the
     * server the customer finished, then sends them to the status page to
     * wait for that confirmation.
     *
     * @private
     * @param {object} processingValues - The processing values of the transaction.
     * @return {Promise}
     */
    _showMoamalatLightbox(processingValues) {
        const reference = processingValues['merchant_reference'] || processingValues['reference'];
        const loadingEl = document.getElementById('o_moamalat_loading');
        if (loadingEl) {
            loadingEl.style.display = 'none';
        }

        return new Promise((resolve, reject) => {
            let completed = false;

            Lightbox.Checkout.configure = {
                MID: processingValues['merchant_id'],
                TID: processingValues['terminal_id'],
                AmountTrxn: processingValues['amount'],
                MerchantReference: reference,
                TrxDateTime: processingValues['datetime_local'],
                SecureHash: processingValues['secure_hash'],

                completeCallback: (data) => {
                    completed = true;
                    this._notifyMoamalatOutcome(reference, 'success', data).then(resolve);
                },
                errorCallback: (error) => {
                    this._notifyMoamalatOutcome(reference, 'error', error).then(() => {
                        reject(new Error(error?.Message || _t("The payment failed.")));
                    });
                },
                cancelCallback: () => {
                    if (completed) {
                        return;
                    }
                    this._notifyMoamalatOutcome(reference, 'cancelled', {}).then(() => {
                        reject(new Error(_t("The payment was cancelled.")));
                    });
                },
            };

            try {
                Lightbox.Checkout.showLightbox();
            } catch (error) {
                reject(error);
            }
        });
    },

    /**
     * Tell the server the customer finished, then follow it to the status page.
     *
     * @private
     * @param {string} reference - The transaction reference.
     * @param {string} status - What the Lightbox reported.
     * @param {object} data - The raw Lightbox payload.
     * @return {Promise}
     */
    async _notifyMoamalatOutcome(reference, status, data) {
        let redirectUrl = '/payment/status';
        try {
            const result = await rpc('/payment/moamalat/callback', {
                reference: reference,
                status: status,
                data: data ?? {},
            });
            redirectUrl = result?.redirect_url || redirectUrl;
        } catch {
            // The status page reflects the server's own view of the
            // transaction, so it is still the right place to land.
        }
        window.location = redirectUrl;
    },

});
