import { register_payment_method } from "@point_of_sale/app/services/pos_store";
import { PaymentNumoQr } from "@pos_numo_qr/app/payment_numo_qr";

register_payment_method("numo_qr", PaymentNumoQr);
