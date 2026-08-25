"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { FormEvent, Suspense, useEffect, useState } from "react";

import { Account, Category, MontraApiError, montra } from "@/lib/api";
import { PageHeader } from "@/components/shell";
import { TransferForm } from "@/components/transfer-form";
import { AttachmentPicker } from "@/components/attachment-picker";
import { SmsPaste } from "@/components/sms-paste";
import { AmountInput, Button, Card, ErrorNotice, Field, Input, Select } from "@/components/ui";
import { accountForChannel, toLocalInputValue } from "@/lib/format";

/**
 * Add income or expense.
 *
 * The form never decides a ledger direction; it sends a transaction type and
 * the backend's posting engine resolves the effect from the account's nature.
 */
function AddTransactionForm() {
  const router = useRouter();
  const params = useSearchParams();

  const [type, setType] = useState<"EXPENSE" | "INCOME" | "TRANSFER">("EXPENSE");
  const [accounts, setAccounts] = useState<Account[]>([]);
  const [categories, setCategories] = useState<Category[]>([]);
  const [form, setForm] = useState({
    account_id: params.get("account") ?? "",
    amount: "",
    occurred_at: toLocalInputValue(),
    category_id: "",
    description: "",
    merchant: "",
    fee_amount: "",
  });
  const [files, setFiles] = useState<File[]>([]);
  const [transferPrefill, setTransferPrefill] = useState<{
    amount: string | null;
    fee: string | null;
    occurredAt: string | null;
    channel: "MOBILE_MONEY" | "BANK" | null;
    sourceId: string | null;
    destinationId: string | null;
  } | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    montra.accounts().then((list) => {
      setAccounts(list);
      setForm((f) => ({ ...f, account_id: f.account_id || list[0]?.id || "" }));
    });
  }, []);

  useEffect(() => {
    if (type === "TRANSFER") return;
    montra.categories(type).then(setCategories);
    setForm((f) => ({ ...f, category_id: "" }));
  }, [type]);

  const selected = accounts.find((a) => a.id === form.account_id);

  function update(key: keyof typeof form, value: string) {
    setForm((f) => ({ ...f, [key]: value }));
  }

  async function submit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const created = await montra.createTransaction({
        transaction_type: type,
        account_id: form.account_id,
        amount: form.amount,
        occurred_at: form.occurred_at,
        category_id: form.category_id || null,
        description: form.description || null,
        merchant: form.merchant || null,
        // Sent alongside rather than added in: the backend posts it as its own
        // line, so the amount above stays the cost of the thing itself.
        fee_amount: type === "EXPENSE" && form.fee_amount ? form.fee_amount : null,
      });

      // The transaction is saved by now. If a receipt fails to upload, that is
      // a separate, smaller problem — and saying "could not save" would be a
      // lie that costs the user a duplicate entry.
      try {
        for (const file of files) {
          await montra.uploadAttachment(created.id, file);
        }
      } catch {
        setError("The transaction was saved, but the receipt could not be attached.");
        setFiles([]);
        setBusy(false);
        return;
      }

      router.push("/transactions");
      router.refresh();
    } catch (err) {
      setError(
        err instanceof MontraApiError ? err.message : "Could not save the transaction.",
      );
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <PageHeader title="Add transaction"
        icon="plus" />

      {/* Above the tabs, because the message decides which tab applies. Asking
          the user to choose first and then pasting something that contradicts
          them would be the wrong way round. */}
      <SmsPaste
        onParsed={(parsed) => {
          if (parsed.transaction_type) setType(parsed.transaction_type);
          if (parsed.transaction_type === "TRANSFER") {
            setTransferPrefill({
              amount: parsed.amount,
              fee: parsed.fee_amount,
              occurredAt: parsed.occurred_at,
              channel: parsed.channel,
              sourceId: parsed.source_account_id,
              destinationId: parsed.destination_account_id,
            });
            return;
          }
          // A resolved account number beats a guess from the wording.
          const resolved =
            parsed.source_account_id ?? parsed.destination_account_id ?? null;
          const onAccount = accountForChannel(accounts, parsed.channel);
          setForm((f) => ({
            ...f,
            amount: parsed.amount ?? f.amount,
            fee_amount: parsed.fee_amount ?? f.fee_amount,
            // Held in full, seconds included: the input shows minutes but the
            // value submitted is the moment the message stated.
            occurred_at: parsed.occurred_at ?? f.occurred_at,
            description: parsed.counterparty ?? f.description,
            // A MoMo message is about the wallet; picking it saves the step
            // the user would otherwise take every single time.
            account_id: resolved ?? onAccount?.id ?? f.account_id,
          }));
        }}
      />

      {/* Money leaving, money arriving, money moving between your own
          accounts — all three are "recording something", so all three start
          here. A transfer is not a transaction the ledger can post directly,
          which is why it swaps in a different form rather than another field. */}
      <div className="mb-5 grid grid-cols-3 gap-2 rounded-control bg-background-secondary p-1">
        {(
          [
            ["EXPENSE", "Expense", "bg-semantic-expense/15 text-semantic-expense"],
            ["INCOME", "Income", "bg-semantic-income/15 text-semantic-income"],
            ["TRANSFER", "Transfer", "bg-semantic-transfer/15 text-semantic-transfer"],
          ] as const
        ).map(([value, label, active]) => (
          <button
            key={value}
            onClick={() => setType(value)}
            aria-pressed={type === value}
            className={`pressable min-h-[44px] rounded-[10px] text-sm font-semibold transition ${
              type === value ? active : "text-content-secondary"
            }`}
          >
            {label}
          </button>
        ))}
      </div>

      {type === "TRANSFER" && (
        <TransferForm
          defaultSourceId={params.get("account") ?? ""}
          prefill={transferPrefill ?? undefined}
        />
      )}
      {type !== "TRANSFER" && (
      <Card>
        <form onSubmit={submit} className="space-y-4">
          {error && <ErrorNotice message={error} />}
          <Field label="Amount">
            <AmountInput
              required
              placeholder="0"
              value={form.amount}
              onChange={(e) => update("amount", e.target.value)}
            />
          </Field>
          <Field
            label="Account"
            hint={
              selected?.account_nature === "LIABILITY" && type === "EXPENSE"
                ? "This card purchase will increase the amount you owe."
                : undefined
            }
          >
            <Select
              required
              value={form.account_id}
              onChange={(e) => update("account_id", e.target.value)}
            >
              {accounts.map((a) => (
                <option key={a.id} value={a.id}>
                  {a.name}
                </option>
              ))}
            </Select>
          </Field>
          <Field label="Category">
            <Select
              value={form.category_id}
              onChange={(e) => update("category_id", e.target.value)}
            >
              <option value="">Uncategorised</option>
              {categories.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.name}
                </option>
              ))}
            </Select>
          </Field>
          <Field label="When" hint="Defaults to now. Change it for something you are recording after the fact.">
            <Input
              type="datetime-local"
              required
              value={form.occurred_at}
              onChange={(e) => update("occurred_at", e.target.value)}
            />
          </Field>
          {type === "EXPENSE" && (
            <Field
              label="Fee"
              hint="Optional. Recorded as its own line, so the amount above stays what the purchase cost."
            >
              <AmountInput
                placeholder="0"
                value={form.fee_amount}
                onChange={(e) => update("fee_amount", e.target.value)}
              />
            </Field>
          )}
          <Field label="Description">
            <Input
              value={form.description}
              placeholder="Simba Supermarket"
              onChange={(e) => update("description", e.target.value)}
            />
          </Field>
          <Field label="Receipt" hint="Optional. Images or PDF, up to 10MB.">
            <AttachmentPicker
              files={files}
              onChange={setFiles}
              onError={setError}
              disabled={busy}
            />
          </Field>
          <div className="flex gap-3">
            <Button type="submit" disabled={busy || !form.account_id} className="flex-1">
              {busy ? "Saving…" : `Add ${type === "EXPENSE" ? "expense" : "income"}`}
            </Button>
            <Button variant="secondary" onClick={() => router.back()}>
              Cancel
            </Button>
          </div>
        </form>
      </Card>
      )}
    </>
  );
}

export default function Page() {
  return (
    <Suspense fallback={null}>
      <AddTransactionForm />
    </Suspense>
  );
}
