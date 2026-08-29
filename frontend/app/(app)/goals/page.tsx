"use client";

import Link from "next/link";
import { FormEvent, useCallback, useEffect, useState } from "react";

import { Account, Goal, MontraApiError, montra } from "@/lib/api";
import { ContextSwitch, useFinancialContext } from "@/components/context";
import { PageHeader } from "@/components/shell";
import { useSession } from "@/components/session";
import {
  AmountInput,
  Button,
  Card,
  EmptyState,
  ErrorNotice,
  Field,
  Input,
  Select,
  StatusChip,
} from "@/components/ui";
import { ListSkeleton } from "@/components/skeletons";
import { formatDate, formatMoney } from "@/lib/format";

/**
 * Goals.
 *
 * Every figure is derived server-side from the transfers tagged to a goal, so
 * nothing here does arithmetic of its own. Contributing posts a real transfer;
 * this screen only chooses the amount and where it comes from.
 */

function ContributeForm({
  goal,
  accounts,
  onDone,
  onCancel,
}: {
  goal: Goal;
  accounts: Account[];
  onDone: () => void;
  onCancel: () => void;
}) {
  // Fixed for the life of the form: replaying it returns the original transfer
  // rather than moving the money twice.
  const [idempotencyKey] = useState(() => crypto.randomUUID());
  const [sourceId, setSourceId] = useState("");
  const [amount, setAmount] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  // Money has to come from somewhere else; the goal's own account is not a
  // source for its own contribution.
  const sources = accounts.filter((a) => a.id !== goal.account.id);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await montra.contributeToGoal(
        goal.id,
        { source_account_id: sourceId, amount },
        idempotencyKey,
      );
      onDone();
    } catch (err) {
      setError(err instanceof MontraApiError ? err.message : "Could not add that.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <form onSubmit={submit} className="mt-3 space-y-3 border-t border-line/5 pt-3">
      {error && <ErrorNotice message={error} />}
      <Field label="From">
        <Select required value={sourceId} onChange={(e) => setSourceId(e.target.value)}>
          <option value="">Choose an account</option>
          {sources.map((a) => (
            <option key={a.id} value={a.id}>
              {a.name}
            </option>
          ))}
        </Select>
      </Field>
      <Field label="Amount" hint={`Moves into ${goal.account.name}. Nothing is spent.`}>
        <AmountInput required value={amount} onChange={(e) => setAmount(e.target.value)} />
      </Field>
      <div className="flex gap-2">
        <Button type="submit" disabled={busy || !sourceId || !amount}>
          {busy ? "Adding…" : "Add money"}
        </Button>
        <Button variant="secondary" onClick={onCancel}>
          Cancel
        </Button>
      </div>
    </form>
  );
}

function GoalCard({
  goal,
  accounts,
  onChanged,
}: {
  goal: Goal;
  accounts: Account[];
  onChanged: () => void;
}) {
  const [contributing, setContributing] = useState(false);
  const [busy, setBusy] = useState(false);
  const achieved = goal.status === "ACHIEVED";
  const percent = Math.max(0, Math.min(100, Number(goal.progress_percent)));

  async function archive() {
    setBusy(true);
    try {
      await montra.archiveGoal(goal.id);
      onChanged();
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card className="mb-3">
      <div className="flex items-baseline justify-between gap-3">
        <p className="truncate text-sm font-medium text-content-primary">{goal.name}</p>
        {achieved && <StatusChip tone="income">Reached</StatusChip>}
      </div>

      <p className="mt-1">
        <span className="tabular text-sm font-semibold text-content-primary">
          {formatMoney(goal.saved, goal.currency)}
        </span>
        <span className="text-sm text-content-muted">
          {" "}
          of {formatMoney(goal.target_amount, goal.currency)}
        </span>
      </p>

      <div className="mt-2 h-2 w-full overflow-hidden rounded-full bg-line/10">
        <div
          className={`h-full rounded-full ${achieved ? "bg-semantic-income" : "bg-accent"}`}
          style={{ width: `${percent}%` }}
        />
      </div>

      <p className="mt-2 text-xs text-content-secondary">
        {achieved
          ? `Saved in ${goal.account.name}. It stays there until you move it.`
          : `${formatMoney(goal.remaining, goal.currency)} to go · ${goal.account.name}`}
      </p>

      {/* Only where there is a date to arrive by, and something left to do. */}
      {!achieved && goal.target_date && goal.required_monthly && (
        <p className="mt-1 text-xs text-content-muted">
          {formatMoney(goal.required_monthly, goal.currency)} a month to reach it by{" "}
          {formatDate(`${goal.target_date}T00:00:00`)}.
        </p>
      )}
      {!achieved && !goal.target_date && (
        <p className="mt-1 text-xs text-content-muted">No deadline.</p>
      )}

      {contributing ? (
        <ContributeForm
          goal={goal}
          accounts={accounts}
          onDone={() => {
            setContributing(false);
            onChanged();
          }}
          onCancel={() => setContributing(false)}
        />
      ) : (
        <div className="mt-3 flex flex-wrap gap-2">
          {!achieved && (
            <button
              type="button"
              onClick={() => setContributing(true)}
              className="pressable inline-flex min-h-[36px] items-center rounded-full bg-accent px-3 text-xs font-semibold text-background-primary"
            >
              Add money
            </button>
          )}
          {/* Starting a schedule from here is the natural place: the goal and
              its account are already chosen, so the form opens knowing both. */}
          {!achieved && (
            <Link href="/planning/recurring/new" className="pressable pressable-tint rounded-full">
              <span className="inline-flex min-h-[36px] items-center rounded-full border border-line/10 px-3 text-xs text-content-secondary">
                Set up monthly
              </span>
            </Link>
          )}
          <button
            type="button"
            onClick={archive}
            disabled={busy}
            className="pressable pressable-tint min-h-[36px] rounded-full border border-line/10 px-3 text-xs text-content-secondary disabled:opacity-40"
          >
            Archive
          </button>
        </div>
      )}
    </Card>
  );
}

export default function Goals() {
  const { user } = useSession();
  const { context, family } = useFinancialContext();  const [goals, setGoals] = useState<Goal[] | null>(null);
  const [accounts, setAccounts] = useState<Account[]>([]);
  const [adding, setAdding] = useState(false);
  const [form, setForm] = useState({ name: "", account_id: "", target_amount: "", target_date: "" });
  // The date is the user's decision, so it is off until they say otherwise
  // rather than defaulting to some month and pretending they chose it.
  const [dated, setDated] = useState(false);
  const [visibility, setVisibility] = useState("PRIVATE");
  const [error, setError] = useState<string | null>(null);
  // Same reason as Home: the previous context's rows are not a preview of this
  // one's. Cleared during render, so the stale set never paints.
  const [loadedContext, setLoadedContext] = useState(context);
  if (loadedContext !== context) {
    setLoadedContext(context);
    setGoals(null);
  }
  const [saving, setSaving] = useState(false);

  const load = useCallback(() => {
    montra
      .goals(context)
      .then(setGoals)
      .catch(() => setGoals([]));
  }, [context]);

  useEffect(load, [load]);
  useEffect(() => {
    montra
      .accounts()
      .then((list) => setAccounts(list.filter((a) => a.account_nature === "ASSET")))
      .catch(() => setAccounts([]));
  }, []);

  const currency = user?.base_currency ?? "RWF";

  async function submit(event: FormEvent) {
    event.preventDefault();
    setSaving(true);
    setError(null);
    try {
      await montra.createGoal({
        name: form.name,
        account_id: form.account_id,
        target_amount: form.target_amount,
        target_date: dated && form.target_date ? form.target_date : null,
        visibility,
      });
      setAdding(false);
      setDated(false);
      setForm({ name: "", account_id: "", target_amount: "", target_date: "" });
      load();
    } catch (err) {
      setError(err instanceof MontraApiError ? err.message : "Could not add that goal.");
    } finally {
      setSaving(false);
    }
  }

  if (goals === null) {
    return (
      <>
        <PageHeader title="Goals" icon="piggyBank" />
        <ListSkeleton />
      </>
    );
  }

  return (
    <>
      {family && <ContextSwitch className="mb-5" />}

      <PageHeader
        title="Goals"
        icon="piggyBank"
        action={<Button onClick={() => setAdding((v) => !v)}>{adding ? "Cancel" : "Add"}</Button>}
      />

      {adding && (
        <Card className="mb-4">
          <form onSubmit={submit} className="space-y-4">
            {error && <ErrorNotice message={error} />}
            <Field label="What for">
              <Input
                required
                maxLength={160}
                placeholder="A new laptop"
                value={form.name}
                onChange={(e) => setForm({ ...form, name: e.target.value })}
              />
            </Field>
            <Field label="Saving into" hint="The account the money will sit in.">
              <Select
                required
                value={form.account_id}
                onChange={(e) => setForm({ ...form, account_id: e.target.value })}
              >
                <option value="">Choose an account</option>
                {accounts.map((a) => (
                  <option key={a.id} value={a.id}>
                    {a.name}
                  </option>
                ))}
              </Select>
            </Field>
            <Field label="Target" hint={`In ${currency}.`}>
              <AmountInput
                required
                value={form.target_amount}
                onChange={(e) => setForm({ ...form, target_amount: e.target.value })}
              />
            </Field>

            <div>
              <label className="pressable flex items-center gap-2 text-sm text-content-primary">
                <input
                  type="checkbox"
                  checked={dated}
                  onChange={(e) => setDated(e.target.checked)}
                  className="h-4 w-4 accent-accent"
                />
                Set a target date
              </label>
              <p className="mt-1 text-xs text-content-secondary">
                With one, Montra works out what to put aside each month. Without, it just
                tracks the total.
              </p>
              {dated && (
                <div className="mt-3">
                  <Input
                    type="date"
                    required
                    value={form.target_date}
                    onChange={(e) => setForm({ ...form, target_date: e.target.value })}
                  />
                </div>
              )}
            </div>


            {/* Only where there is a household to share with: the API refuses
                otherwise, and an option that always errors is worse than no
                option. Same words the Household page uses. */}
            {family && (
              <Field
                label="Who can see it"
                hint="Shared means the household can add to it too."
              >
                <Select
                  value={visibility}
                  onChange={(e) => setVisibility(e.target.value)}
                >
                  <option value="PRIVATE">Only me</option>
                  <option value="FAMILY_VISIBLE">Household can see</option>
                  <option value="SHARED">Shared</option>
                </Select>
              </Field>
            )}

            <Button
              type="submit"
              disabled={saving || !form.name || !form.account_id || !form.target_amount}
            >
              {saving ? "Adding…" : "Add goal"}
            </Button>
          </form>
        </Card>
      )}

      {goals.length === 0 ? (
        <EmptyState
          title="No goals yet"
          message="Set something to save towards and Montra will track what you have put aside for it."
          action={!adding && <Button onClick={() => setAdding(true)}>Add a goal</Button>}
        />
      ) : (
        goals.map((goal) => (
          <GoalCard key={goal.id} goal={goal} accounts={accounts} onChanged={load} />
        ))
      )}
    </>
  );
}
