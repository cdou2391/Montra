"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { FormEvent, useState } from "react";

import { MontraApiError, montra } from "@/lib/api";
import { Logo } from "@/components/logo";
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
    // Centred only when there is room for it. On a phone the keyboard takes
    // roughly half the screen, and a centred form puts the password field and
    // the submit button underneath it — so below that height the form sits at
    // the top and stays reachable.
    <main
      className="
        mx-auto flex min-h-dvh max-w-md flex-col justify-start px-4 py-4
        [@media(min-height:720px)]:py-10 [@media(min-height:720px)]:justify-center
      "
    >
      {/* On a small phone with the keyboard up there is no room for a
          wordmark and a sign-in form. The heading below still says which
          page this is, and the mark was on screen before the keyboard
          opened. */}
      <div className="mb-3 hidden items-center gap-3 [@media(min-height:380px)]:flex [@media(min-height:720px)]:mb-5">
        <Logo size={40} />
        <span className="text-title text-content-primary">Montra</span>
      </div>
      <h1 className="mb-1 text-title [@media(min-height:720px)]:mb-2">Create your account</h1>
      <p className="mb-4 hidden text-sm text-content-secondary [@media(min-height:640px)]:block [@media(min-height:720px)]:mb-6">
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
            hint="At least 12 characters. A few words you will remember beats a short one with symbols in it."
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
