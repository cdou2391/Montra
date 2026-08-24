"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { FormEvent, useState } from "react";

import { MontraApiError, montra } from "@/lib/api";
import { Button, Card, ErrorNotice, Field, Input, Select } from "@/components/ui";

const CURRENCIES = ["RWF", "USD", "EUR", "GBP", "KES", "UGX", "TZS"];

export default function RegisterPage() {
  const router = useRouter();
  const [form, setForm] = useState({
    email: "",
    password: "",
    display_name: "",
    base_currency: "RWF",
    timezone:
      Intl.DateTimeFormat().resolvedOptions().timeZone || "Africa/Kigali",
  });
  const [error, setError] = useState<string | null>(null);
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState(false);

  function update(key: keyof typeof form, value: string) {
    setForm((f) => ({ ...f, [key]: value }));
  }

  async function submit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    setFieldErrors({});
    try {
      await montra.register(form);
      // Phase 3: land in onboarding, which asks for the first account.
      router.push("/accounts/new?onboarding=1");
      router.refresh();
    } catch (err) {
      if (err instanceof MontraApiError) {
        setError(err.message);
        if (err.details) {
          setFieldErrors(
            Object.fromEntries(err.details.map((d) => [d.field, d.message])),
          );
        }
      } else {
        setError("Could not create your account. Try again.");
      }
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="mx-auto flex min-h-dvh max-w-md flex-col justify-center px-4 py-10">
      <h1 className="mb-2 text-title">Create your account</h1>
      <p className="mb-6 text-sm text-content-secondary">
        One place for what you have, what you owe, and what is coming next.
      </p>
      <Card>
        <form onSubmit={submit} className="space-y-4">
          {error && <ErrorNotice message={error} />}
          <Field label="Name">
            <Input
              value={form.display_name}
              onChange={(e) => update("display_name", e.target.value)}
            />
          </Field>
          <Field label="Email" error={fieldErrors.email}>
            <Input
              type="email"
              required
              autoComplete="email"
              value={form.email}
              onChange={(e) => update("email", e.target.value)}
            />
          </Field>
          <Field
            label="Password"
            hint="At least 10 characters, mixing letters with numbers or symbols."
            error={fieldErrors.password}
          >
            <Input
              type="password"
              required
              autoComplete="new-password"
              value={form.password}
              onChange={(e) => update("password", e.target.value)}
            />
          </Field>
          <Field label="Base currency" hint="Used for net worth and totals.">
            <Select
              value={form.base_currency}
              onChange={(e) => update("base_currency", e.target.value)}
            >
              {CURRENCIES.map((c) => (
                <option key={c} value={c}>
                  {c}
                </option>
              ))}
            </Select>
          </Field>
          <Button type="submit" disabled={busy} className="w-full">
            {busy ? "Creating…" : "Create account"}
          </Button>
        </form>
      </Card>
      <p className="mt-6 text-center text-sm text-content-secondary">
        Already have an account?{" "}
        <Link href="/login" className="text-accent">
          Sign in
        </Link>
      </p>
    </main>
  );
}
