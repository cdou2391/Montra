/**
 * Money formatting.
 *
 * Amounts arrive from the API as strings and are never parsed into a Number for
 * arithmetic — only for display grouping (UI/UX section 91).
 */

export function formatMoney(amount: string, currency: string): string {
  const negative = amount.startsWith("-");
  const [whole, fraction = "00"] = amount.replace("-", "").split(".");
  const grouped = whole.replace(/\B(?=(\d{3})+(?!\d))/g, ",");
  const zeroDecimal = currency === "RWF" || currency === "JPY";
  const body = zeroDecimal ? grouped : `${grouped}.${fraction}`;
  return `${negative ? "-" : ""}${currency} ${body}`;
}

export function formatDate(iso: string): string {
  return new Date(iso).toLocaleDateString(undefined, {
    day: "numeric",
    month: "short",
    year: "numeric",
  });
}

/** Time of day, in the viewer's local zone. */
export function formatTime(iso: string): string {
  return new Date(iso).toLocaleTimeString(undefined, {
    hour: "2-digit",
    minute: "2-digit",
  });
}

export function formatDateTime(iso: string): string {
  return `${formatDate(iso)}, ${formatTime(iso)}`;
}

/** Value for an <input type="datetime-local">, which wants local wall time. */
export function toLocalInputValue(value: Date = new Date()): string {
  const offset = value.getTimezoneOffset() * 60_000;
  return new Date(value.getTime() - offset).toISOString().slice(0, 16);
}

/** Signed display for a ledger entry, from the account's own perspective. */
export function signedAmount(direction: "INCREASE" | "DECREASE", amount: string): string {
  return direction === "INCREASE" ? `+${amount}` : `-${amount}`;
}
