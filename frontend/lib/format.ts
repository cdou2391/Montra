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
  return new Date(`${iso}T00:00:00`).toLocaleDateString(undefined, {
    day: "numeric",
    month: "short",
    year: "numeric",
  });
}

/** Signed display for a ledger entry, from the account's own perspective. */
export function signedAmount(direction: "INCREASE" | "DECREASE", amount: string): string {
  return direction === "INCREASE" ? `+${amount}` : `-${amount}`;
}
