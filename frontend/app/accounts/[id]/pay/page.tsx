"use client";

import { useParams, useRouter } from "next/navigation";
import { FormEvent, useEffect, useState } from "react";

import { Account, CardSummary, MontraApiError, montra } from "@/lib/api";
import { AppShell, PageHeader } from "@/components/shell";
import { Providers } from "@/app/providers";
import { RequireSession } from "@/components/session";
import { formatMoney, toLocalInputValue } from "@/lib/format";
import { AmountInput, Button, Card, ErrorNotice, Field, Input, Select } from "@/components/ui";

/**
 * Card payment (Phase 9) and prepaid top-up (Phase 10).
 *
 * Both are transfers. The page says so plainly, because the single most common
 * misunderstanding about a card payment is thinking it is a second expense.
 */
function PayCard() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();

  const [card, setCard] = useState<Account | null>(null);
  const [summary, setSummary] = useState<CardSummary | null>(null);
  const [sources, setSources] = useState<Account[]>([]);
  const [form, setForm] = useState({
    source_account_id: "",
    amount: "",
    occurred_at: toLocalInputValue(),
  });
  const [idempotencyKey] = useState(() => crypto.randomUUID());
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const isCredit = card?.account_type === "CREDIT_CARD";

  useEffect(() => {
    montra.account(id).then((a) => {
      setCard(a);
      if (a.account_type === "CREDIT_CARD") {
        montra.cardSummary(id).then(setSummary).catch(() => setSummary(null));
      }
    });
    montra.accounts().then((list) => {
      // A card is paid from money you hold, never from another liability.
      const assets = list.filter((a) => a.account_nature === "ASSET" && a.id !== id);
      setSources(assets);
      setForm((f) => ({ ...f, source_account_id: f.source_account_id || assets[0]?.id || "" }));
    });
  }, [id]);

  function update(key: keyof typeof form, value: string) {
    setForm((f) => ({ ...f, [key]: value }));
  }

  async function submit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    const payload = {
      source_account_id: form.source_account_id,
      amount: form.amount,
      occurred_at: form.occurred_at,
    };
    try {
      if (isCredit) {
        await montra.payCard(id, payload, idempotencyKey);
      } else {
        await montra.topUpPrepaid(id, payload, idempotencyKey);
      }
      router.push(`/accounts/${id}`);
      router.refresh();
    } catch (err) {
      setError(err instanceof MontraApiError ? err.message : "Could not complete the payment.");
    } finally {
      setBusy(false);
    }
  }

  const title = isCredit ? `Pay ${card?.name ?? "card"}` : `Top up ${card?.name ?? "card"}`;

  const shortcuts = isCredit
    ? [
        summary?.minimum_payment
          ? { label: "Minimum", value: summary.minimum_payment }
          : null,
        summary?.statement_balance
          ? { label: "Statement", value: summary.statement_balance }
          : null,
        summary?.outstanding_balance
          ? { label: "Full balance", value: summary.outstanding_balance }
          : null,
      ].filter((s): s is { label: string; value: string } => s !== null)
    : [];

  return (
    <AppShell>
      <PageHeader title={title} icon="creditCard" />

      {isCredit && summary && (
        <Card className="mb-4">
          <p className="text-xs uppercase tracking-wide text-content-muted">Outstanding</p>
          <p className="tabular mt-1 text-xl font-bold">
            {formatMoney(summary.outstanding_balance, summary.currency)}
          </p>
        </Card>
      )}

      <Card>
        <form onSubmit={submit} className="space-y-4">
          {error && <ErrorNotice message={error} />}

          {sources.length === 0 ? (
            <p className="text-sm text-content-secondary">
              You need an account with money in it before you can pay this card.
            </p>
          ) : (
            <>
              <Field label="Pay from">
                <Select
                  required
                  value={form.source_account_id}
                  onChange={(e) => update("source_account_id", e.target.value)}
                >
                  {sources.map((a) => (
                    <option key={a.id} value={a.id}>
                      {a.name} — {formatMoney(a.balance, a.currency)}
                    </option>
                  ))}
                </Select>
              </Field>

              <Field label="Amount">
                <AmountInput
                  required
                  placeholder="0"
                  value={form.amount}
                  onChange={(e) => update("amount", e.target.value)}
                />
              </Field>

              {shortcuts.length > 0 && (
                <div className="flex flex-wrap gap-2">
                  {shortcuts.map((s) => (
                    <button
                      key={s.label}
                      type="button"
                      onClick={() => update("amount", s.value)}
                      className="min-h-[36px] rounded-full border border-white/10 px-3 text-xs text-content-secondary transition hover:bg-white/5 hover:text-content-primary"
                    >
                      {s.label}
                    </button>
                  ))}
                </div>
              )}

              <Field label="When">
                <Input
                  type="datetime-local"
                  required
                  value={form.occurred_at}
                  onChange={(e) => update("occurred_at", e.target.value)}
                />
              </Field>

              <p className="rounded-control border border-white/10 bg-background-secondary px-4 py-3 text-xs text-content-secondary">
                {isCredit
                  ? "This moves money you already owed. Your cash goes down, the balance owed goes down by the same amount, and your net worth does not change. It is not counted as spending."
                  : "A top-up moves money between your own accounts. Your net worth does not change and it is not counted as spending."}
              </p>

              <div className="flex gap-3">
                <Button
                  type="submit"
                  disabled={busy || !form.amount || !form.source_account_id}
                  className="flex-1"
                >
                  {busy ? "Sending…" : isCredit ? "Make payment" : "Top up"}
                </Button>
                <Button variant="secondary" onClick={() => router.back()}>
                  Cancel
                </Button>
              </div>
            </>
          )}
        </form>
      </Card>
    </AppShell>
  );
}

export default function Page() {
  return (
    <Providers>
      <RequireSession>
        <PayCard />
      </RequireSession>
    </Providers>
  );
}
