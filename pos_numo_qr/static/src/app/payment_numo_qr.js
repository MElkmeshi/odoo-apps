import { _t } from "@web/core/l10n/translation";
import { PaymentInterface } from "@point_of_sale/app/payment/payment_interface";
import { makeAwaitable } from "@point_of_sale/app/store/make_awaitable_dialog";
import { AlertDialog } from "@web/core/confirmation_dialog/confirmation_dialog";

import { buildNumoPayload } from "@pos_numo_qr/app/numo_payload";
import { NumoQrDialog } from "@pos_numo_qr/app/numo_qr_dialog";

export class PaymentNumoQr extends PaymentInterface {
    /**
     * Show the QR and wait for the cashier.
     *
     * There is no gateway call here and no confirmation channel: NUMO's
     * merchant-presented flow ends at the customer's own banking app. The
     * cashier confirming is the only signal the till gets, so the payment is
     * only ever as trustworthy as that.
     *
     * @override
     * @param {string} uuid - The uuid of the payment line.
     * @returns {Promise<boolean>} Whether the payment line should be accepted.
     */
    async send_payment_request(uuid) {
        const order = this.pos.get_order();
        const line = order.payment_ids.find((paymentLine) => paymentLine.uuid === uuid);
        if (!line) {
            return false;
        }

        let payload;
        try {
            payload = this._buildPayload(line.get_amount(), order);
        } catch (error) {
            // A misconfigured method must not produce a QR pointing nowhere.
            this.env.services.dialog.add(AlertDialog, {
                title: _t("NUMO QR is not configured"),
                body: error.message,
            });
            return false;
        }

        line.set_payment_status("waiting");
        const confirmed = await makeAwaitable(this.env.services.dialog, NumoQrDialog, {
            payload,
            amount: this.env.utils.formatCurrency(line.get_amount()),
            merchantName: this.payment_method_id.numo_merchant_name,
            reference: order.name,
        });

        return Boolean(confirmed);
    }

    /**
     * Nothing to cancel: no request ever left the till.
     *
     * @override
     * @returns {Promise<boolean>}
     */
    async send_payment_cancel() {
        return true;
    }

    /**
     * Assemble the payload from the payment method's configuration.
     *
     * @private
     * @param {number} amount
     * @param {object} order
     * @returns {string}
     */
    _buildPayload(amount, order) {
        const method = this.payment_method_id;
        if (!method.numo_iban || !method.numo_bank_code) {
            throw new Error(
                _t("Set the IBAN and bank code on this payment method before using it.")
            );
        }
        return buildNumoPayload({
            accountName: method.numo_account_name,
            account: method.numo_iban,
            bankCode: method.numo_bank_code,
            merchantName: method.numo_merchant_name,
            city: method.numo_city,
            mcc: method.numo_mcc || "9999",
            merchantAccount: method.numo_merchant_account,
            amount,
            amountDecimals: this.pos.currency.decimal_places,
            additionalData: {
                billNumber: order.name,
                terminalLabel: this.pos.config.name,
            },
        });
    }
}
