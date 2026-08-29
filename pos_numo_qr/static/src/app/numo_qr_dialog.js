import { Component } from "@odoo/owl";
import { Dialog } from "@web/core/dialog/dialog";
import { _t } from "@web/core/l10n/translation";
import { generateQRCodeDataUrl } from "@point_of_sale/utils";

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

    setup() {
        // Rendered once, up front, rather than from a getter: the payload never
        // changes while the dialog is open, and the till has no reason to
        // re-encode it on every render.
        this.qrSrc = generateQRCodeDataUrl(this.props.payload, { width: 320, height: 320 });
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
