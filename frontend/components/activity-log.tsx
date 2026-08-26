"use client";

/**
 * The household's audit trail (Implementation Plan Phase 28).
 *
 * Deliberately plain: it says who did what and when, and nothing about
 * amounts. The events carry no financial detail, which is what makes them safe
 * to show every member regardless of what they can see of each other's money.
 */

import { AuditEvent } from "@/lib/api";
import { Icon, IconName } from "@/components/icons";
import { Card } from "@/components/ui";
import { formatDate, formatTime } from "@/lib/format";

const WORDING: Record<string, string> = {
  ACCOUNT_CREATED: "added an account",
  ACCOUNT_SHARED: "shared an account with the household",
  ACCOUNT_MADE_PRIVATE: "made an account private",
  ACCOUNT_VISIBILITY_CHANGED: "changed who can see an account",
  ACCOUNT_ARCHIVED: "archived an account",
  TRANSACTION_CREATED: "recorded a transaction",
  SHARED_TRANSACTION_CREATED: "recorded a transaction on a shared account",
  TRANSACTION_UPDATED: "edited a transaction",
  TRANSACTION_DELETED: "deleted a transaction",
  TRANSFER_CREATED: "made a transfer",
  TRANSFER_CANCELLED: "cancelled a transfer",
  FAMILY_CREATED: "created the household",
  FAMILY_MEMBER_INVITED: "invited someone",
  FAMILY_MEMBER_JOINED: "joined the household",
  FAMILY_MEMBER_REMOVED: "removed a member",
  FAMILY_MEMBER_LEFT: "left the household",
  FAMILY_ROLE_CHANGED: "changed a member's role",
  LOAN_PAYMENT_RECORDED: "recorded a loan payment",
  ATTACHMENT_ADDED: "attached a receipt",
  ATTACHMENT_DELETED: "removed a receipt",
};

const ICONS: Record<string, IconName> = {
  ACCOUNT: "wallet",
  TRANSACTION: "list",
  TRANSFER: "transfer",
  FAMILY: "users",
  LOAN: "handshake",
  ATTACHMENT: "paperclip",
};

export function ActivityLog({ events }: { events: AuditEvent[] }) {
  if (events.length === 0) {
    return (
      <Card>
        <p className="text-sm text-content-secondary">Nothing has happened yet.</p>
      </Card>
    );
  }

  return (
    <Card>
      {events.map((event) => (
        <div
          key={event.id}
          className="flex items-start gap-3 border-b border-line/5 py-3 first:pt-0 last:border-0 last:pb-0"
        >
          <span className="mt-0.5 shrink-0 text-content-secondary">
            <Icon name={ICONS[event.entity_type] ?? "list"} size={16} />
          </span>
          <div className="min-w-0 flex-1">
            <p className="text-sm text-content-primary">
              <span className="font-medium">
                {event.actor?.display_name ?? "Someone"}
              </span>{" "}
              {/* An unmapped event is still worth showing; a raw code beats a
                  silently missing row in a record people rely on. */}
              {WORDING[event.event_type] ?? event.event_type.toLowerCase().replace(/_/g, " ")}
            </p>
            <p className="mt-0.5 text-xs text-content-muted">
              {formatDate(event.created_at)}, {formatTime(event.created_at)}
            </p>
          </div>
        </div>
      ))}
    </Card>
  );
}
