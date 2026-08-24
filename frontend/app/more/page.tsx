"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";

import { montra } from "@/lib/api";
import { AppShell, PageHeader } from "@/components/shell";
import { Providers } from "@/app/providers";
import { RequireSession, useSession } from "@/components/session";
import { Button, Card } from "@/components/ui";
import { Avatar } from "@/components/avatar";

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
      <Link href="/profile" className="mb-4 block">
        <Card className="transition hover:bg-surface-elevated">
          <div className="flex items-center gap-4">
            {user && <Avatar user={user} />}
            <div className="min-w-0">
              <p className="truncate font-medium">{user?.display_name ?? user?.email}</p>
              <p className="mt-0.5 text-xs text-content-muted">
                {user?.base_currency} · {user?.timezone}
              </p>
            </div>
            <span aria-hidden className="ml-auto text-content-muted">
              ›
            </span>
          </div>
        </Card>
      </Link>

      <Card className="mb-4">
        <p className="text-section">Go to</p>
        <div className="mt-3 space-y-1">
          {[
            { href: "/profile", label: "Profile and preferences" },
            { href: "/notifications", label: "Notifications" },
            { href: "/transactions", label: "Activity" },
            { href: "/planning/recurring", label: "Recurring" },
            { href: "/accounts", label: "Accounts" },
          ].map((item) => (
            <Link
              key={item.href}
              href={item.href}
              className="flex min-h-[44px] items-center rounded-control px-3 text-sm text-content-secondary transition hover:bg-white/5 hover:text-content-primary"
            >
              {item.label}
            </Link>
          ))}
        </div>
      </Card>

      <Card className="mb-4">
        <p className="text-section">Coming next</p>
        <ul className="mt-3 space-y-2 text-sm text-content-secondary">
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
