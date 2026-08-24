"use client";

import { useParams, useRouter } from "next/navigation";
import { FormEvent, useEffect, useState } from "react";

import { MontraApiError, PlannedTransaction, montra } from "@/lib/api";
import { AppShell, PageHeader } from "@/components/shell";
import { Providers } from "@/app/providers";
import { RequireSession } from "@/components/session";
import { formatMoney, toLocalInputValue } from "@/lib/format";
import { AmountInput, Button, Card, ErrorNotice, Field, Input, Skeleton } from "@/components/ui";

function Reschedule() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const [planned, setPlanned] = useState<PlannedTransaction | null>(null);
  const [form, setForm] = useState({ expected_at: "", amount: "", reminder_days_before: "3" });
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    montra.planned().then((rows) => {
      const found = rows.find((r) => r.id === id) ?? null;
      setPlanned(found);
      if (found) {
        setForm((f) => ({
          ...f,
          expected_at: toLocalInputValue(new Date(found.expected_at)),
          amount: found.amount,
        }));
      }
    });
  }, [id]);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await montra.reschedulePlanned(id, {
        expected_at: form.expected_at,
        amount: form.amount,
        reminder_days_before: form.reminder_days_before
          ? Number(form.reminder_days_before)
          : null,
      });
      router.push("/planning");
      router.refresh();
    } catch (err) {
      setError(err instanceof MontraApiError ? err.message : "Could not reschedule.");
    } finally {
      setBusy(false);
    }
  }

  if (!planned) {
    return (
      <AppShell>
        <PageHeader title="Reschedule" icon="calendar" />
        <Skeleton className="h-48 w-full" />
      </AppShell>
    );
  }

  return (
    <AppShell>
      <PageHeader title="Reschedule" icon="calendar" />
      <Card className="mb-4">
        <p className="font-medium">{planned.description}</p>
        <p className="tabular mt-1 text-sm text-content-secondary">
          Currently {formatMoney(planned.amount, planned.currency)} on{" "}
          {planned.occurrence_date}
        </p>
      </Card>

      <Card>
        <form onSubmit={submit} className="space-y-4">
          {error && <ErrorNotice message={error} />}
          <Field label="New date">
            <Input
              type="datetime-local"
              required
              value={form.expected_at}
              onChange={(e) => setForm((f) => ({ ...f, expected_at: e.target.value }))}
            />
          </Field>
          <Field label="Amount" hint="Adjust if the figure changed too.">
            <AmountInput
              value={form.amount}
              onChange={(e) => setForm((f) => ({ ...f, amount: e.target.value }))}
            />
          </Field>
          <Field label="Remind me" hint="Days before. The old reminder is replaced.">
            <Input
              type="number"
              min={0}
              max={60}
              value={form.reminder_days_before}
              onChange={(e) =>
                setForm((f) => ({ ...f, reminder_days_before: e.target.value }))
              }
            />
          </Field>
          <div className="flex gap-3">
            <Button type="submit" disabled={busy} className="flex-1">
              {busy ? "Saving…" : "Reschedule"}
            </Button>
            <Button variant="secondary" onClick={() => router.back()}>
              Cancel
            </Button>
          </div>
        </form>
      </Card>
    </AppShell>
  );
}

export default function Page() {
  return (
    <Providers>
      <RequireSession>
        <Reschedule />
      </RequireSession>
    </Providers>
  );
}
