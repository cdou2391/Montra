"use client";

import { useEffect, useState } from "react";

import { Forecast, montra } from "@/lib/api";
import { PageHeader } from "@/components/shell";
import { ContextSwitch, useFinancialContext } from "@/components/context";
import { ForecastChart, ForecastTable } from "@/components/forecast-chart";
import { Icon } from "@/components/icons";
import { formatMoney } from "@/lib/format";
import { Card, EmptyState, Skeleton } from "@/components/ui";

/**
 * Cash-flow forecast (Implementation Plan Phase 24).
 *
 * Projects only what is already known — today's balances plus planned items
 * and loan instalments. It does not guess at future spending, so the number is
 * defensible rather than merely plausible.
 */
export default function ForecastPage() {
  const { context, family } = useFinancialContext();
  const [period, setPeriod] = useState<"7d" | "30d">("30d");
  const [forecast, setForecast] = useState<Forecast | null>(null);

  useEffect(() => {
    setForecast(null);
    montra
      .forecast(context, period)
      .then(setForecast)
      .catch(() => setForecast(null));
  }, [context, period]);

  const ending = forecast ? Number(forecast.projected_ending_balance) : 0;
  const change = forecast ? Number(forecast.net_change) : 0;

  return (
    <>
      {family && <ContextSwitch className="mb-5" />}
      <PageHeader title="Forecast" icon="trendingUp" />

      <div className="mb-5 grid grid-cols-2 gap-2 rounded-control bg-background-secondary p-1">
        {(
          [
            ["7d", "7 days"],
            ["30d", "30 days"],
          ] as const
        ).map(([value, label]) => (
          <button
            key={value}
            onClick={() => setPeriod(value)}
            aria-pressed={period === value}
            className={`pressable min-h-[40px] rounded-[10px] text-sm font-semibold transition ${
              period === value ? "bg-accent-muted text-accent" : "text-content-secondary"
            }`}
          >
            {label}
          </button>
        ))}
      </div>

      {forecast === null ? (
        <Skeleton className="h-64 w-full" />
      ) : forecast.points.length === 0 ? (
        <EmptyState
          title="Nothing to project"
          message="Add an account and some upcoming items and the forecast will fill in."
        />
      ) : (
        <>
          <Card className="mb-4">
            <p className="text-xs uppercase tracking-wide text-content-muted">
              Projected in {period === "7d" ? "7 days" : "30 days"}
            </p>
            <p
              className={`tabular mt-1 text-value sm:text-value-lg ${
                ending < 0 ? "text-semantic-expense" : "text-content-primary"
              }`}
            >
              {formatMoney(forecast.projected_ending_balance, forecast.currency)}
            </p>
            <p className="mt-1 text-xs text-content-secondary">
              {change >= 0 ? "Up " : "Down "}
              {formatMoney(String(Math.abs(change)), forecast.currency)} from{" "}
              {formatMoney(forecast.starting_balance, forecast.currency)} today
            </p>

            <div className="mt-4">
              <ForecastChart forecast={forecast} />
            </div>
          </Card>

          <div className="mb-4 grid grid-cols-2 gap-3">
            <Card>
              <p className="text-xs uppercase tracking-wide text-content-muted">Coming in</p>
              <p className="tabular mt-1 font-semibold text-semantic-income">
                {formatMoney(forecast.upcoming_income, forecast.currency)}
              </p>
            </Card>
            <Card>
              <p className="text-xs uppercase tracking-wide text-content-muted">Going out</p>
              <p className="tabular mt-1 font-semibold text-semantic-expense">
                {formatMoney(forecast.upcoming_expenses, forecast.currency)}
              </p>
            </Card>
          </div>

          {forecast.warnings.length > 0 && (
            <Card className="mb-4 border-semantic-expense/30">
              <p className="text-xs uppercase tracking-wide text-semantic-expense">
                Watch out
              </p>
              {forecast.warnings.map((warning) => (
                <div key={warning.account_id} className="mt-3 flex items-start gap-3">
                  {/* Icon and wording carry the meaning; the colour only
                      reinforces it. */}
                  <span className="mt-0.5 shrink-0 text-semantic-expense">
                    <Icon name="alertTriangle" size={18} />
                  </span>
                  <div className="min-w-0">
                    <p className="text-sm text-content-primary">{warning.message}</p>
                    <p className="tabular mt-0.5 text-xs text-content-secondary">
                      Projected {formatMoney(warning.projected_balance, forecast.currency)}
                    </p>
                  </div>
                </div>
              ))}
            </Card>
          )}

          <h2 className="mb-3 text-section">By date</h2>
          <Card>
            <ForecastTable forecast={forecast} />
          </Card>
        </>
      )}
    </>
  );
}
