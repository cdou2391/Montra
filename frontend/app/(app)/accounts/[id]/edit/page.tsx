"use client";

import { useParams, useRouter } from "next/navigation";
import { FormEvent, useEffect, useState } from "react";

import { Account, MontraApiError, montra } from "@/lib/api";
import { PageHeader } from "@/components/shell";
import { SkeletonForm } from "@/components/skeletons";
import { AmountInput, Button, Card, ErrorNotice, Field, Input, Toggle } from "@/components/ui";

/**
 * Account details.
 *
 * Everything here is metadata rather than money: changing it moves no balance
 * and writes no transaction, so the form saves with a plain PATCH and never
 * touches the posting engine. Cards get the extra fields the plastic needs.
 *
 * Currency is the exception, and it is the backend that enforces it — an
 * account with history cannot change currency, because every amount already
 * recorded is denominated in the old one.
 */
export default function EditCardPage() {
  const router = useRouter();
  const { id } = useParams<{ id: string }>();

  const [account, setAccount] = useState<Account | null>(null);
  const [form, setForm] = useState({
    name: "",
    description: "",
    account_identifier: "",
    currency: "",
    credit_limit: "",
    statement_closing_day: "",
    payment_due_day: "",
    minimum_payment: "",
    interest_rate: "",
    expiry: "",
  });
  const [excluded, setExcluded] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    montra.account(id).then((a) => {
      setAccount(a);
      setExcluded(a.excluded_from_totals);
      const card = a.credit_card;
      setForm({
        name: a.name,
        description: a.description ?? "",
        account_identifier: a.masked_identifier ? "" : "",
        currency: a.currency,
        credit_limit: card?.credit_limit ?? "",
        statement_closing_day: card?.statement_closing_day?.toString() ?? "",
        payment_due_day: card?.payment_due_day?.toString() ?? "",
        minimum_payment: card?.minimum_payment ?? "",
        interest_rate: card?.interest_rate ?? "",
        // Prepaid cards carry no credit-card block, so the expiry is read
        // from the account itself.
        expiry: a.expiry ? a.expiry.expires_on.slice(0, 7) : "",
      });
    });
  }, [id]);

  const isCredit = account?.account_type === "CREDIT_CARD";
  const isCard = isCredit || account?.account_type === "PREPAID_CARD";
  // An account that has never been used can still change its currency; one
  // with history cannot, because its amounts are already in the old one.
  const currencyLocked = account?.has_activity !== false;

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
        description: form.description || null,
        excluded_from_totals: excluded,
        ...(form.account_identifier
          ? { account_identifier: form.account_identifier }
          : {}),
        ...(currencyLocked ? {} : { currency: form.currency }),
        ...(isCard
          ? {
              expiry_month: expiryMonth ? Number(expiryMonth) : null,
              expiry_year: expiryYear ? Number(expiryYear) : null,
            }
          : {}),
        // Credit terms would be rejected on a prepaid card, and there is
        // nothing there to send anyway.
        ...(isCredit
          ? {
              credit_limit: form.credit_limit || null,
              statement_closing_day: form.statement_closing_day
                ? Number(form.statement_closing_day)
                : null,
              payment_due_day: form.payment_due_day ? Number(form.payment_due_day) : null,
              minimum_payment: form.minimum_payment || null,
              interest_rate: form.interest_rate || null,
            }
          : {}),
      });
      router.push(`/accounts/${id}`);
      router.refresh();
    } catch (err) {
      setError(err instanceof MontraApiError ? err.message : "Could not save the changes.");
    } finally {
      setBusy(false);
    }
  }

  if (!account) return <SkeletonForm fields={5} />;

  return (
    <>
      <PageHeader
        title={isCard ? "Card details" : "Account details"}
        icon={isCard ? "creditCard" : "wallet"}
      />

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
            label="Description"
            hint="Optional. A note to tell this account from a similar one."
          >
            <Input
              value={form.description}
              onChange={(e) => update("description", e.target.value)}
            />
          </Field>

          <Field
            label={isCard ? "Last 4 digits" : "Account number"}
            hint={
              account.masked_identifier
                ? `Currently ${account.masked_identifier}. Leave blank to keep it.`
                : "Optional. Only the last few characters are ever shown."
            }
          >
            <Input
              maxLength={20}
              value={form.account_identifier}
              onChange={(e) => update("account_identifier", e.target.value)}
            />
          </Field>

          <Field
            label="Currency"
            hint={
              currencyLocked
                ? "Fixed once the account has any history — its amounts are already in this currency."
                : "Can still change: nothing has been recorded here yet."
            }
          >
            <Input
              maxLength={3}
              disabled={currencyLocked}
              value={form.currency}
              onChange={(e) => update("currency", e.target.value.toUpperCase())}
            />
          </Field>

          {isCard && (
          <Field
            label="Card expires"
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
          )}

          {isCredit && (
          <Field label="Credit limit" hint="Needed to show utilization.">
            <AmountInput
              value={form.credit_limit}
              onChange={(e) => update("credit_limit", e.target.value)}
            />
          </Field>

          )}

          {isCredit && (
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

          )}

          {isCredit && (
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
          )}

          <Toggle
            label="Exclude from totals"
            hint="Keeps this account out of your assets, liabilities and net worth. It still appears in your accounts, and its transactions still count towards spending."
            checked={excluded}
            onChange={setExcluded}
          />

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
