"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { MontraApiError, Preferences, ResetPreview, montra } from "@/lib/api";
import { AppShell, PageHeader } from "@/components/shell";
import { Providers } from "@/app/providers";
import { RequireSession, useSession } from "@/components/session";
import { Avatar } from "@/components/avatar";
import { Button, Card, ErrorNotice, Field, Input, Skeleton } from "@/components/ui";
import { ConfirmDialog } from "@/components/confirm-dialog";

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-baseline justify-between gap-4 border-b border-white/5 py-3 last:border-0">
      <span className="text-sm text-content-secondary">{label}</span>
      <span className="min-w-0 truncate text-sm font-medium text-content-primary">{value}</span>
    </div>
  );
}

function Toggle({
  label,
  hint,
  checked,
  onChange,
  disabled,
}: {
  label: string;
  hint?: string;
  checked: boolean;
  onChange: (next: boolean) => void;
  disabled?: boolean;
}) {
  return (
    <button
      role="switch"
      aria-checked={checked}
      disabled={disabled}
      onClick={() => onChange(!checked)}
      className="pressable pressable-surface flex w-full items-center justify-between gap-4 border-b border-white/5 py-4 text-left last:border-0 disabled:opacity-50"
    >
      <span className="min-w-0">
        <span className="block text-sm font-medium text-content-primary">{label}</span>
        {hint && <span className="mt-0.5 block text-xs text-content-secondary">{hint}</span>}
      </span>
      <span
        aria-hidden
        className={`relative h-6 w-11 shrink-0 rounded-full transition ${
          checked ? "bg-accent" : "bg-white/15"
        }`}
      >
        <span
          className={`absolute top-0.5 h-5 w-5 rounded-full bg-background-primary transition-all ${
            checked ? "left-[22px]" : "left-0.5"
          }`}
        />
      </span>
    </button>
  );
}

function Profile() {
  const { user } = useSession();
  const router = useRouter();
  const [prefs, setPrefs] = useState<Preferences | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  const [resetOpen, setResetOpen] = useState(false);
  const [preview, setPreview] = useState<ResetPreview | null>(null);
  const [resetPassword, setResetPassword] = useState("");
  const [resetError, setResetError] = useState<string | null>(null);
  const [resetting, setResetting] = useState(false);

  useEffect(() => {
    montra
      .preferences()
      .then(setPrefs)
      .catch(() => setPrefs(null));
  }, []);

  function openReset() {
    setResetError(null);
    setResetPassword("");
    setPreview(null);
    setResetOpen(true);
    // Counts are fetched fresh each time, so the warning is never stale.
    montra
      .resetPreview()
      .then(setPreview)
      .catch(() => setPreview(null));
  }

  async function confirmReset() {
    setResetting(true);
    setResetError(null);
    try {
      await montra.resetProfile(resetPassword);
      setResetOpen(false);
      // Land on Home, which is now the empty state a new account sees.
      router.push("/");
      router.refresh();
    } catch (err) {
      setResetError(
        err instanceof MontraApiError ? err.message : "Could not reset your profile.",
      );
    } finally {
      setResetting(false);
    }
  }

  async function save(patch: Partial<Preferences>) {
    if (!prefs) return;
    // Optimistic: the control should not lag behind the tap.
    const previous = prefs;
    setPrefs({ ...prefs, ...patch });
    setSaving(true);
    setError(null);
    try {
      setPrefs(await montra.updatePreferences(patch));
    } catch (err) {
      setPrefs(previous);
      setError(err instanceof MontraApiError ? err.message : "Could not save that.");
    } finally {
      setSaving(false);
    }
  }

  async function signOut() {
    await montra.logout();
    router.push("/login");
    router.refresh();
  }

  if (!user) {
    return (
      <AppShell>
        <PageHeader title="Profile"
        icon="user" />
        <Skeleton className="h-48 w-full" />
      </AppShell>
    );
  }

  return (
    <AppShell>
      <PageHeader title="Profile"
        icon="user" />

      <Card className="mb-4">
        <div className="flex items-center gap-4">
          <Avatar user={user} size="lg" />
          <div className="min-w-0">
            <p className="truncate text-section text-content-primary">
              {user.display_name ?? "Montra user"}
            </p>
            <p className="mt-0.5 truncate text-sm text-content-secondary">{user.email}</p>
          </div>
        </div>
      </Card>

      <Card className="mb-4">
        <p className="mb-1 text-xs uppercase tracking-wide text-content-muted">Account</p>
        <Row label="Base currency" value={user.base_currency} />
        <Row label="Timezone" value={user.timezone} />
        <Row label="Household" value={user.active_family?.name ?? "Not in a household yet"} />
        <p className="mt-3 text-xs text-content-muted">
          Changing your name, currency or timezone is not available yet.
        </p>
      </Card>

      <Card className="mb-4">
        <p className="mb-1 text-xs uppercase tracking-wide text-content-muted">Preferences</p>
        {error && (
          <div className="mb-3">
            <ErrorNotice message={error} />
          </div>
        )}
        {prefs === null ? (
          <Skeleton className="h-32 w-full" />
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

      <Button variant="secondary" onClick={signOut}>
        Sign out
      </Button>

      <Card className="mt-8 border-semantic-expense/25">
        <p className="text-xs uppercase tracking-wide text-semantic-expense">Danger zone</p>
        <p className="mt-2 text-sm font-medium text-content-primary">Reset profile</p>
        <p className="mt-1 text-sm text-content-secondary">
          Deletes every account, transaction, loan and plan, and puts you back where a new
          account starts. Your login stays.
        </p>
        <div className="mt-4">
          <Button variant="destructive" onClick={openReset}>
            Reset profile
          </Button>
        </div>
      </Card>

      <ConfirmDialog
        open={resetOpen}
        onClose={() => setResetOpen(false)}
        title="Reset profile"
      >
        <p className="text-section text-content-primary">Reset your profile?</p>
        <p className="mt-2 text-sm text-content-secondary">
          This permanently deletes your financial history. It cannot be undone, and there is no
          backup.
        </p>

        {/* A warning that names real numbers is a warning; "this cannot be
            undone" on its own is wallpaper. */}
        <div className="mt-4 rounded-control border border-semantic-expense/30 bg-semantic-expense/10 p-4">
          {preview === null ? (
            <Skeleton className="h-24 w-full" />
          ) : (
            <ul className="space-y-1 text-sm text-content-primary">
              {[
                ["accounts", "accounts"],
                ["transactions", "transactions"],
                ["transfers", "transfers"],
                ["loans", "loans"],
                ["planned_transactions", "upcoming items"],
                ["recurring_rules", "recurring series"],
                ["custom_categories", "custom categories"],
                ["notifications", "notifications"],
              ]
                .filter(([key]) => preview[key as keyof ResetPreview] > 0)
                .map(([key, label]) => (
                  <li key={key} className="flex justify-between gap-4">
                    <span className="text-content-secondary">{label}</span>
                    <span className="tabular font-semibold">
                      {preview[key as keyof ResetPreview]}
                    </span>
                  </li>
                ))}
              {Object.values(preview).every((v) => v === 0) && (
                <li className="text-content-secondary">
                  There is nothing to delete — your profile is already empty.
                </li>
              )}
            </ul>
          )}
        </div>

        {resetError && (
          <div className="mt-4">
            <ErrorNotice message={resetError} />
          </div>
        )}

        <div className="mt-4">
          <Field label="Confirm with your password" hint="Required for an action this final.">
            <Input
              type="password"
              autoComplete="current-password"
              value={resetPassword}
              onChange={(e) => setResetPassword(e.target.value)}
            />
          </Field>
        </div>

        <div className="mt-5 flex flex-col-reverse gap-3 sm:flex-row">
          <Button
            variant="secondary"
            onClick={() => setResetOpen(false)}
            className="flex-1"
          >
            Keep my data
          </Button>
          <Button
            variant="destructive"
            onClick={confirmReset}
            disabled={resetting || !resetPassword}
            className="flex-1"
          >
            {resetting ? "Resetting…" : "Delete everything"}
          </Button>
        </div>
      </ConfirmDialog>
    </AppShell>
  );
}

export default function Page() {
  return (
    <Providers>
      <RequireSession>
        <Profile />
      </RequireSession>
    </Providers>
  );
}
