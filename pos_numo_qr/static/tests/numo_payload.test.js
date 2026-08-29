import { describe, expect, test } from "@odoo/hoot";
import { buildNumoPayload, crc16ccitt, tlv } from "@pos_numo_qr/app/numo_payload";

/**
 * The vectors below are not invented. They were captured from qrpay.ly, a
 * working Libyan NUMO implementation, and its validator accepted the dynamic
 * one. Encoding to something a real reader parses is the only property of this
 * module that matters, so the tests assert byte equality against real payloads
 * rather than against our own idea of the format.
 */
const REAL_STATIC_PAYLOAD =
    "000201010211" +
    "2706kjhkhj" +
    "2804IBAN" +
    "2925LY19024007010118519020701" +
    "3003024" +
    "52049999" +
    "5303434" +
    "5802LY" +
    "5906kjhkhj" +
    "60011" +
    "6304572E";

const REAL_DYNAMIC_PAYLOAD =
    "0002010102122706kjhkhj2804IBAN2925LY190240070101185190207013003024520499995303434" +
    "5407100.5005802LY5906kjhkhj600116304E0B9";

describe("crc16ccitt", () => {
    test("reproduces the checksum of a real payload", () => {
        expect(crc16ccitt(REAL_STATIC_PAYLOAD.slice(0, -4))).toBe("572E");
    });
});

describe("tlv", () => {
    test("takes the length from the value, not from the caller", () => {
        expect(tlv("54", "100.500")).toBe("5407100.500");
    });

    test("omits empty values", () => {
        expect(tlv("31", "")).toBe("");
        expect(tlv("31", null)).toBe("");
        expect(tlv("31", undefined)).toBe("");
    });

    test("omits Odoo's boolean false for an unset Char field", () => {
        // Odoo sends `false` rather than "" for an empty Char. Encoding that
        // literally puts the string "false" in the customer's QR code.
        expect(tlv("02", false)).toBe("");
    });

    test("truncates a merchant name to the 25 characters the standard allows", () => {
        expect(tlv("59", "x".repeat(40))).toBe("5925" + "x".repeat(25));
    });
});

describe("buildNumoPayload", () => {
    test("reproduces a real static payload byte for byte", () => {
        const payload = buildNumoPayload({
            accountName: "kjhkhj",
            account: "LY19 0240 0701 0118 5190 2070 1", // spacing must be stripped
            bankCode: "024",
            merchantName: "kjhkhj",
            city: "1",
        });
        expect(payload).toBe(REAL_STATIC_PAYLOAD);
    });

    test("reproduces the dynamic payload the reference validator accepted", () => {
        const payload = buildNumoPayload({
            accountName: "kjhkhj",
            account: "LY19024007010118519020701",
            bankCode: "024",
            merchantName: "kjhkhj",
            city: "1",
            amount: 100.5,
        });
        expect(payload).toBe(REAL_DYNAMIC_PAYLOAD);
    });

    test("declares the amount's true length, not the one printed in the CBL doc", () => {
        // The portal prints `5406100.500` for a 7-character value. A reader
        // consuming 6 characters keeps the stray "0" and desynchronises for the
        // rest of the payload, so every field after the amount is lost.
        const payload = buildNumoPayload({
            accountName: "kjhkhj",
            account: "LY19024007010118519020701",
            bankCode: "024",
            merchantName: "kjhkhj",
            city: "1",
            amount: 100.5,
        });
        expect(payload).toInclude("5407100.500");
        expect(payload).not.toInclude("5406100.500");
    });

    test("marks a payload with an amount as dynamic and one without as static", () => {
        const base = {
            accountName: "kjhkhj",
            account: "LY19024007010118519020701",
            bankCode: "024",
            merchantName: "kjhkhj",
            city: "1",
        };
        expect(buildNumoPayload({ ...base, amount: 5 }).slice(6, 12)).toBe("010212");
        expect(buildNumoPayload(base).slice(6, 12)).toBe("010211");
    });

    test("leaves no literal 'false' in the payload when optional fields are unset", () => {
        const payload = buildNumoPayload({
            accountName: "Hajat Market",
            account: "LY19024007010118519020701",
            bankCode: "024",
            merchantName: "Hajat Market",
            city: "Tripoli",
            merchantAccount: false, // as Odoo sends it
            amount: 4.6,
            amountDecimals: 2,
        });
        expect(payload).not.toInclude("false");
    });
});
