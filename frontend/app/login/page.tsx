"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { FormEvent, useState } from "react";

import { MontraApiError, montra } from "@/lib/api";
import { Button, Card, ErrorNotice, Field, Input } from "@/components/ui";

export default function LoginPage() {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await montra.login(email, password);
      router.push("/");
      router.refresh();
    } catch (err) {
      setError(
        err instanceof MontraApiError ? err.message : "Could not sign in. Try again.",
      );
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="mx-auto flex min-h-dvh max-w-md flex-col justify-center px-4 py-10">
      <h1 className="mb-2 text-title">Welcome back</h1>
      <p className="mb-6 text-sm text-content-secondary">Sign in to your Montra account.</p>
      <Card>
        <form onSubmit={submit} className="space-y-4">
          {error && <ErrorNotice message={error} />}
          <Field label="Email">
            <Input
              type="email"
              value={email}
              autoComplete="email"
              required
              onChange={(e) => setEmail(e.target.value)}
            />
          </Field>
          <Field label="Password">
            <Input
              type="password"
              value={password}
              autoComplete="current-password"
              required
              onChange={(e) => setPassword(e.target.value)}
            />
          </Field>
          <Button type="submit" disabled={busy} className="w-full">
            {busy ? "Signing in…" : "Sign in"}
          </Button>
        </form>
      </Card>
      <p className="mt-6 text-center text-sm text-content-secondary">
        New to Montra?{" "}
        <Link href="/register" className="text-accent">
          Create an account
        </Link>
      </p>
    </main>
  );
}
