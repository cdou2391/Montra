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
  fee: "fee",
  balance: "balance",
  timestamp: "date and time",
  reference: "reference",
};

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
        className="pressable pressable-surface mb-5 flex w-full items-center gap-3 rounded-control border border-dashed border-white/15 px-4 py-3 text-left"
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
    <div className="mb-5 rounded-control border border-white/10 p-4">
      <Field label="Paste the message">
        <textarea
          rows={4}
          value={message}
          onChange={(e) => setMessage(e.target.value)}
          placeholder="*165*S*200000 RWF transferred to …"
          className="min-h-[96px] w-full rounded-control border border-white/10 bg-background-secondary px-3 py-2 text-sm text-content-primary placeholder:text-content-muted focus:border-accent focus:outline-none"
        />
      </Field>

      {result && !result.understood && (
        <p className="mt-3 text-xs text-semantic-warning">
          {/* Explicit rather than silent: a form that quietly stays blank looks
              like the button did nothing. */}
          That message was not recognised. Fill the form in below instead.
        </p>
      )}

      {result?.understood && (
        <p className="mt-3 text-xs text-semantic-income">
          Filled in the {readableFields(result.matched)}.
          {result.balance_after
            ? ` The message says the balance is now ${formatMoney(
                result.balance_after,
                result.currency ?? "RWF",
              )}.`
            : ""}{" "}
          Check it, then add.
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
