"use client";

import { useRouter } from "next/navigation";
import { FormEvent, useEffect, useState } from "react";

import { Account, MontraApiError, montra } from "@/lib/api";
import { PageHeader } from "@/components/shell";
import { useSession } from "@/components/session";
import { AmountInput, Button, Card, ErrorNotice, Field, Input, Select } from "@/components/ui";

const FREQUENCIES = [
  { value: "", label: "No schedule" },
  { value: "WEEKLY", label: "Weekly" },
  { value: "MONTHLY", label: "Monthly" },
  { value: "QUARTERLY", label: "Quarterly" },
  { value: "YEARLY", label: "Yearly" },
];

export default function NewLoan() {
  const router = useRouter();
  const { user } = useSession();
  const [direction, setDirection] = useState<"PAYABLE" | "RECEIVABLE">("PAYABLE");
  const [, setAccounts] = useState<Account[]>([]);
  const [form, setForm] = useState({
    name: "",
    counterparty: "",
    currency: user?.base_currency ?? "RWF",
    original_principal: "",
    opening_outstanding_principal: "",
    start_date: new Date().toISOString().slice(0, 10),
    end_date: "",
    interest_rate: "",
    expected_payment_amount: "",
    payment_frequency: "MONTHLY",
    next_payment_date: "",
    notes: "",
  });
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    montra.accounts().then(setAccounts);
  }, []);

  function update(key: keyof typeof form, value: string) {
    setForm((f) => ({ ...f, [key]: value }));
  }

  async function submit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await montra.createLoan({
        name: form.name,
        direction,
        currency: form.currency,
        original_principal: form.original_principal,
        // Default the outstanding figure to the original, which is the common
        // case for a loan you are recording from its start.
        opening_outstanding_principal:
          form.opening_outstanding_principal || form.original_principal,
        start_date: form.start_date,
        counterparty: form.counterparty || null,
        interest_rate: form.interest_rate || null,
        end_date: form.end_date || null,
        expected_payment_amount: form.expected_payment_amount || null,
        payment_frequency: form.payment_frequency || null,
        next_payment_date: form.next_payment_date || null,
        notes: form.notes || null,
      });
      router.push("/loans");
      router.refresh();
    } catch (err) {
      setError(err instanceof MontraApiError ? err.message : "Could not create the loan.");
    } finally {
      setBusy(false);
    }
  }

  const owed = direction === "PAYABLE";

  return (
    <>
      <PageHeader title="Add loan" icon="handshake" />

      <div className="mb-5 grid grid-cols-2 gap-2 rounded-control bg-background-secondary p-1">
        {([
          ["PAYABLE", "I owe someone"],
          ["RECEIVABLE", "Someone owes me"],
        ] as const).map(([value, label]) => (
          <button
            key={value}
            onClick={() => setDirection(value)}
            aria-pressed={direction === value}
            className={`pressable min-h-[44px] rounded-[10px] px-2 text-sm font-semibold transition ${
              direction === value
                ? value === "PAYABLE"
                  ? "bg-semantic-expense/15 text-semantic-expense"
                  : "bg-semantic-income/15 text-semantic-income"
                : "text-content-secondary"
            }`}
          >
            {label}
          </button>
        ))}
      </div>

      <Card>
        <form onSubmit={submit} className="space-y-4">
          {error && <ErrorNotice message={error} />}

          <Field label="Name">
            <Input
              required
              placeholder={owed ? "Car loan" : "Loan to Jean"}
              value={form.name}
              onChange={(e) => update("name", e.target.value)}
            />
          </Field>

          <Field label={owed ? "Lender" : "Borrower"} hint="Optional.">
            <Input
              placeholder={owed ? "Bank of Kigali" : "Jean"}
              value={form.counterparty}
              onChange={(e) => update("counterparty", e.target.value)}
            />
          </Field>

          <Field label="Currency">
            <Input
              required
              maxLength={3}
              value={form.currency}
              onChange={(e) => update("currency", e.target.value.toUpperCase())}
            />
          </Field>

          <Field label="Original amount" hint="What the loan was for at the start.">
            <AmountInput
              required
              placeholder="0"
              value={form.original_principal}
              onChange={(e) => update("original_principal", e.target.value)}
            />
          </Field>

          <Field
            label="Still outstanding"
            hint="Leave blank if nothing has been paid off yet."
          >
            <AmountInput
              placeholder={form.original_principal || "0"}
              value={form.opening_outstanding_principal}
              onChange={(e) => update("opening_outstanding_principal", e.target.value)}
            />
          </Field>

          <div className="grid grid-cols-2 gap-3">
            <Field label="Started">
              <Input
                type="date"
                required
                value={form.start_date}
                onChange={(e) => update("start_date", e.target.value)}
              />
            </Field>
            <Field label="Ends" hint="Optional">
              <Input
                type="date"
                value={form.end_date}
                onChange={(e) => update("end_date", e.target.value)}
              />
            </Field>
          </div>

          <Field label="Interest rate" hint="% per year. Optional.">
            <Input
              type="number"
              step="0.01"
              min={0}
              value={form.interest_rate}
              onChange={(e) => update("interest_rate", e.target.value)}
            />
          </Field>

          <div className="grid grid-cols-2 gap-3">
            <Field label="Expected payment" hint="Optional">
              <AmountInput
                value={form.expected_payment_amount}
                onChange={(e) => update("expected_payment_amount", e.target.value)}
              />
            </Field>
            <Field label="How often">
              <Select
                value={form.payment_frequency}
                onChange={(e) => update("payment_frequency", e.target.value)}
              >
                {FREQUENCIES.map((f) => (
                  <option key={f.value} value={f.value}>
                    {f.label}
                  </option>
                ))}
              </Select>
            </Field>
          </div>

          <Field label="Next payment due" hint="Optional">
            <Input
              type="date"
              value={form.next_payment_date}
              onChange={(e) => update("next_payment_date", e.target.value)}
            />
          </Field>

          <p className="rounded-control border border-white/10 bg-background-secondary px-4 py-3 text-xs text-content-secondary">
            Adding a loan records no transaction. It changes your net worth,
            because {owed ? "what you owe counts against it" : "what you are owed counts toward it"},
            but no money moves until you record a payment.
          </p>

          <div className="flex gap-3">
            <Button type="submit" disabled={busy} className="flex-1">
              {busy ? "Saving…" : "Add loan"}
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
