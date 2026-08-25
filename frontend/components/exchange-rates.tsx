"use client";

/**
 * Exchange rates, entered by hand.
 *
 * Automatic rates are deferred by the PRD, and a net worth that moves because
 * a third party changed a number is worse than one you set deliberately and
 * can explain. Only currencies actually held are offered — asking for a USD
 * rate matters once there is a dollar account to convert.
 *
 * Nothing here changes what an account holds. A USD account holds dollars
 * whatever rate is recorded; this only makes the totals mean something.
 */

import { FormEvent, useCallback, useEffect, useState } from "react";

import { CurrenciesInUse, ExchangeRate, MontraApiError, montra } from "@/lib/api";
import { Icon } from "@/components/icons";
import { Button, Card, ErrorNotice, Field, Input, Select } from "@/components/ui";

export function ExchangeRates() {
  const [rates, setRates] = useState<ExchangeRate[]>([]);
  const [inUse, setInUse] = useState<CurrenciesInUse | null>(null);
  const [form, setForm] = useState({ quote: "", rate: "" });
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(() => {
    montra.exchangeRates().then(setRates).catch(() => setRates([]));
    montra.currenciesInUse().then(setInUse).catch(() => setInUse(null));
  }, []);
  useEffect(load, [load]);

  const base = inUse?.base_currency ?? "";
  const others = (inUse?.currencies ?? []).filter((c) => c !== base);

  useEffect(() => {
    // Default to the first currency still without a rate, which is the one
    // the prompt elsewhere is complaining about.
    if (!form.quote && inUse) {
      setForm((f) => ({ ...f, quote: inUse.missing[0] ?? others[0] ?? "" }));
    }
  }, [inUse, form.quote, others]);

  async function save(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await montra.setExchangeRate({
        base_currency: form.quote,
        quote_currency: base,
        rate: form.rate,
      });
      setForm((f) => ({ ...f, rate: "" }));
      load();
    } catch (err) {
      setError(err instanceof MontraApiError ? err.message : "Could not save that rate.");
    } finally {
      setBusy(false);
    }
  }

  async function remove(id: string) {
    await montra.deleteExchangeRate(id).catch(() => undefined);
    load();
  }

  if (!inUse || others.length === 0) {
    // Nothing to convert: one currency, no question to answer.
    return null;
  }

  return (
    <Card>
      <p className="mb-1 text-xs uppercase tracking-wide text-content-muted">Exchange rates</p>
      <p className="mb-4 text-xs text-content-secondary">
        Used only to total your accounts in {base}. Balances keep their own
        currency everywhere else.
      </p>

      {error && (
        <div className="mb-4">
          <ErrorNotice message={error} />
        </div>
      )}

      {rates.length > 0 && (
        <ul className="mb-4">
          {rates.map((r) => (
            <li
              key={r.id}
              className="flex items-center gap-3 border-b border-white/5 py-3 first:pt-0 last:border-0 last:pb-0"
            >
              <div className="min-w-0 flex-1">
                <p className="tabular text-sm text-content-primary">
                  1 {r.base_currency} = {r.rate} {r.quote_currency}
                </p>
                <p className="mt-0.5 text-xs text-content-muted">Set {r.as_of}</p>
              </div>
              <button
                onClick={() => remove(r.id)}
                aria-label={`Remove the ${r.base_currency} to ${r.quote_currency} rate`}
                className="pressable shrink-0 text-content-muted hover:text-semantic-expense"
              >
                <Icon name="trash" size={16} />
              </button>
            </li>
          ))}
        </ul>
      )}

      <form onSubmit={save} className="space-y-4">
        <div className="grid grid-cols-2 gap-3">
          <Field label="One unit of">
            <Select
              required
              value={form.quote}
              onChange={(e) => setForm((f) => ({ ...f, quote: e.target.value }))}
            >
              {others.map((c) => (
                <option key={c} value={c}>
                  {c}
                </option>
              ))}
            </Select>
          </Field>
          <Field label={`Is worth, in ${base}`}>
            <Input
              required
              type="number"
              step="0.00000001"
              min="0"
              inputMode="decimal"
              placeholder="1300"
              value={form.rate}
              onChange={(e) => setForm((f) => ({ ...f, rate: e.target.value }))}
            />
          </Field>
        </div>
        <Button type="submit" disabled={busy || !form.quote}>
          {busy ? "Saving…" : "Save rate"}
        </Button>
      </form>
    </Card>
  );
}
