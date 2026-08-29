import { _t } from "@web/core/l10n/translation";
import { PaymentInterface } from "@point_of_sale/app/utils/payment/payment_interface";
import { makeAwaitable } from "@point_of_sale/app/utils/make_awaitable_dialog";
import { AlertDialog } from "@web/core/confirmation_dialog/confirmation_dialog";

import { buildPayloadForMethod } from "@pos_numo_qr/app/numo_payload";
import { NumoQrDialog } from "@pos_numo_qr/app/numo_qr_dialog";

export class PaymentNumoQr extends PaymentInterface {
    /**
     * Accept the payment, showing the QR at the till first if configured to.
     *
     * There is no gateway call here and no confirmation channel: NUMO's
     * merchant-presented flow ends at the customer's own banking app, so
     * nothing the till does can tell it the money arrived. What guards the
     * shop is the outstanding account the payment method points at: the takings
     * sit there until a bank statement clears them, and a transfer that never
     * happened simply never reconciles.
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

        if (this.payment_method_id.numo_qr_display === "receipt") {
            // The customer scans from the printed receipt after the sale, so
            // there is nothing for the cashier to watch and nothing to confirm.
            return true;
        }

        line.setPaymentStatus("waiting");
        const confirmed = await makeAwaitable(this.env.services.dialog, NumoQrDialog, {
            payload,
            amount: this.env.utils.formatCurrency(line.getAmount()),
            merchantName: this.payment_method_id.numo_merchant_name,
            reference: this._orderReference(order),
        });

        if (!confirmed) {
            // Returning false alone leaves the line at "retry", and any line
            // that is not done or reversed makes the order refuse every further
            // electronic payment. A card terminal has a request worth retrying;
            // this never sent one, so the line is just a trap. Odoo removes the
            // line the same way for its own QR methods.
            order.removePaymentline(line);
        }

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
     * Called even in receipt mode, before anything is accepted, so a broken
     * configuration is caught while the cashier can still pick another method
     * rather than after the customer has walked out with a useless QR.
     *
     * @private
     * @param {number} amount
     * @param {object} order
     * @returns {string}
     */
    _buildPayload(amount, order) {
        return buildPayloadForMethod(this.payment_method_id, {
            amount,
            amountDecimals: this.pos.currency.decimal_places,
            reference: this._orderReference(order),
            terminalLabel: this.pos.config.name,
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
