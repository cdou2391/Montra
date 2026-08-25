"use client";

/**
 * Exchange rates, fetched daily.
 *
 * Rates arrive on their own each morning, so nobody has to type one. The form
 * below is an override for when the published number is not the one you got —
 * a bank's tourist rate rarely matches the reference rate — and a rate you
 * enter stops being refreshed, because deliberate input outranks a feed.
 *
 * Nothing here changes what an account holds. A USD account holds dollars
 * whatever rate is recorded; this only makes the totals mean something.
 */

import { FormEvent, useCallback, useEffect, useState } from "react";

import { CurrenciesInUse, ExchangeRate, MontraApiError, montra } from "@/lib/api";
import { Icon } from "@/components/icons";
import { Button, Card, ErrorNotice, Field, Input, Select } from "@/components/ui";

const SOURCE_NAMES: Record<string, string> = {
  MANUAL: "set by you",
  FRANKFURTER: "Frankfurter",
  OPEN_ER_API: "open.er-api.com",
  CURRENCY_FREAKS: "CurrencyFreaks",
};

export function ExchangeRates() {
  const [rates, setRates] = useState<ExchangeRate[]>([]);
  const [inUse, setInUse] = useState<CurrenciesInUse | null>(null);
  const [form, setForm] = useState({ quote: "", rate: "" });
  const [showOverride, setShowOverride] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [refreshing, setRefreshing] = useState(false);

  const load = useCallback(() => {
    montra.exchangeRates().then(setRates).catch(() => setRates([]));
    montra.currenciesInUse().then(setInUse).catch(() => setInUse(null));
  }, []);
  useEffect(load, [load]);

  const base = inUse?.base_currency ?? "";
  const others = (inUse?.currencies ?? []).filter((c) => c !== base);

  useEffect(() => {
    if (!form.quote && inUse) {
      setForm((f) => ({ ...f, quote: inUse.missing[0] ?? others[0] ?? "" }));
    }
  }, [inUse, form.quote, others]);

  async function refresh() {
    setRefreshing(true);
    setError(null);
    try {
      await montra.refreshExchangeRates();
      load();
    } catch {
      // A feed being down is not the user's problem to solve, but they should
      // know why nothing changed.
      setError("Could not reach the rate feed. The stored rates are still in use.");
    } finally {
      setRefreshing(false);
    }
  }

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
      setShowOverride(false);
      load();
    } catch (err) {
      setError(err instanceof MontraApiError ? err.message : "Could not save that rate.");
    } finally {
      setBusy(false);
    }
  }

  async function handBackToFeed(rate: ExchangeRate) {
    // Deleting the row is what returns the pair to the feed; the next run
    // fills it again.
    await montra.deleteExchangeRate(rate.id).catch(() => undefined);
    await montra.refreshExchangeRates().catch(() => undefined);
    load();
  }

  if (!inUse || others.length === 0) {
    // One currency, no question to answer.
    return null;
  }

  return (
    <Card>
      <p className="mb-1 text-xs uppercase tracking-wide text-content-muted">Exchange rates</p>
      <p className="mb-4 text-xs text-content-secondary">
        Fetched every morning and used only to total your accounts in {base}.
        Balances keep their own currency everywhere else.
      </p>

      {error && (
        <div className="mb-4">
          <ErrorNotice message={error} />
        </div>
      )}

      {rates.length > 0 ? (
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
                <p className="mt-0.5 text-xs text-content-muted">
                  {r.as_of} · {SOURCE_NAMES[r.source] ?? r.source}
                </p>
              </div>
              {!r.automatic && (
                <button
                  onClick={() => handBackToFeed(r)}
                  className="pressable shrink-0 text-xs text-accent"
                >
                  Use daily rate
                </button>
              )}
            </li>
          ))}
        </ul>
      ) : (
        <p className="mb-4 text-sm text-content-secondary">
          No rate yet for {others.join(" or ")}.
        </p>
      )}

      <div className="flex flex-wrap gap-3">
        <Button variant="secondary" disabled={refreshing} onClick={refresh}>
          {refreshing ? "Updating…" : "Update now"}
        </Button>
        <button
          onClick={() => setShowOverride((open) => !open)}
          className="pressable text-xs text-content-secondary hover:text-content-primary"
        >
          {showOverride ? "Cancel" : "Set one myself"}
        </button>
      </div>

      {showOverride && (
        <form onSubmit={save} className="mt-4 space-y-4 border-t border-white/5 pt-4">
          <p className="text-xs text-content-secondary">
            <Icon name="alertTriangle" size={12} className="mr-1 inline" />
            A rate you set here stops being updated daily.
          </p>
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
                placeholder="1475"
                value={form.rate}
                onChange={(e) => setForm((f) => ({ ...f, rate: e.target.value }))}
              />
            </Field>
          </div>
          <Button type="submit" disabled={busy || !form.quote}>
            {busy ? "Saving…" : "Save rate"}
          </Button>
        </form>
      )}
    </Card>
  );
}
