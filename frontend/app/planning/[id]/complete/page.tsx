"use client";

import { useParams, useRouter } from "next/navigation";
import { FormEvent, useEffect, useState } from "react";

import { Account, MontraApiError, PlannedTransaction, montra } from "@/lib/api";
import { AppShell, PageHeader } from "@/components/shell";
import { Providers } from "@/app/providers";
import { RequireSession } from "@/components/session";
import { formatMoney, toLocalInputValue } from "@/lib/format";
import { AmountInput, Button, Card, ErrorNotice, Field, Input, Select, Skeleton } from "@/components/ui";

/**
 * Completing a planned item — the moment it becomes a real ledger entry.
 *
 * Amount, time and account all default from the plan, because the common case
 * is that the bill arrived exactly as expected.
 */
function CompletePlanned() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();

  const [planned, setPlanned] = useState<PlannedTransaction | null>(null);
  const [accounts, setAccounts] = useState<Account[]>([]);
  const [form, setForm] = useState({ amount: "", occurred_at: "", account_id: "" });
  // One key per form instance: a double tap cannot post twice.
  const [idempotencyKey] = useState(() => crypto.randomUUID());
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    montra
      .planned()
      .then((rows) => {
        const found = rows.find((r) => r.id === id) ?? null;
        setPlanned(found);
        if (found) {
          setForm({
            amount: found.amount,
            occurred_at: toLocalInputValue(new Date(found.expected_at)),
            account_id: found.account?.id ?? "",
          });
        }
      })
      .catch(() => setPlanned(null));
    montra.accounts().then(setAccounts);
  }, [id]);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await montra.completePlanned(
        id,
        {
          actual_amount: form.amount,
          actual_occurred_at: form.occurred_at,
          account_id: form.account_id || null,
        },
        idempotencyKey,
      );
      router.push("/planning");
      router.refresh();
    } catch (err) {
      setError(err instanceof MontraApiError ? err.message : "Could not complete this.");
    } finally {
      setBusy(false);
    }
  }

  if (!planned) {
    return (
      <AppShell>
        <PageHeader title="Complete" icon="calendar" />
        <Skeleton className="h-48 w-full" />
      </AppShell>
    );
  }

  const isIncome = planned.planned_type === "INCOME";

  return (
    <AppShell>
      <PageHeader title={isIncome ? "Mark as received" : "Mark as paid"} icon="calendar" />

      <Card className="mb-4">
        <p className="font-medium">{planned.description}</p>
        <p className="tabular mt-1 text-lg font-bold">
          {formatMoney(planned.amount, planned.currency)}
        </p>
        <p className="mt-1 text-xs text-content-secondary">
          Planned for {planned.occurrence_date}
        </p>
      </Card>

      <Card>
        <form onSubmit={submit} className="space-y-4">
          {error && <ErrorNotice message={error} />}

          <Field
            label={isIncome ? "Amount received" : "Amount paid"}
            hint="Change it if the real figure differed."
          >
            <AmountInput
              required
              value={form.amount}
              onChange={(e) => setForm((f) => ({ ...f, amount: e.target.value }))}
            />
          </Field>

          <Field label={isIncome ? "Received at" : "Paid at"}>
            <Input
              type="datetime-local"
              required
              value={form.occurred_at}
              onChange={(e) => setForm((f) => ({ ...f, occurred_at: e.target.value }))}
            />
          </Field>

          <Field label="Account" hint="Change it if the money moved elsewhere.">
            <Select
              value={form.account_id}
              onChange={(e) => setForm((f) => ({ ...f, account_id: e.target.value }))}
            >
              {accounts.map((a) => (
                <option key={a.id} value={a.id}>
                  {a.name}
                </option>
              ))}
            </Select>
          </Field>

          <p className="rounded-control border border-white/10 bg-background-secondary px-4 py-3 text-xs text-content-secondary">
            This records a real {isIncome ? "income" : "expense"} against your balance. The plan
            is marked complete and its reminder is cancelled.
          </p>

          <div className="flex gap-3">
            <Button type="submit" disabled={busy} className="flex-1">
              {busy ? "Recording…" : isIncome ? "Confirm received" : "Confirm paid"}
            </Button>
            <Button variant="secondary" onClick={() => router.back()}>
              Cancel
            </Button>
          </div>
        </form>
      </Card>
    </AppShell>
  );
}

export default function Page() {
  return (
    <Providers>
      <RequireSession>
        <CompletePlanned />
      </RequireSession>
    </Providers>
  );
}
