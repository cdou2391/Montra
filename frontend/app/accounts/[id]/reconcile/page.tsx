"use client";

import { useParams, useRouter } from "next/navigation";
import { FormEvent, useEffect, useState } from "react";

import { Account, MontraApiError, ReconciliationPreview, montra } from "@/lib/api";
import { AppShell, PageHeader } from "@/components/shell";
import { Providers } from "@/app/providers";
import { RequireSession } from "@/components/session";
import { MoneyValue } from "@/components/financial";
import { formatMoney, toLocalInputValue } from "@/lib/format";
import { AmountInput, Button, Card, ErrorNotice, Field, Input, Skeleton } from "@/components/ui";

/**
 * Reconciliation (Implementation Plan Phase 8).
 *
 * Montra records the difference as an explicit financial event. It never
 * rewrites history or edits the opening balance, so the screen shows the user
 * exactly what will be written before they commit to it.
 */
function Reconcile() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();

  const [account, setAccount] = useState<Account | null>(null);
  const [actual, setActual] = useState("");
  const [occurredAt, setOccurredAt] = useState(toLocalInputValue());
  const [reason, setReason] = useState("");
  const [preview, setPreview] = useState<ReconciliationPreview | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    montra.account(id).then(setAccount).catch(() => setAccount(null));
  }, [id]);

  // Ask the server what the adjustment would be, rather than doing money
  // arithmetic in the browser.
  useEffect(() => {
    if (!actual.trim()) {
      setPreview(null);
      return;
    }
    const timer = setTimeout(() => {
      montra
        .reconciliationPreview(id, actual)
        .then(setPreview)
        .catch(() => setPreview(null));
    }, 300);
    return () => clearTimeout(timer);
  }, [id, actual]);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await montra.reconcile(id, {
        actual_balance: actual,
        occurred_at: occurredAt,
        reason: reason || null,
      });
      router.push(`/accounts/${id}`);
      router.refresh();
    } catch (err) {
      setError(err instanceof MontraApiError ? err.message : "Could not reconcile.");
    } finally {
      setBusy(false);
    }
  }

  if (!account) {
    return (
      <AppShell>
        <PageHeader title="Reconcile" />
        <Skeleton className="h-48 w-full" />
      </AppShell>
    );
  }

  const isLiability = account.account_nature === "LIABILITY";
  const matches = preview?.direction === null;

  return (
    <AppShell>
      <PageHeader title={`Reconcile ${account.name}`} />

      <Card className="mb-4">
        <p className="text-xs uppercase tracking-wide text-content-muted">
          {isLiability ? "Montra says you owe" : "Montra says you have"}
        </p>
        <p className="mt-1">
          <MoneyValue amount={account.balance} currency={account.currency} size="value" />
        </p>
        <p className="mt-2 text-xs text-content-secondary">
          If your {isLiability ? "statement" : "bank"} disagrees, enter the real figure below.
          Montra records the difference as its own entry — your history and opening balance stay
          exactly as they are.
        </p>
      </Card>

      <Card>
        <form onSubmit={submit} className="space-y-4">
          {error && <ErrorNotice message={error} />}

          <Field
            label={isLiability ? "Actual balance owed" : "Actual balance"}
            hint={`In ${account.currency}.`}
          >
            <AmountInput
              required
              placeholder="0"
              value={actual}
              onChange={(e) => setActual(e.target.value)}
            />
          </Field>

          {preview && (
            <div
              aria-live="polite"
              className="rounded-control border border-white/10 bg-background-secondary p-4"
            >
              {matches ? (
                <p className="text-sm text-content-secondary">
                  That matches what Montra already has. Nothing will be recorded.
                </p>
              ) : (
                <>
                  <p className="text-xs uppercase tracking-wide text-content-muted">
                    Adjustment to record
                  </p>
                  <p
                    className={`tabular mt-1 text-lg font-semibold ${
                      preview.direction === "INCREASE"
                        ? "text-semantic-income"
                        : "text-semantic-expense"
                    }`}
                  >
                    {preview.direction === "INCREASE" ? "+" : "−"}
                    {formatMoney(preview.difference, preview.currency)}
                  </p>
                  <p className="mt-2 text-xs text-content-secondary">
                    {formatMoney(preview.current_balance, preview.currency)} →{" "}
                    {formatMoney(preview.actual_balance, preview.currency)}
                  </p>
                </>
              )}
            </div>
          )}

          <Field label="As of" hint="When you observed this balance.">
            <Input
              type="datetime-local"
              required
              value={occurredAt}
              onChange={(e) => setOccurredAt(e.target.value)}
            />
          </Field>

          <Field label="Reason" hint="Optional, but future you will thank present you.">
            <Input
              placeholder="Matched bank statement"
              value={reason}
              onChange={(e) => setReason(e.target.value)}
            />
          </Field>

          <div className="flex gap-3">
            <Button type="submit" disabled={busy || !actual.trim()} className="flex-1">
              {busy ? "Recording…" : matches ? "Nothing to record" : "Record adjustment"}
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
        <Reconcile />
      </RequireSession>
    </Providers>
  );
}
