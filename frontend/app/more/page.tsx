"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";

import { montra } from "@/lib/api";
import { AppShell, PageHeader } from "@/components/shell";
import { Providers } from "@/app/providers";
import { RequireSession, useSession } from "@/components/session";
import { Button, Card } from "@/components/ui";

function More() {
  const { user } = useSession();
  const router = useRouter();

  async function signOut() {
    await montra.logout();
    router.push("/login");
    router.refresh();
  }

  return (
    <AppShell>
      <PageHeader title="More" />
      <Card className="mb-4">
        <p className="text-sm text-content-secondary">Signed in as</p>
        <p className="mt-1 font-medium">{user?.email}</p>
        <p className="mt-1 text-xs text-content-muted">
          Base currency {user?.base_currency} · {user?.timezone}
        </p>
      </Card>

      <Card className="mb-4">
        <p className="text-section">Coming next</p>
        <ul className="mt-3 space-y-2 text-sm text-content-secondary">
          <li>Upcoming and recurring transactions</li>
          <li>Loans you owe and are owed</li>
          <li>Household sharing</li>
          <li>Cash-flow forecast and insights</li>
        </ul>
      </Card>

      <div className="flex gap-3">
        <Link href="/accounts/new">
          <Button variant="secondary">Add account</Button>
        </Link>
        <Button variant="destructive" onClick={signOut}>
          Sign out
        </Button>
      </div>
    </AppShell>
  );
}

export default function Page() {
  return (
    <Providers>
      <RequireSession>
        <More />
      </RequireSession>
    </Providers>
  );
}
