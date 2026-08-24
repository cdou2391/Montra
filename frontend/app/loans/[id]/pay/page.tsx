"use client";

import { useParams, useRouter } from "next/navigation";
import { FormEvent, useEffect, useMemo, useState } from "react";

import { Account, Loan, MontraApiError, montra } from "@/lib/api";
import { AppShell, PageHeader } from "@/components/shell";
import { Providers } from "@/app/providers";
import { RequireSession } from "@/components/session";
import { formatMoney } from "@/lib/format";
import { AmountInput, Button, Card, ErrorNotice, Field, Input, Select, Skeleton } from "@/components/ui";

/**
 * Record a loan payment.
 *
 * The split is the whole point, so the form shows it being reconciled live
 * rather than letting the user discover a mismatch on submit.
 */
function RecordPayment() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();

  const [loan, setLoan] = useState<Loan | null>(null);
  const [accounts, setAccounts] = useState<Account[]>([]);
  const [form, setForm] = useState({
    account_id: "",
    payment_date: new Date().toISOString().slice(0, 10),
    total_amount: "",
    interest_amount: "0",
    fee_amount: "0",
  });
  const [idempotencyKey] = useState(() => crypto.randomUUID());
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    montra.loan(id).then((l) => {
      setLoan(l);
      setForm((f) => ({
        ...f,
        total_amount: f.total_amount || l.expected_payment_amount || "",
      }));
    });
    montra.accounts().then((list) => {
      // Loans are settled with money you hold, never with a card.
      const assets = list.filter((a) => a.account_nature === "ASSET");
      setAccounts(assets);
      setForm((f) => ({ ...f, account_id: f.account_id || assets[0]?.id || "" }));
    });
  }, [id]);

  // Principal is derived, never typed: it is whatever is left after interest
  // and fees, which is what makes the allocation always add up.
  const principal = useMemo(() => {
    const total = Number(form.total_amount || 0);
    const interest = Number(form.interest_amount || 0);
    const fee = Number(form.fee_amount || 0);
    return total - interest - fee;
  }, [form.total_amount, form.interest_amount, form.fee_amount]);

  const outstanding = Number(loan?.outstanding_principal ?? 0);
  const principalTooHigh = principal > outstanding;
  const principalNegative = principal < 0;

  function update(key: keyof typeof form, value: string) {
    setForm((f) => ({ ...f, [key]: value }));
  }

  async function submit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await montra.recordLoanPayment(
        id,
        {
          account_id: form.account_id,
          payment_date: form.payment_date,
          total_amount: form.total_amount,
          principal_amount: principal.toFixed(2),
          interest_amount: form.interest_amount || "0",
          fee_amount: form.fee_amount || "0",
        },
        idempotencyKey,
      );
      router.push(`/loans/${id}`);
      router.refresh();
    } catch (err) {
      setError(err instanceof MontraApiError ? err.message : "Could not record the payment.");
    } finally {
      setBusy(false);
    }
  }

  if (!loan) {
    return (
      <AppShell>
        <PageHeader title="Record payment" icon="handshake" />
        <Skeleton className="h-56 w-full" />
      </AppShell>
    );
  }

  const owed = loan.direction === "PAYABLE";
  const money = (v: number | string) => formatMoney(String(v), loan.currency);

  return (
    <AppShell>
      <PageHeader title={owed ? "Record payment" : "Record repayment"} icon="handshake" />

      <Card className="mb-4">
        <p className="font-medium">{loan.name}</p>
        <p className="tabular mt-1 text-lg font-bold">
          {money(loan.outstanding_principal)}
        </p>
        <p className="mt-0.5 text-xs text-content-secondary">
          {owed ? "outstanding" : "still owed to you"}
        </p>
      </Card>

      <Card>
        <form onSubmit={submit} className="space-y-4">
          {error && <ErrorNotice message={error} />}

          <Field label={owed ? "Pay from" : "Receive into"}>
            <Select
              required
              value={form.account_id}
              onChange={(e) => update("account_id", e.target.value)}
            >
              {accounts.map((a) => (
                <option key={a.id} value={a.id}>
                  {a.name} — {formatMoney(a.balance, a.currency)}
                </option>
              ))}
            </Select>
          </Field>

          <Field label="Total amount" hint="The full amount that moves.">
            <AmountInput
              required
              placeholder="0"
              value={form.total_amount}
              onChange={(e) => update("total_amount", e.target.value)}
            />
          </Field>

          <div className="grid grid-cols-2 gap-3">
            <Field label="Interest" hint={owed ? "Counts as expense" : "Counts as income"}>
              <AmountInput
                value={form.interest_amount}
                onChange={(e) => update("interest_amount", e.target.value)}
              />
            </Field>
            <Field label="Fees" hint={owed ? "Counts as expense" : "Counts as income"}>
              <AmountInput
                value={form.fee_amount}
                onChange={(e) => update("fee_amount", e.target.value)}
              />
            </Field>
          </div>

          {/* Live reconciliation of the split. */}
          <div
            aria-live="polite"
            className="rounded-control border border-white/10 bg-background-secondary p-4"
          >
            <p className="text-xs uppercase tracking-wide text-content-muted">
              Goes to principal
            </p>
            <p
              className={`tabular mt-1 text-lg font-semibold ${
                principalNegative || principalTooHigh
                  ? "text-semantic-expense"
                  : "text-content-primary"
              }`}
            >
              {money(principal.toFixed(2))}
            </p>
            {principalNegative ? (
              <p className="mt-2 text-xs text-semantic-expense">
                Interest and fees exceed the total.
              </p>
            ) : principalTooHigh ? (
              <p className="mt-2 text-xs text-semantic-expense">
                That is more principal than the {money(outstanding)} remaining.
              </p>
            ) : (
              <p className="mt-2 text-xs text-content-secondary">
                {owed
                  ? "Principal settles debt you already carried, so it is not counted as spending. Interest and fees are."
                  : "Principal is your own money coming back, so it is not income. Interest and fees are."}
              </p>
            )}
          </div>

          <Field label="Date">
            <Input
              type="date"
              required
              value={form.payment_date}
              onChange={(e) => update("payment_date", e.target.value)}
            />
          </Field>

          <div className="flex gap-3">
            <Button
              type="submit"
              disabled={
                busy ||
                !form.account_id ||
                !form.total_amount ||
                principalNegative ||
                principalTooHigh
              }
              className="flex-1"
            >
              {busy ? "Recording…" : "Record payment"}
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
        <RecordPayment />
      </RequireSession>
    </Providers>
  );
}
