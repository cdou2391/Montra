"use client";

import { useCallback, useEffect, useState } from "react";

import { Account, AuditEvent, Family, Invitation, MontraApiError, montra } from "@/lib/api";
import { PageHeader } from "@/components/shell";
import { useSession } from "@/components/session";
import { useFinancialContext } from "@/components/context";
import { ConfirmDialog } from "@/components/confirm-dialog";
import { ActivityLog } from "@/components/activity-log";
import { Icon } from "@/components/icons";
import { ListSkeleton } from "@/components/skeletons";
import { formatMoney } from "@/lib/format";
import {
  Button,
  Card,
  EmptyState,
  ErrorNotice,
  Field,
  Input,
  Select,
  Skeleton,
  StatusChip,
} from "@/components/ui";

/**
 * Household management (UI/UX section 52, Implementation Plan Phase 18).
 *
 * The sharing controls live here rather than buried in account settings,
 * because deciding what the household can see is one decision made once, not
 * an account-by-account afterthought.
 */

const VISIBILITY_LABELS: Record<string, string> = {
  PRIVATE: "Only me",
  FAMILY_VISIBLE: "Household can see",
  SHARED: "Shared account",
};

function CreateHousehold({ onCreated }: { onCreated: () => void }) {
  const { user } = useSession();
  const [name, setName] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function create() {
    setBusy(true);
    setError(null);
    try {
      await montra.createFamily(name, user?.base_currency ?? "RWF");
      onCreated();
    } catch (err) {
      setError(err instanceof MontraApiError ? err.message : "Could not create it.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card>
      <p className="text-section">Start a household</p>
      <p className="mt-2 text-sm text-content-secondary">
        Share what you choose with the people you live with. Nothing is shared until you say
        so — joining a household does not expose anything you already have.
      </p>
      <div className="mt-4 space-y-4">
        {error && <ErrorNotice message={error} />}
        <Field label="Household name">
          <Input
            placeholder="Our Household"
            value={name}
            onChange={(e) => setName(e.target.value)}
          />
        </Field>
        <Button onClick={create} disabled={busy || !name.trim()}>
          {busy ? "Creating…" : "Create household"}
        </Button>
      </div>
    </Card>
  );
}

function JoinHousehold({ onJoined }: { onJoined: () => void }) {
  const [token, setToken] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function join() {
    setBusy(true);
    setError(null);
    try {
      await montra.acceptInvitation(token.trim());
      onJoined();
    } catch (err) {
      setError(
        err instanceof MontraApiError ? err.message : "That invitation could not be used.",
      );
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card className="mt-4">
      <p className="text-section">Join one</p>
      <p className="mt-2 text-sm text-content-secondary">
        Paste the invitation code someone sent you.
      </p>
      <div className="mt-4 space-y-4">
        {error && <ErrorNotice message={error} />}
        <Field label="Invitation code">
          <Input value={token} onChange={(e) => setToken(e.target.value)} />
        </Field>
        <Button variant="secondary" onClick={join} disabled={busy || !token.trim()}>
          {busy ? "Joining…" : "Join household"}
        </Button>
      </div>
    </Card>
  );
}

function SharingControls({ onChanged }: { onChanged: () => void }) {
  const [accounts, setAccounts] = useState<Account[] | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);

  const load = useCallback(() => {
    montra
      .accounts()
      .then((all) => setAccounts(all.filter((a) => a.can_edit)))
      .catch(() => setAccounts([]));
  }, []);
  useEffect(load, [load]);

  async function change(account: Account, visibility: string) {
    setBusyId(account.id);
    try {
      await montra.setAccountVisibility(account.id, visibility);
      load();
      onChanged();
    } finally {
      setBusyId(null);
    }
  }

  if (accounts === null) return <ListSkeleton cards={2} />;
  // can_edit already means "yours to change", which is exactly the set whose
  // sharing you may decide.
  const mine = accounts;

  return (
    <Card>
      <p className="text-xs uppercase tracking-wide text-content-muted">What you share</p>
      <p className="mt-2 text-sm text-content-secondary">
        Household members can see what you mark visible. Only shared accounts can be spent
        from by others.
      </p>
      <div className="mt-4 space-y-3">
        {mine.map((account) => (
          <div key={account.id} className="border-t border-line/5 pt-3 first:border-0 first:pt-0">
            <div className="flex items-center justify-between gap-3">
              <div className="min-w-0">
                <p className="truncate text-sm font-medium text-content-primary">
                  {account.name}
                </p>
                <p className="mt-0.5 text-xs text-content-secondary">
                  {formatMoney(account.balance, account.currency)}
                </p>
              </div>
              <Select
                value={account.visibility}
                disabled={busyId === account.id}
                onChange={(e) => change(account, e.target.value)}
                className="max-w-[190px]"
              >
                {Object.entries(VISIBILITY_LABELS).map(([value, label]) => (
                  <option key={value} value={value}>
                    {label}
                  </option>
                ))}
              </Select>
            </div>
          </div>
        ))}
      </div>
    </Card>
  );
}

function Household({ family, onChanged }: { family: Family; onChanged: () => void }) {
  const { user } = useSession();
  const [invitations, setInvitations] = useState<Invitation[]>([]);
  const [issued, setIssued] = useState<Invitation | null>(null);
  const [email, setEmail] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [leaveOpen, setLeaveOpen] = useState(false);
  const [events, setEvents] = useState<AuditEvent[]>([]);

  const isOwner = family.role === "OWNER";

  const load = useCallback(() => {
    if (!isOwner) return;
    montra
      .invitations(family.id)
      .then((rows) => setInvitations(rows.filter((i) => i.status === "PENDING")))
      .catch(() => setInvitations([]));
  }, [family.id, isOwner]);
  useEffect(load, [load]);

  // Every member can read the trail, owner or not.
  useEffect(() => {
    montra
      .familyActivity(family.id)
      .then(setEvents)
      .catch(() => setEvents([]));
  }, [family.id]);

  // Every member can read the trail, owner or not.
  useEffect(() => {
    montra
      .familyActivity(family.id)
      .then(setEvents)
      .catch(() => setEvents([]));
  }, [family.id]);

  async function invite() {
    setBusy(true);
    setError(null);
    try {
      setIssued(await montra.invite(family.id, email.trim() || null));
      setEmail("");
      load();
    } catch (err) {
      setError(err instanceof MontraApiError ? err.message : "Could not invite them.");
    } finally {
      setBusy(false);
    }
  }

  async function leave() {
    await montra.leaveFamily(family.id);
    setLeaveOpen(false);
    onChanged();
  }

  return (
    <>
      <Card className="mb-4">
        <div className="flex items-center gap-3">
          <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-accent-muted text-accent">
            <Icon name="users" size={20} />
          </span>
          <div className="min-w-0">
            <p className="truncate text-section text-content-primary">{family.name}</p>
            <p className="mt-0.5 text-xs text-content-secondary">
              {family.members.filter((m) => m.status === "ACTIVE").length} members · you are{" "}
              {family.role.toLowerCase()}
            </p>
          </div>
        </div>
      </Card>

      <Card className="mb-4">
        <p className="mb-1 text-xs uppercase tracking-wide text-content-muted">Members</p>
        {family.members
          .filter((m) => m.status === "ACTIVE")
          .map((m) => (
            <div
              key={m.user_id}
              className="flex items-center justify-between gap-3 border-b border-line/5 py-3 last:border-0"
            >
              <div className="min-w-0">
                <p className="truncate text-sm font-medium text-content-primary">
                  {m.display_name ?? m.email}
                  {m.user_id === user?.id && (
                    <span className="ml-1 text-xs text-content-muted">(you)</span>
                  )}
                </p>
                <p className="mt-0.5 truncate text-xs text-content-secondary">{m.email}</p>
              </div>
              <StatusChip tone={m.role === "OWNER" ? "income" : "neutral"}>
                {m.role.toLowerCase()}
              </StatusChip>
            </div>
          ))}
      </Card>

      {isOwner && (
        <Card className="mb-4">
          <p className="mb-1 text-xs uppercase tracking-wide text-content-muted">Invite</p>
          {error && (
            <div className="mb-3">
              <ErrorNotice message={error} />
            </div>
          )}

          {issued?.token ? (
            <div className="rounded-control border border-accent/30 bg-accent-muted p-4">
              <p className="text-sm font-medium text-content-primary">
                Send them this code
              </p>
              <p className="mt-2 break-all font-mono text-xs text-accent">{issued.token}</p>
              {/* Shown once: only its hash is stored. */}
              <p className="mt-2 text-xs text-content-secondary">
                This is the only time it is shown. Generate a new invitation if it is lost.
              </p>
              <div className="mt-3">
                <Button variant="secondary" onClick={() => setIssued(null)}>
                  Done
                </Button>
              </div>
            </div>
          ) : (
            <div className="space-y-4">
              <Field label="Their email" hint="Optional — leave blank for an open code.">
                <Input
                  type="email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  placeholder="partner@example.com"
                />
              </Field>
              <Button onClick={invite} disabled={busy}>
                {busy ? "Creating…" : "Create invitation"}
              </Button>
            </div>
          )}

          {invitations.length > 0 && (
            <div className="mt-4 border-t border-line/5 pt-3">
              <p className="text-xs uppercase tracking-wide text-content-muted">Pending</p>
              {invitations.map((i) => (
                <div
                  key={i.id}
                  className="flex items-center justify-between gap-3 py-2 text-sm"
                >
                  <span className="truncate text-content-secondary">
                    {i.invitee_email ?? "Open invitation"}
                  </span>
                  <button
                    onClick={async () => {
                      await montra.cancelInvitation(family.id, i.id);
                      load();
                    }}
                    className="pressable shrink-0 text-xs text-semantic-expense"
                  >
                    Cancel
                  </button>
                </div>
              ))}
            </div>
          )}
        </Card>
      )}

      <div className="mb-4">
        <SharingControls onChanged={onChanged} />
      </div>

      {/* What changed in the household, and who changed it. No amounts — the
          trail is readable by every member, and the money is not. */}
      <h2 className="mb-3 text-section">Recent changes</h2>
      <div className="mb-5">
        <ActivityLog events={events} />
      </div>

      <Button variant="destructive" onClick={() => setLeaveOpen(true)}>
        Leave household
      </Button>

      <ConfirmDialog
        open={leaveOpen}
        onClose={() => setLeaveOpen(false)}
        title="Leave household"
      >
        <p className="text-section text-content-primary">Leave {family.name}?</p>
        <p className="mt-2 text-sm text-content-secondary">
          Everything you shared becomes private again, so the household will no longer see any
          of your accounts. Your own data is untouched.
        </p>
        <div className="mt-5 flex flex-col-reverse gap-3 sm:flex-row">
          <Button variant="secondary" onClick={() => setLeaveOpen(false)} className="flex-1">
            Stay
          </Button>
          <Button variant="destructive" onClick={leave} className="flex-1">
            Leave
          </Button>
        </div>
      </ConfirmDialog>
    </>
  );
}

export default function FamilyPage() {
  const { family, loading, refresh } = useFinancialContext();

  return (
    <>
      <PageHeader title="Household" icon="users" />
      {loading ? (
        <Skeleton className="h-48 w-full" />
      ) : family ? (
        <Household family={family} onChanged={refresh} />
      ) : (
        <>
          <EmptyState
            title="No household yet"
            message="Share a view of your finances with the people you live with, while keeping whatever you want to yourself."
          />
          <div className="mt-4">
            <CreateHousehold onCreated={refresh} />
            <JoinHousehold onJoined={refresh} />
          </div>
        </>
      )}
    </>
  );
}
