import { Component } from "@odoo/owl";
import { Dialog } from "@web/core/dialog/dialog";
import { _t } from "@web/core/l10n/translation";

/**
 * The QR the customer scans, plus the cashier's confirm/cancel.
 *
 * The dialog knows nothing about NUMO: it is handed a finished payload and an
 * amount to display. Building the payload is the encoder's job.
 */
export class NumoQrDialog extends Component {
    static template = "pos_numo_qr.NumoQrDialog";
    static components = { Dialog };
    static props = {
        payload: String,
        amount: String,
        merchantName: { type: String, optional: true },
        reference: { type: String, optional: true },
        getPayload: Function,
        close: Function,
    };

    /**
     * The QR image URL.
     *
     * Odoo 18's POS has no client-side QR generator, so this goes through the
     * server's barcode route. That means the till needs a connection at the
     * moment of payment; a bundled generator would remove that dependency.
     */
    get qrSrc() {
        const params = new URLSearchParams({
            barcode_type: "QR",
            value: this.props.payload,
            width: "400",
            height: "400",
            humanreadable: "0",
        });
        return `/report/barcode/?${params.toString()}`;
    }

    get confirmLabel() {
        return _t("Payment Received");
    }

    confirm() {
        this.props.getPayload(true);
        this.props.close();
    }

    cancel() {
        this.props.getPayload(false);
        this.props.close();
    }
}
