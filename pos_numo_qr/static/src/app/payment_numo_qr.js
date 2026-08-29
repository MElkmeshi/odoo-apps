import { _t } from "@web/core/l10n/translation";
import { PaymentInterface } from "@point_of_sale/app/utils/payment/payment_interface";
import { makeAwaitable } from "@point_of_sale/app/utils/make_awaitable_dialog";
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
    async sendPaymentRequest(uuid) {
        const order = this.pos.getOrder();
        const line = order.getPaymentlineByUuid(uuid);
        if (!line) {
            return false;
        }

        let payload;
        try {
            payload = this._buildPayload(line.getAmount(), order);
        } catch (error) {
            // A misconfigured method must not produce a QR pointing nowhere.
            this.env.services.dialog.add(AlertDialog, {
                title: _t("NUMO QR is not configured"),
                body: error.message,
            });
            return false;
        }

        line.setPaymentStatus("waiting");
        const confirmed = await makeAwaitable(this.env.services.dialog, NumoQrDialog, {
            payload,
            amount: this.env.utils.formatCurrency(line.getAmount()),
            merchantName: this.payment_method_id.numo_merchant_name,
            reference: this._orderReference(order),
        });

        return Boolean(confirmed);
    }

    /**
     * Nothing to cancel: no request ever left the till.
     *
     * @override
     * @returns {Promise<boolean>}
     */
    async sendPaymentCancel() {
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
                billNumber: this._orderReference(order),
                terminalLabel: this.pos.config.name,
            },
        });
    }

    /**
     * The reference that goes in the QR and on screen.
     *
     * Not `order.name`: an order that has not been saved yet is named "/", and
     * a payment QR is shown before the order is ever saved. `pos_reference` is
     * the receipt reference the till reconciles against, which is the one worth
     * carrying into the bank's record of the transfer.
     *
     * @private
     * @param {object} order
     * @returns {string}
     */
    _orderReference(order) {
        return order.pos_reference || order.getName() || "";
    }
}
