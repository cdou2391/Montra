"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { FormEvent, Suspense, useState } from "react";

import { MontraApiError, montra } from "@/lib/api";
import { AppShell, PageHeader } from "@/components/shell";
import { Providers } from "@/app/providers";
import { RequireSession, useSession } from "@/components/session";
import { AmountInput, Button, Card, ErrorNotice, Field, Input, Select } from "@/components/ui";
import { toLocalInputValue } from "@/lib/format";

const ACCOUNT_TYPES = [
  { value: "CHECKING", label: "Bank — current" },
  { value: "SAVINGS", label: "Bank — savings" },
  { value: "CASH", label: "Cash" },
  { value: "MOBILE_MONEY", label: "Mobile money" },
  { value: "CREDIT_CARD", label: "Credit card" },
  { value: "PREPAID_CARD", label: "Prepaid card" },
  { value: "INVESTMENT", label: "Investment" },
  { value: "OTHER", label: "Other" },
];

function NewAccountForm() {
  const router = useRouter();
  const params = useSearchParams();
  const { user } = useSession();
  const onboarding = params.get("onboarding") === "1";

  const [form, setForm] = useState({
    name: "",
    account_type: "CHECKING",
    currency: user?.base_currency ?? "RWF",
    opening_balance: "0",
    opening_balance_at: toLocalInputValue(),
    account_identifier: "",
  });
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const isLiability = form.account_type === "CREDIT_CARD";

  function update(key: keyof typeof form, value: string) {
    setForm((f) => ({ ...f, [key]: value }));
  }

  async function submit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await montra.createAccount({
        ...form,
        account_identifier: form.account_identifier || null,
      });
      router.push(onboarding ? "/" : "/accounts");
      router.refresh();
    } catch (err) {
      setError(
        err instanceof MontraApiError ? err.message : "Could not create the account.",
      );
    } finally {
      setBusy(false);
    }
  }

  return (
    <AppShell>
      <PageHeader title={onboarding ? "Add your first account" : "Add account"} />
      <Card>
        <form onSubmit={submit} className="space-y-4">
          {error && <ErrorNotice message={error} />}
          <Field label="Account name">
            <Input
              required
              placeholder="BK Current"
              value={form.name}
              onChange={(e) => update("name", e.target.value)}
            />
          </Field>
          <Field label="Type">
            <Select
              value={form.account_type}
              onChange={(e) => update("account_type", e.target.value)}
            >
              {ACCOUNT_TYPES.map((t) => (
                <option key={t.value} value={t.value}>
                  {t.label}
                </option>
              ))}
            </Select>
          </Field>
          <Field label="Currency">
            <Input
              required
              maxLength={3}
              value={form.currency}
              onChange={(e) => update("currency", e.target.value.toUpperCase())}
            />
          </Field>
          <Field
            label={isLiability ? "Current balance owed" : "Opening balance"}
            hint={
              isLiability
                ? "How much you currently owe on this card."
                : "What the account holds as of the date below."
            }
          >
            <AmountInput
              required
              value={form.opening_balance}
              onChange={(e) => update("opening_balance", e.target.value)}
            />
          </Field>
          <Field label="As of" hint="The moment this balance was accurate.">
            <Input
              type="datetime-local"
              required
              value={form.opening_balance_at}
              onChange={(e) => update("opening_balance_at", e.target.value)}
            />
          </Field>
          <Field label="Last 4 digits" hint="Optional. Only the last four are ever shown.">
            <Input
              maxLength={20}
              value={form.account_identifier}
              onChange={(e) => update("account_identifier", e.target.value)}
            />
          </Field>
          <div className="flex gap-3">
            <Button type="submit" disabled={busy} className="flex-1">
              {busy ? "Saving…" : "Add account"}
            </Button>
            {!onboarding && (
              <Button variant="secondary" onClick={() => router.back()}>
                Cancel
              </Button>
            )}
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
        <Suspense fallback={null}>
          <NewAccountForm />
        </Suspense>
      </RequireSession>
    </Providers>
  );
}
