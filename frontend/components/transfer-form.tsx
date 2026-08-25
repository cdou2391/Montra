"use client";

/**
 * Moving money between two accounts.
 *
 * Lives here rather than on a page because it is reachable two ways — the
 * Transfer tab on Add, and the standalone /transfer route that account screens
 * link to with a source pre-selected. One form, so the two cannot drift.
 */

import { useRouter } from "next/navigation";
import { FormEvent, useEffect, useState } from "react";

import { Account, MontraApiError, montra } from "@/lib/api";
import { AttachmentPicker } from "@/components/attachment-picker";
import { AmountInput, Button, Card, ErrorNotice, Field, Input, Select } from "@/components/ui";
import { accountForChannel, toLocalInputValue } from "@/lib/format";

export function TransferForm({
  defaultSourceId = "",
  prefill,
}: {
  defaultSourceId?: string;
  /** Values read from a pasted message. The accounts are still the user's to
      choose: a notification says money moved, not which two of your accounts
      it moved between. */
  prefill?: {
    amount?: string | null;
    fee?: string | null;
    occurredAt?: string | null;
    channel?: "MOBILE_MONEY" | "BANK" | null;
  };
}) {
  const router = useRouter();

  const [accounts, setAccounts] = useState<Account[]>([]);
  const [form, setForm] = useState({
    source_account_id: defaultSourceId,
    destination_account_id: "",
    source_amount: "",
    fee_amount: "",
    occurred_at: toLocalInputValue(),
    notes: "",
  });

  useEffect(() => {
    if (!prefill) return;
    setForm((f) => {
      // Only the sending side: the message names the account it came out of,
      // and says nothing reliable about which of yours it went into.
      const from = accountForChannel(accounts, prefill.channel ?? null);
      const source = from?.id ?? f.source_account_id;
      return {
        ...f,
        source_amount: prefill.amount ?? f.source_amount,
        fee_amount: prefill.fee ?? f.fee_amount,
        occurred_at: prefill.occurredAt ?? f.occurred_at,
        source_account_id: source,
        // The destination cannot stay equal to the new source.
        destination_account_id:
          f.destination_account_id === source ? "" : f.destination_account_id,
      };
    });
  }, [prefill, accounts]);
  // Generated once per form instance so a double submit cannot post twice.
  const [idempotencyKey] = useState(() => crypto.randomUUID());
  const [files, setFiles] = useState<File[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    montra.accounts().then((list) => {
      setAccounts(list);
      setForm((f) => ({
        ...f,
        source_account_id: f.source_account_id || list[0]?.id || "",
        destination_account_id: f.destination_account_id || list[1]?.id || "",
      }));
    });
  }, []);

  const source = accounts.find((a) => a.id === form.source_account_id);
  const destination = accounts.find((a) => a.id === form.destination_account_id);
  const isRepayment = destination?.account_nature === "LIABILITY";

  function update(key: keyof typeof form, value: string) {
    setForm((f) => ({ ...f, [key]: value }));
  }

  async function submit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const transfer = await montra.createTransfer(
        {
          source_account_id: form.source_account_id,
          destination_account_id: form.destination_account_id,
          source_amount: form.source_amount,
          destination_amount: form.source_amount,
          occurred_at: form.occurred_at,
          notes: form.notes || null,
          // Charged to the sender and posted as its own line, so the amount
          // above stays what actually arrived.
          fee_amount: form.fee_amount || null,
        },
        idempotencyKey,
      );

      // The money has moved by this point. A failed receipt must not read as a
      // failed transfer, so it is reported on its own terms.
      try {
        for (const file of files) {
          await montra.uploadTransferAttachment(transfer.id, file);
        }
      } catch {
        setError("The transfer went through, but the receipt could not be attached.");
        setFiles([]);
        setBusy(false);
        return;
      }

      router.push("/transactions");
      router.refresh();
    } catch (err) {
      setError(err instanceof MontraApiError ? err.message : "Could not make the transfer.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card>
      <form onSubmit={submit} className="space-y-4">
        {error && <ErrorNotice message={error} />}
        <Field label="From">
          <Select
            required
            value={form.source_account_id}
            onChange={(e) => update("source_account_id", e.target.value)}
          >
            {accounts.map((a) => (
              <option key={a.id} value={a.id}>
                {a.name}
              </option>
            ))}
          </Select>
        </Field>
        <Field
          label="To"
          hint={
            isRepayment
              ? "Paying this card reduces what you owe; your net worth does not change."
              : undefined
          }
        >
          <Select
            required
            value={form.destination_account_id}
            onChange={(e) => update("destination_account_id", e.target.value)}
          >
            {accounts
              .filter((a) => a.id !== form.source_account_id)
              .map((a) => (
                <option key={a.id} value={a.id}>
                  {a.name}
                </option>
              ))}
          </Select>
        </Field>
        <Field label="Amount" hint={source ? `In ${source.currency}` : undefined}>
          <AmountInput
            required
            placeholder="0"
            value={form.source_amount}
            onChange={(e) => update("source_amount", e.target.value)}
          />
        </Field>
        <Field
          label="Fee"
          hint="Optional. Charged to the sending account as its own line; the amount above is what arrives."
        >
          <AmountInput
            placeholder="0"
            value={form.fee_amount}
            onChange={(e) => update("fee_amount", e.target.value)}
          />
        </Field>
        <Field label="When" hint="Defaults to now.">
          <Input
            type="datetime-local"
            required
            value={form.occurred_at}
            onChange={(e) => update("occurred_at", e.target.value)}
          />
        </Field>
        <Field label="Note">
          <Input value={form.notes} onChange={(e) => update("notes", e.target.value)} />
        </Field>
        <Field label="Proof of payment" hint="Optional. Images or PDF, up to 10MB.">
          <AttachmentPicker
            files={files}
            onChange={setFiles}
            onError={setError}
            disabled={busy}
            label="Attach proof"
          />
        </Field>
        <div className="flex gap-3">
          <Button
            type="submit"
            disabled={busy || !form.destination_account_id}
            className="flex-1"
          >
            {busy ? "Transferring…" : "Confirm transfer"}
          </Button>
          <Button variant="secondary" onClick={() => router.back()}>
            Cancel
          </Button>
        </div>
      </form>
    </Card>
  );
}
