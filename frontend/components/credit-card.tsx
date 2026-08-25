"use client";

/**
 * Credit-card presentation (UI/UX sections 35-36).
 *
 * The screen leads with what is owed and how much room is left, because those
 * are the two numbers a card holder acts on.
 */

import { CardExpiry, CardSummary } from "@/lib/api";
import { formatDate, formatMoney } from "@/lib/format";
import { MoneyValue } from "@/components/financial";
import { Card } from "@/components/ui";
import { Icon } from "@/components/icons";

/** Restrained bar; colour only appears once utilization genuinely matters. */
export function UtilizationBar({ summary }: { summary: CardSummary }) {
  if (summary.utilization_percentage === null || summary.utilization_band === null) return null;

  const pct = Number(summary.utilization_percentage);
  const band = summary.utilization_band;
  const fill = {
    NORMAL: "bg-accent",
    NEUTRAL: "bg-accent",
    WARNING: "bg-semantic-warning",
    HIGH: "bg-semantic-expense",
  }[band];
  const caption = {
    NORMAL: "Comfortable",
    NEUTRAL: "Moderate",
    WARNING: "Getting high",
    HIGH: "Very high",
  }[band];

  return (
    <div className="mt-5">
      <div className="flex items-baseline justify-between">
        <span className="text-xs uppercase tracking-wide text-content-muted">Utilization</span>
        <span className="tabular text-sm font-semibold text-content-primary">{pct}%</span>
      </div>
      <div
        role="progressbar"
        aria-valuenow={pct}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-label="Credit utilization"
        className="mt-2 h-2 w-full overflow-hidden rounded-full bg-white/8"
      >
        <div
          className={`h-full rounded-full transition-all ${fill}`}
          // Over-limit cards would otherwise overflow the track.
          style={{ width: `${Math.min(pct, 100)}%` }}
        />
      </div>
      <p className="mt-1.5 text-xs text-content-muted">
        {caption}
        {pct > 100 ? " — over your limit" : ""}
      </p>
    </div>
  );
}

/**
 * Expiry, stated as a date rather than as MM/YY.
 *
 * A card printed 08/28 works to the end of August, which is not obvious from
 * the two numbers embossed on it; the API resolves the month end and this only
 * renders it. The icon and the wording carry the urgency, not the colour alone.
 */
export function ExpiryNotice({ expiry }: { expiry: CardExpiry | null }) {
  if (!expiry) return null;

  const on = formatDate(`${expiry.expires_on}T00:00:00`);
  if (expiry.status === "VALID") {
    return <Stat label="Expires" value={on} tone="muted" />;
  }

  const expired = expiry.status === "EXPIRED";
  const days = expiry.days_remaining;
  return (
    <div
      className={`flex items-start gap-2.5 rounded-control p-3 ${
        expired ? "bg-semantic-expense/10" : "bg-semantic-warning/10"
      }`}
    >
      <span
        className={`mt-0.5 shrink-0 ${
          expired ? "text-semantic-expense" : "text-semantic-warning"
        }`}
      >
        <Icon name="alertTriangle" size={16} />
      </span>
      <div className="min-w-0">
        <p className="text-sm font-medium text-content-primary">
          {expired
            ? `Expired ${on}`
            : days === 0
              ? `Expires today, ${on}`
              : `Expires in ${days} day${days === 1 ? "" : "s"}`}
        </p>
        <p className="mt-0.5 text-xs text-content-secondary">
          {expired ? expiry.advice : `Good until ${on}. ${expiry.advice}`}
        </p>
      </div>
    </div>
  );
}

function Stat({
  label,
  value,
  tone = "neutral",
}: {
  label: string;
  value: string;
  tone?: "neutral" | "expense" | "muted";
}) {
  return (
    <div>
      <p className="text-xs uppercase tracking-wide text-content-muted">{label}</p>
      <p
        className={`tabular mt-1 text-sm font-semibold ${
          tone === "expense"
            ? "text-semantic-expense"
            : tone === "muted"
              ? "text-content-secondary"
              : "text-content-primary"
        }`}
      >
        {value}
      </p>
    </div>
  );
}

export function CreditCardSummaryCard({
  summary,
  hidden,
}: {
  summary: CardSummary;
  hidden?: boolean;
}) {
  const money = (v: string | null) =>
    v === null ? "—" : hidden ? "••••" : formatMoney(v, summary.currency);

  return (
    <Card>
      <p className="text-xs uppercase tracking-wide text-content-muted">Outstanding</p>
      <p className="mt-1">
        <MoneyValue
          amount={summary.outstanding_balance}
          currency={summary.currency}
          size="value-lg"
          hidden={hidden}
        />
      </p>

      {summary.expiry && summary.expiry.status !== "VALID" && (
        <div className="mt-5">
          <ExpiryNotice expiry={summary.expiry} />
        </div>
      )}

      <div className="mt-5 grid grid-cols-2 gap-4">
        <Stat label="Available credit" value={money(summary.available_credit)} />
        <Stat label="Limit" value={money(summary.credit_limit)} tone="muted" />
        {summary.expiry?.status === "VALID" && <ExpiryNotice expiry={summary.expiry} />}
      </div>

      <UtilizationBar summary={summary} />

      {(summary.statement_balance ||
        summary.minimum_payment ||
        summary.payment_due_date) && (
        <div className="mt-5 grid grid-cols-2 gap-4 border-t border-white/5 pt-5">
          {summary.statement_balance && (
            <Stat label="Statement balance" value={money(summary.statement_balance)} />
          )}
          {summary.payment_due_date && (
            <Stat
              label="Payment due"
              value={formatDate(`${summary.payment_due_date}T00:00:00`)}
            />
          )}
          {summary.minimum_payment && (
            <Stat
              label="Minimum payment"
              value={money(summary.minimum_payment)}
              tone="expense"
            />
          )}
          {summary.interest_rate && (
            <Stat label="Interest rate" value={`${summary.interest_rate}%`} tone="muted" />
          )}
        </div>
      )}
    </Card>
  );
}
