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


/**
 * The account a parsed message is about.
 *
 * A MoMo notification is about the wallet even when it mentions a bank at the
 * other end, so the channel maps to account types rather than to a name.
 * Returns nothing when the user holds no matching account — better to leave
 * the field as it was than to select an account the message never mentioned.
 */
export function accountForChannel<T extends { id: string; account_type: string }>(
  accounts: T[],
  channel: "MOBILE_MONEY" | "BANK" | null,
): T | undefined {
  if (!channel) return undefined;
  const wanted =
    channel === "MOBILE_MONEY" ? ["MOBILE_MONEY"] : ["CHECKING", "SAVINGS"];
  // The list arrives favourite-first, so the preferred one wins when a user
  // holds several of a kind.
  for (const type of wanted) {
    const match = accounts.find((a) => a.account_type === type);
    if (match) return match;
  }
  return undefined;
}
