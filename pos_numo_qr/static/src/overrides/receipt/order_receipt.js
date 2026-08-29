import { patch } from "@web/core/utils/patch";
import { OrderReceipt } from "@point_of_sale/app/screens/receipt_screen/receipt/order_receipt";
import { generateQRCodeDataUrl } from "@point_of_sale/utils";

import { buildPayloadForMethod } from "@pos_numo_qr/app/numo_payload";

patch(OrderReceipt.prototype, {
    /**
     * The NUMO QR to print, or null when this sale has nothing to do with NUMO.
     *
     * Built from the payment line rather than the order total: a customer can
     * split a bill across cash and NUMO, and the QR must ask for the part they
     * actually owe the bank, not the whole ticket.
     *
     * @returns {{src: string, amount: number, method: object}|null}
     */
    get numoQr() {
        const line = this.order.payment_ids.find(
            (payment) =>
                !payment.is_change &&
                payment.payment_method_id?.use_payment_terminal === "numo_qr" &&
                payment.payment_method_id?.numo_qr_display === "receipt"
        );
        if (!line) {
            return null;
        }

        let payload;
        try {
            payload = buildPayloadForMethod(line.payment_method_id, {
                amount: line.amount,
                amountDecimals: this.order.currency.decimal_places,
                reference: this.order.pos_reference || this.order.getName() || "",
                terminalLabel: this.order.config?.name,
            });
        } catch {
            // A misconfigured method is reported on the payment screen. Losing
            // the QR must not take the whole receipt down with it.
            return null;
        }

        return {
            // Smaller than the on-screen code: receipt paper is 80mm at best,
            // and an oversized QR is what gets clipped at the edges.
            src: generateQRCodeDataUrl(payload, { width: 220, height: 220 }),
            amount: line.amount,
            method: line.payment_method_id,
        };
    },
});
