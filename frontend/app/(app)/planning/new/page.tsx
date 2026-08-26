"use client";

import { useRouter } from "next/navigation";
import { FormEvent, useEffect, useState } from "react";

import { Account, Category, MontraApiError, montra } from "@/lib/api";
import { PageHeader } from "@/components/shell";
import { toLocalInputValue } from "@/lib/format";
import { AmountInput, Button, Card, ErrorNotice, Field, Input, Select } from "@/components/ui";

function tomorrowAt9() {
  const d = new Date();
  d.setDate(d.getDate() + 1);
  d.setHours(9, 0, 0, 0);
  return toLocalInputValue(d);
}

export default function NewPlanned() {
  const router = useRouter();
  const [type, setType] = useState<"EXPENSE" | "INCOME" | "TRANSFER">("EXPENSE");
  const [accounts, setAccounts] = useState<Account[]>([]);
  const [categories, setCategories] = useState<Category[]>([]);
  const [form, setForm] = useState({
    account_id: "",
    amount: "",
    expected_at: tomorrowAt9(),
    description: "",
    category_id: "",
    destination_account_id: "",
    reminder_days_before: "3",
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
    if (type === "TRANSFER") {
      // Moving your own money between accounts is not spending, so it is not
      // categorised.
      setCategories([]);
      setForm((f) => ({ ...f, category_id: "" }));
      return;
    }
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
      await montra.createPlanned({
        planned_type: type,
        account_id: form.account_id,
        destination_account_id:
          type === "TRANSFER" ? form.destination_account_id : null,
        amount: form.amount,
        expected_at: form.expected_at,
        description: form.description,
        category_id: form.category_id || null,
        reminder_days_before: form.reminder_days_before
          ? Number(form.reminder_days_before)
          : null,
      });
      router.push("/planning");
      router.refresh();
    } catch (err) {
      setError(err instanceof MontraApiError ? err.message : "Could not save.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <PageHeader title="Add upcoming"
        icon="calendar" />

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

      <Card>
        <form onSubmit={submit} className="space-y-4">
          {error && <ErrorNotice message={error} />}

          <Field label="What is it?">
            <Input
              required
              placeholder={
                type === "EXPENSE"
                  ? "School fees"
                  : type === "INCOME"
                    ? "Salary"
                    : "Move to savings"
              }
              value={form.description}
              onChange={(e) => update("description", e.target.value)}
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

          <Field label={type === "TRANSFER" ? "From" : "Account"}>
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

          {type === "TRANSFER" ? (
            <Field label="To" hint="Both accounts must use the same currency.">
              <Select
                required
                value={form.destination_account_id}
                onChange={(e) => update("destination_account_id", e.target.value)}
              >
                <option value="">Choose an account</option>
                {accounts
                  .filter((a) => a.id !== form.account_id)
                  .map((a) => (
                    <option key={a.id} value={a.id}>
                      {a.name}
                    </option>
                  ))}
              </Select>
            </Field>
          ) : (
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
          )}

          <Field label={type === "TRANSFER" ? "When should it move?" : "When is it due?"}>
            <Input
              type="datetime-local"
              required
              value={form.expected_at}
              onChange={(e) => update("expected_at", e.target.value)}
            />
          </Field>

          <Field label="Remind me" hint="Days before it is due. Leave blank for no reminder.">
            <Input
              type="number"
              min={0}
              max={60}
              value={form.reminder_days_before}
              onChange={(e) => update("reminder_days_before", e.target.value)}
            />
          </Field>

          <p className="rounded-control border border-line/10 bg-background-secondary px-4 py-3 text-xs text-content-secondary">
            Nothing is recorded against your balance yet. This stays a plan until you mark it
            {type === "EXPENSE" ? " paid" : type === "INCOME" ? " received" : " done"}.
            {type === "TRANSFER" &&
              " A transfer moves money between your own accounts, so it is not counted as spending."}
          </p>

          <div className="flex gap-3">
            <Button
              type="submit"
              disabled={
                busy ||
                !form.account_id ||
                (type === "TRANSFER" && !form.destination_account_id)
              }
              className="flex-1"
            >
              {busy ? "Saving…" : "Add to upcoming"}
            </Button>
            <Button variant="secondary" onClick={() => router.back()}>
              Cancel
            </Button>
          </div>
        </form>
      </Card>
    </>
  );
}
