import { Component } from "@odoo/owl";
import { generateQRCodeDataUrl } from "@point_of_sale/utils";

/**
 * The printable slip: the same QR the dialog shows, on paper.
 *
 * Printed before the customer has paid, so it deliberately carries no total,
 * no line items and no "thank you": it is a request for a transfer, not a
 * receipt for one. The till still prints its own receipt once the cashier
 * confirms.
 *
 * Takes plain values rather than a `pos.order` because it is rendered while
 * the order is still unsaved.
 */
export class NumoQrReceipt extends Component {
    static template = "pos_numo_qr.NumoQrReceipt";
    static props = {
        payload: String,
        amount: String,
        merchantName: { type: String, optional: true },
        city: { type: String, optional: true },
        reference: { type: String, optional: true },
        date: { type: String, optional: true },
    };

    setup() {
        // Smaller than the on-screen code: receipt paper is 80mm at best, and
        // an oversized QR is what gets clipped at the edges.
        this.qrSrc = generateQRCodeDataUrl(this.props.payload, { width: 220, height: 220 });
    }
}
