"use client";

import { useEffect, useState } from "react";

import { AppMeta, MontraApiError, Preferences, montra } from "@/lib/api";
import { PageHeader } from "@/components/shell";
import { Card, ErrorNotice, Field, Input, Skeleton, Toggle } from "@/components/ui";
import { ExchangeRates } from "@/components/exchange-rates";
import { useBalancePrivacy } from "@/components/balance-privacy";
import { useTheme } from "@/components/theme";

/**
 * How the app behaves, as against who you are.
 *
 * The split with Profile is deliberate: anything here changes the way Montra
 * works for you and nothing here is a fact about you. Your name, currency,
 * timezone, household, and your data — backup, restore, reset — stay on
 * Profile, because those are the person and their records rather than the
 * software.
 */
export default function AppSettings() {
  const [prefs, setPrefs] = useState<Preferences | null>(null);
  const [meta, setMeta] = useState<AppMeta | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  const { refresh: refreshPrivacy } = useBalancePrivacy();
  const { theme, setTheme } = useTheme();

  useEffect(() => {
    montra.preferences().then(setPrefs).catch(() => setPrefs(null));
    // The version comes from the API rather than the bundle, so one number
    // describes the running system instead of whichever half was built last.
    montra.meta().then(setMeta).catch(() => setMeta(null));
  }, []);

  async function save(patch: Partial<Preferences>) {
    if (!prefs) return;
    // Optimistic: the control should not lag behind the tap.
    const previous = prefs;
    setPrefs({ ...prefs, ...patch });
    setSaving(true);
    setError(null);
    try {
      setPrefs(await montra.updatePreferences(patch));
      // The masking lives in a provider above this page; without this it would
      // keep the old preference until the next full load.
      refreshPrivacy();
    } catch (err) {
      setPrefs(previous);
      setError(err instanceof MontraApiError ? err.message : "Could not save that.");
    } finally {
      setSaving(false);
    }
  }

  return (
    <>
      <PageHeader title="App settings" icon="settings" />

      <Card className="mb-4">
        <p className="mb-1 text-xs uppercase tracking-wide text-content-muted">Appearance</p>
        {/* Three states, so a segmented control rather than a switch: a toggle
            cannot say "follow the device", and following the device is what
            most people want. */}
        <p className="mt-2 text-sm font-medium text-content-primary">Theme</p>
        <p className="mt-0.5 text-xs text-content-secondary">
          Light, dark, or whatever your device is set to.
        </p>
        <div className="mt-3 grid grid-cols-3 gap-2 rounded-control bg-background-secondary p-1">
          {(
            [
              ["SYSTEM", "System"],
              ["LIGHT", "Light"],
              ["DARK", "Dark"],
            ] as const
          ).map(([value, label]) => (
            <button
              key={value}
              type="button"
              onClick={() => setTheme(value)}
              aria-pressed={theme === value}
              className={`pressable min-h-[38px] rounded-[10px] text-sm font-semibold transition ${
                theme === value ? "bg-accent-muted text-accent" : "text-content-secondary"
              }`}
            >
              {label}
            </button>
          ))}
        </div>
      </Card>

      <Card className="mb-4">
        <p className="mb-1 text-xs uppercase tracking-wide text-content-muted">Privacy</p>
        {error && (
          <div className="mb-3">
            <ErrorNotice message={error} />
          </div>
        )}
        {prefs === null ? (
          <Skeleton className="h-24 w-full" />
        ) : (
          <>
            <Toggle
              label="Hide balances by default"
              hint="Amounts start masked when you open the app."
              checked={prefs.hide_balances}
              disabled={saving}
              onChange={(v) => save({ hide_balances: v })}
            />
            <Toggle
              label="Remember balance privacy"
              hint="Keep balances hidden between sessions."
              checked={prefs.persist_balance_privacy}
              disabled={saving}
              onChange={(v) => save({ persist_balance_privacy: v })}
            />
          </>
        )}
      </Card>

      <Card className="mb-4">
        <p className="mb-1 text-xs uppercase tracking-wide text-content-muted">Notifications</p>
        {prefs === null ? (
          <Skeleton className="h-24 w-full" />
        ) : (
          <>
            <Toggle
              label="Notifications"
              hint="Reminders for upcoming bills and income."
              checked={prefs.notifications_enabled}
              disabled={saving}
              onChange={(v) => save({ notifications_enabled: v })}
            />
            <div className="pt-4">
              <Field
                label="Default reminder"
                hint="Days before something is due. Used when adding upcoming items."
              >
                <Input
                  type="number"
                  min={0}
                  max={30}
                  value={prefs.default_reminder_days ?? ""}
                  disabled={saving}
                  onChange={(e) =>
                    save({
                      default_reminder_days: e.target.value ? Number(e.target.value) : null,
                    })
                  }
                />
              </Field>
            </div>
          </>
        )}
      </Card>

      <div className="mb-4">
        <ExchangeRates />
      </div>

      <Card>
        <p className="mb-1 text-xs uppercase tracking-wide text-content-muted">About</p>
        <div className="flex items-baseline justify-between gap-4 border-b border-line/5 py-3">
          <span className="text-sm text-content-secondary">App</span>
          <span className="text-sm font-medium text-content-primary">
            {meta?.name ?? "Montra"}
          </span>
        </div>
        <div className="flex items-baseline justify-between gap-4 py-3">
          <span className="text-sm text-content-secondary">Version</span>
          <span className="tabular text-sm font-medium text-content-primary">
            {meta ? meta.version : "—"}
          </span>
        </div>
        <p className="mt-2 text-xs text-content-muted">
          Personal and household finance tracking.
        </p>
      </Card>
    </>
  );
}
