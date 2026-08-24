"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import { Account, montra } from "@/lib/api";
import { AppShell, PageHeader } from "@/components/shell";
import { Providers } from "@/app/providers";
import { RequireSession } from "@/components/session";
import { AccountCard } from "@/components/financial";
import { Button, EmptyState, Skeleton } from "@/components/ui";

function Accounts() {
  const [accounts, setAccounts] = useState<Account[] | null>(null);

  useEffect(() => {
    montra.accounts().then(setAccounts).catch(() => setAccounts([]));
  }, []);

  const assets = (accounts ?? []).filter((a) => a.account_nature === "ASSET");
  const liabilities = (accounts ?? []).filter((a) => a.account_nature === "LIABILITY");

  return (
    <AppShell>
      <PageHeader
        title="Accounts"
        action={
          <Link href="/accounts/new">
            <Button>Add</Button>
          </Link>
        }
      />
      {accounts === null ? (
        <div className="space-y-3">
          <Skeleton className="h-20 w-full" />
          <Skeleton className="h-20 w-full" />
        </div>
      ) : accounts.length === 0 ? (
        <EmptyState
          title="No accounts yet"
          message="Add a bank account, cash, mobile money or a card to get started."
          action={
            <Link href="/accounts/new">
              <Button>Add account</Button>
            </Link>
          }
        />
      ) : (
        <div className="space-y-8">
          <section className="space-y-3">
            <h2 className="text-section text-content-secondary">What you have</h2>
            {assets.map((a) => (
              <AccountCard key={a.id} account={a} />
            ))}
          </section>
          {liabilities.length > 0 && (
            <section className="space-y-3">
              <h2 className="text-section text-content-secondary">What you owe</h2>
              {liabilities.map((a) => (
                <AccountCard key={a.id} account={a} />
              ))}
            </section>
          )}
        </div>
      )}
    </AppShell>
  );
}

export default function Page() {
  return (
    <Providers>
      <RequireSession>
        <Accounts />
      </RequireSession>
    </Providers>
  );
}
