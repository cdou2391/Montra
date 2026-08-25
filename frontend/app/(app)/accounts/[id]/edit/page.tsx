"use client";

import { useParams, useRouter } from "next/navigation";
import { FormEvent, useEffect, useState } from "react";

import { Account, MontraApiError, montra } from "@/lib/api";
import { PageHeader } from "@/components/shell";
import { AmountInput, Button, Card, ErrorNotice, Field, Input, Skeleton } from "@/components/ui";

/**
 * Card details.
 *
 * Everything here is metadata about the plastic rather than about the money:
 * changing it moves no balance and writes no transaction, so the form saves
 * with a plain PATCH and never touches the posting engine.
 */
export default function EditCardPage() {
  const router = useRouter();
  const { id } = useParams<{ id: string }>();

  const [account, setAccount] = useState<Account | null>(null);
  const [form, setForm] = useState({
    name: "",
    credit_limit: "",
    statement_closing_day: "",
    payment_due_day: "",
    minimum_payment: "",
    interest_rate: "",
    expiry: "",
  });
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    montra.account(id).then((a) => {
      setAccount(a);
      const card = a.credit_card;
      setForm({
        name: a.name,
        credit_limit: card?.credit_limit ?? "",
        statement_closing_day: card?.statement_closing_day?.toString() ?? "",
        payment_due_day: card?.payment_due_day?.toString() ?? "",
        minimum_payment: card?.minimum_payment ?? "",
        interest_rate: card?.interest_rate ?? "",
        expiry:
          card?.expiry_month && card?.expiry_year
            ? `${card.expiry_year}-${String(card.expiry_month).padStart(2, "0")}`
            : "",
      });
    });
  }, [id]);

  function update(key: keyof typeof form, value: string) {
    setForm((f) => ({ ...f, [key]: value }));
  }

  async function submit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    const [expiryYear, expiryMonth] = form.expiry ? form.expiry.split("-") : [];
    try {
      await montra.updateAccount(id, {
        name: form.name,
        credit_limit: form.credit_limit || null,
        statement_closing_day: form.statement_closing_day
          ? Number(form.statement_closing_day)
          : null,
        payment_due_day: form.payment_due_day ? Number(form.payment_due_day) : null,
        minimum_payment: form.minimum_payment || null,
        interest_rate: form.interest_rate || null,
        expiry_month: expiryMonth ? Number(expiryMonth) : null,
        expiry_year: expiryYear ? Number(expiryYear) : null,
      });
      router.push(`/accounts/${id}`);
      router.refresh();
    } catch (err) {
      setError(err instanceof MontraApiError ? err.message : "Could not save the changes.");
    } finally {
      setBusy(false);
    }
  }

  if (!account) return <Skeleton className="h-64 w-full" />;

  return (
    <>
      <PageHeader title="Card details" icon="creditCard" />

      <Card>
        <form onSubmit={submit} className="space-y-4">
          {error && <ErrorNotice message={error} />}

          <Field label="Name">
            <Input
              required
              value={form.name}
              onChange={(e) => update("name", e.target.value)}
            />
          </Field>

          <Field
            label="Expires"
            hint="The month printed on the card. You will be warned two months ahead."
          >
            <Input
              type="month"
              min="2000-01"
              max="2100-12"
              value={form.expiry}
              onChange={(e) => update("expiry", e.target.value)}
            />
          </Field>

          <Field label="Credit limit" hint="Needed to show utilization.">
            <AmountInput
              value={form.credit_limit}
              onChange={(e) => update("credit_limit", e.target.value)}
            />
          </Field>

          <div className="grid grid-cols-2 gap-3">
            <Field label="Statement closes" hint="Day of month">
              <Input
                type="number"
                min={1}
                max={31}
                value={form.statement_closing_day}
                onChange={(e) => update("statement_closing_day", e.target.value)}
              />
            </Field>
            <Field label="Payment due" hint="Day of month">
              <Input
                type="number"
                min={1}
                max={31}
                value={form.payment_due_day}
                onChange={(e) => update("payment_due_day", e.target.value)}
              />
            </Field>
          </div>

          <div className="grid grid-cols-2 gap-3">
            <Field label="Minimum payment">
              <AmountInput
                value={form.minimum_payment}
                onChange={(e) => update("minimum_payment", e.target.value)}
              />
            </Field>
            <Field label="Interest rate" hint="% per year">
              <Input
                type="number"
                step="0.01"
                min={0}
                max={100}
                value={form.interest_rate}
                onChange={(e) => update("interest_rate", e.target.value)}
              />
            </Field>
          </div>

          <div className="flex gap-3">
            <Button type="submit" disabled={busy} className="flex-1">
              {busy ? "Saving…" : "Save changes"}
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
