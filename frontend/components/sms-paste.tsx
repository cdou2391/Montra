"use client";

/**
 * Paste a mobile-money SMS to fill the form.
 *
 * It fills fields and stops. Nothing is recorded until the user presses the
 * normal Add button, so a misread message costs a correction rather than a
 * wrong balance — and the user sees exactly what was understood before
 * anything happens.
 */

import { useState } from "react";

import { ParsedSms, montra } from "@/lib/api";
import { Icon } from "@/components/icons";
import { Button, Field } from "@/components/ui";
import { formatMoney } from "@/lib/format";

// The parser's own vocabulary, said as a person would. Several markers can
// describe the same filled field, so the list is deduplicated before it is
// read back — "the accounts, transfer, account" is not a sentence.
const FIELD_NAMES: Record<string, string> = {
  expense: "amount",
  income: "amount",
  transfer: "amount",
  accounts: "accounts",
  account: "accounts",
  merchant: "merchant",
  voucher: "voucher",
  fee: "fee",
  balance: "balance",
  timestamp: "date and time",
  reference: "reference",
};

/** Account numbers the message named that we could not place. */
function unplaced(result: ParsedSms): string[] {
  const out: string[] = [];
  if (result.debited_identifier && !result.source_account_id) {
    out.push(result.debited_identifier);
  }
  if (result.credited_identifier && !result.destination_account_id) {
    out.push(result.credited_identifier);
  }
  return out;
}

function readableFields(matched: string[]): string {
  const named = matched.map((m) => FIELD_NAMES[m] ?? m);
  return [...new Set(named)].join(", ");
}

export function SmsPaste({
  onParsed,
}: {
  onParsed: (parsed: ParsedSms) => void;
}) {
  const [open, setOpen] = useState(false);
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<ParsedSms | null>(null);

  async function read() {
    if (!message.trim()) return;
    setBusy(true);
    try {
      const parsed = await montra.parseSms(message);
      setResult(parsed);
      if (parsed.understood) onParsed(parsed);
    } catch {
      setResult(null);
    } finally {
      setBusy(false);
    }
  }

  if (!open) {
    return (
      <button
        type="button"
        onClick={() => setOpen(true)}
        className="pressable pressable-surface mb-5 flex w-full items-center gap-3 rounded-control border border-dashed border-line/15 px-4 py-3 text-left"
      >
        <span className="text-content-secondary">
          <Icon name="paperclip" size={16} />
        </span>
        <span className="text-sm text-content-secondary">
          Paste a mobile money SMS to fill this in
        </span>
      </button>
    );
  }

  return (
    <div className="mb-5 rounded-control border border-line/10 p-4">
      <Field label="Paste the message">
        <textarea
          rows={4}
          value={message}
          onChange={(e) => setMessage(e.target.value)}
          placeholder="*165*S*200000 RWF transferred to …"
          className="min-h-[96px] w-full rounded-control border border-line/10 bg-background-secondary px-3 py-2 text-sm text-content-primary placeholder:text-content-muted focus:border-accent focus:outline-none"
        />
      </Field>

      {result && !result.understood && (
        <p className="mt-3 text-xs text-semantic-warning">
          {/* Explicit rather than silent: a form that quietly stays blank looks
              like the button did nothing. */}
          That message was not recognised. Fill the form in below instead.
        </p>
      )}

      {result?.understood && unplaced(result).length > 0 && (
        <p className="mt-3 text-xs text-semantic-warning">
          {/* Naming the number is what makes this actionable: it is the value
              to paste into Account details. */}
          {unplaced(result).join(" and ")}{" "}
          {unplaced(result).length === 1 ? "matches" : "match"} none of your
          accounts. Pick the account below, or store that number under Account
          details so it is recognised next time.
        </p>
      )}

      {result?.understood && (
        <p className="mt-3 text-xs text-semantic-income">
          Filled in the {readableFields(result.matched)}.
          {result.balance_after
            ? ` The message says the balance is now ${formatMoney(
                result.balance_after,
                // The balance's own currency. A card quotes a foreign purchase
                // in one currency and its balance in another, and labelling
                // this with the purchase's would state something the message
                // never said.
                result.balance_currency ?? result.currency ?? "RWF",
              )}.`
            : ""}{" "}
          Check it, then add.
        </p>
      )}

      {/* A foreign purchase on a local card. The amount on the form is a
          conversion at today's market rate, not what the bank charged — it has
          its own rate and takes a margin. Warned rather than filled silently:
          a converted figure looks exactly like a real one. */}
      {result?.currency_conversion && (
        <p className="mt-3 text-xs text-semantic-warning">
          The message is in {result.currency_conversion.from_currency} and this
          account is in {result.currency_conversion.to_currency}.{" "}
          {result.currency_conversion.amount ? (
            <>
              Filled in{" "}
              {formatMoney(
                result.currency_conversion.amount,
                result.currency_conversion.to_currency,
              )}
              , converted from{" "}
              {formatMoney(
                result.currency_conversion.from_amount,
                result.currency_conversion.from_currency,
              )}{" "}
              at today&apos;s rate. Your bank used its own rate — replace this
              with the amount it charged.
            </>
          ) : (
            <>
              No rate is known for that pair, so the amount is still in{" "}
              {result.currency_conversion.from_currency}. Replace it with the
              amount your bank charged.
            </>
          )}
        </p>
      )}

      <div className="mt-4 flex gap-3">
        <Button variant="secondary" disabled={busy || !message.trim()} onClick={read}>
          {busy ? "Reading…" : "Read message"}
        </Button>
        <button
          type="button"
          onClick={() => {
            setOpen(false);
            setMessage("");
            setResult(null);
          }}
          className="pressable text-xs text-content-secondary"
        >
          Close
        </button>
      </div>
    </div>
  );
}
