/**
 * NUMO QR payload encoder.
 *
 * NUMO is Libya's national QR payment standard (Central Bank of Libya), an
 * EMVCo-style Tag-Length-Value format. This module is deliberately free of any
 * Odoo import so it stays a pure function of its inputs: it is the piece most
 * likely to be wrong, and it is the piece easiest to test in isolation.
 *
 * Two notes on the standard, both established by testing real payloads against
 * a working Libyan implementation (qrpay.ly) rather than read off the spec:
 *
 * 1. The CBL developer portal prints its dynamic example with the amount as
 *    `5406100.500` — a declared length of 06 for a 7-character value. That is
 *    wrong, and not harmlessly: a reader consumes `100.50`, then treats the
 *    leftover `0` as the start of the next tag and desynchronises for the rest
 *    of the payload. Lengths here are always computed from the value.
 *
 * 2. The same portal shows tag 30 as nested TLV (bank code + bank name). Real
 *    payloads carry a bare 3-digit bank code, which is what this encoder emits.
 */

/** Maximum value length representable by NUMO's 2-digit length prefix. */
const MAX_VALUE_LENGTH = 99;

/** Per-tag caps, where the standard is narrower than the 2-digit length. */
const FIELD_LIMITS = {
    59: 25, // Merchant name
    60: 15, // City
};

/**
 * CRC-16/CCITT-FALSE over the ASCII bytes of `input`.
 *
 * Polynomial 0x1021, initial value 0xFFFF, no reflection, no final XOR. The
 * checksum covers the whole payload including tag 63's own `6304` header.
 *
 * @param {string} input
 * @returns {string} Four uppercase hex digits.
 */
export function crc16ccitt(input) {
    let crc = 0xffff;
    for (let i = 0; i < input.length; i++) {
        crc ^= input.charCodeAt(i) << 8;
        for (let bit = 0; bit < 8; bit++) {
            crc = crc & 0x8000 ? ((crc << 1) ^ 0x1021) & 0xffff : (crc << 1) & 0xffff;
        }
    }
    return crc.toString(16).toUpperCase().padStart(4, "0");
}

/**
 * Encode one Tag-Length-Value field.
 *
 * @param {string} tag - Two-digit tag.
 * @param {string} value
 * @returns {string} The encoded field, or "" when the value is empty.
 */
export function tlv(tag, value) {
    // Odoo serialises an empty Char field as boolean `false`, not "" or null.
    // Without that check the field is encoded as the literal string "false".
    if (value === undefined || value === null || value === "" || value === false) {
        return "";
    }
    let text = String(value);
    const limit = Math.min(FIELD_LIMITS[tag] ?? MAX_VALUE_LENGTH, MAX_VALUE_LENGTH);
    if (text.length > limit) {
        text = text.slice(0, limit);
    }
    return tag + String(text.length).padStart(2, "0") + text;
}

/**
 * Format an amount the way the gateway expects: a plain decimal string, no
 * thousands separator, no currency symbol.
 *
 * @param {number} amount
 * @param {number} decimals - Decimal places of the currency (3 for LYD).
 * @returns {string}
 */
export function formatAmount(amount, decimals = 3) {
    return Number(amount).toFixed(decimals);
}

/**
 * Build the additional-data field (tag 62), itself a nested TLV structure.
 *
 * @param {object} extra
 * @param {string} [extra.billNumber] - 62-01, the POS order reference.
 * @param {string} [extra.storeLabel] - 62-03.
 * @param {string} [extra.terminalLabel] - 62-07, the till name.
 * @returns {string} The encoded tag 62, or "" when nothing was supplied.
 */
export function buildAdditionalData({ billNumber, storeLabel, terminalLabel } = {}) {
    const inner = tlv("01", billNumber) + tlv("03", storeLabel) + tlv("07", terminalLabel);
    return tlv("62", inner);
}

/**
 * Build a complete NUMO payload, CRC included.
 *
 * Tags are emitted in ascending order, which is what conforming readers expect
 * and what real payloads do. Optional fields are omitted entirely rather than
 * sent empty.
 *
 * @param {object} values
 * @param {string} values.accountName - Tag 27.
 * @param {string} [values.accountSchema] - Tag 28, "IBAN" or "Alias".
 * @param {string} values.account - Tag 29, the IBAN or alias.
 * @param {string} values.bankCode - Tag 30, the 3-digit institution code.
 * @param {string} values.merchantName - Tag 59.
 * @param {string} values.city - Tag 60.
 * @param {string} [values.merchantAccount] - Tag 02.
 * @param {string} [values.mcc] - Tag 52, merchant category code.
 * @param {string} [values.currency] - Tag 53, ISO 4217 numeric.
 * @param {string} [values.countryCode] - Tag 58.
 * @param {number} [values.amount] - Tag 54. Omit for a static QR.
 * @param {number} [values.amountDecimals]
 * @param {string} [values.guid] - Tag 31, a per-transaction UUID.
 * @param {string} [values.merchantReference] - Tag 51.
 * @param {string} [values.postalCode] - Tag 61.
 * @param {object} [values.additionalData] - See buildAdditionalData.
 * @returns {string} The payload to encode into a QR code.
 */
export function buildNumoPayload({
    accountName,
    accountSchema = "IBAN",
    account,
    bankCode,
    merchantName,
    city,
    merchantAccount,
    mcc = "9999",
    currency = "434",
    countryCode = "LY",
    amount,
    amountDecimals = 3,
    guid,
    merchantReference,
    postalCode,
    additionalData,
} = {}) {
    // A QR carrying an amount is "dynamic" (12); one the customer types an
    // amount into is "static" (11).
    const hasAmount = amount !== undefined && amount !== null && Number(amount) > 0;

    const body =
        tlv("00", "01") +
        tlv("01", hasAmount ? "12" : "11") +
        tlv("02", merchantAccount) +
        tlv("27", accountName) +
        tlv("28", accountSchema) +
        // Spacing is presentational; the gateway wants the bare identifier.
        tlv("29", String(account || "").replace(/\s+/g, "").toUpperCase()) +
        tlv("30", bankCode) +
        tlv("31", guid) +
        tlv("51", merchantReference) +
        tlv("52", mcc) +
        tlv("53", currency) +
        (hasAmount ? tlv("54", formatAmount(amount, amountDecimals)) : "") +
        tlv("58", countryCode) +
        tlv("59", merchantName) +
        tlv("60", city) +
        tlv("61", postalCode) +
        buildAdditionalData(additionalData) +
        "6304"; // The CRC header is part of the checksummed content.

    return body + crc16ccitt(body);
}
