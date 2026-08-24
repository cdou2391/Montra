"use client";

import { useRouter } from "next/navigation";
import { FormEvent, useEffect, useState } from "react";

import { Account, Category, MontraApiError, montra } from "@/lib/api";
import { AppShell, PageHeader } from "@/components/shell";
import { Providers } from "@/app/providers";
import { RequireSession } from "@/components/session";
import { AmountInput, Button, Card, ErrorNotice, Field, Input, Select } from "@/components/ui";

const FREQUENCIES = [
  { value: "DAILY", label: "Daily" },
  { value: "WEEKLY", label: "Weekly" },
  { value: "MONTHLY", label: "Monthly" },
  { value: "QUARTERLY", label: "Quarterly" },
  { value: "YEARLY", label: "Yearly" },
];

function NewRule() {
  const router = useRouter();
  const [type, setType] = useState<"EXPENSE" | "INCOME">("EXPENSE");
  const [accounts, setAccounts] = useState<Account[]>([]);
  const [categories, setCategories] = useState<Category[]>([]);
  const [form, setForm] = useState({
    account_id: "",
    amount: "",
    name: "",
    frequency: "MONTHLY",
    interval_value: "1",
    start_date: new Date().toISOString().slice(0, 10),
    end_date: "",
    category_id: "",
    occurrence_hour: "9",
    reminder_days_before: "2",
  });
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    montra.accounts().then((list) => {
      setAccounts(list);
      setForm((f) => ({ ...f, account_id: f.account_id || list[0]?.id || "" }));
    });
  }, []);

  useEffect(() => {
    montra.categories(type).then(setCategories);
    setForm((f) => ({ ...f, category_id: "" }));
  }, [type]);

  function update(key: keyof typeof form, value: string) {
    setForm((f) => ({ ...f, [key]: value }));
  }

  async function submit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await montra.createRule({
        planned_type: type,
        account_id: form.account_id,
        amount: form.amount,
        name: form.name,
        frequency: form.frequency,
        interval_value: Number(form.interval_value),
        start_date: form.start_date,
        end_date: form.end_date || null,
        category_id: form.category_id || null,
        occurrence_hour: Number(form.occurrence_hour),
        reminder_days_before: form.reminder_days_before
          ? Number(form.reminder_days_before)
          : null,
      });
      router.push("/planning/recurring");
      router.refresh();
    } catch (err) {
      setError(err instanceof MontraApiError ? err.message : "Could not create the series.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <AppShell>
      <PageHeader title="Add recurring"
        icon="repeat" />

      <div className="mb-5 grid grid-cols-2 gap-2 rounded-control bg-background-secondary p-1">
        {(["EXPENSE", "INCOME"] as const).map((t) => (
          <button
            key={t}
            onClick={() => setType(t)}
            className={`min-h-[44px] rounded-[10px] text-sm font-semibold transition ${
              type === t
                ? t === "EXPENSE"
                  ? "bg-semantic-expense/15 text-semantic-expense"
                  : "bg-semantic-income/15 text-semantic-income"
                : "text-content-secondary"
            }`}
          >
            {t === "EXPENSE" ? "Expense" : "Income"}
          </button>
        ))}
      </div>

      <Card>
        <form onSubmit={submit} className="space-y-4">
          {error && <ErrorNotice message={error} />}

          <Field label="Name">
            <Input
              required
              placeholder={type === "EXPENSE" ? "Netflix" : "Salary"}
              value={form.name}
              onChange={(e) => update("name", e.target.value)}
            />
          </Field>

          <Field label="Amount">
            <AmountInput
              required
              placeholder="0"
              value={form.amount}
              onChange={(e) => update("amount", e.target.value)}
            />
          </Field>

          <Field label="Account">
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

          <div className="grid grid-cols-2 gap-3">
            <Field label="How often">
              <Select
                value={form.frequency}
                onChange={(e) => update("frequency", e.target.value)}
              >
                {FREQUENCIES.map((f) => (
                  <option key={f.value} value={f.value}>
                    {f.label}
                  </option>
                ))}
              </Select>
            </Field>
            <Field label="Every" hint="1 = every time">
              <Input
                type="number"
                min={1}
                max={52}
                value={form.interval_value}
                onChange={(e) => update("interval_value", e.target.value)}
              />
            </Field>
          </div>

          <Field label="First occurrence" hint="Monthly series keep this day of the month.">
            <Input
              type="date"
              required
              value={form.start_date}
              onChange={(e) => update("start_date", e.target.value)}
            />
          </Field>

          <Field label="Ends on" hint="Optional. Leave blank to run indefinitely.">
            <Input
              type="date"
              value={form.end_date}
              onChange={(e) => update("end_date", e.target.value)}
            />
          </Field>

          <Field label="Remind me" hint="Days before each occurrence.">
            <Input
              type="number"
              min={0}
              max={60}
              value={form.reminder_days_before}
              onChange={(e) => update("reminder_days_before", e.target.value)}
            />
          </Field>

          <p className="rounded-control border border-white/10 bg-background-secondary px-4 py-3 text-xs text-content-secondary">
            Montra keeps the next 90 days of this series in your upcoming list. Each occurrence
            stays a plan until you mark it done — nothing posts automatically.
          </p>

          <div className="flex gap-3">
            <Button type="submit" disabled={busy || !form.account_id} className="flex-1">
              {busy ? "Creating…" : "Create series"}
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
        <NewRule />
      </RequireSession>
    </Providers>
  );
}
