"use client";

import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { FormEvent, useEffect, useState } from "react";

import { Category, MontraApiError, Transaction, montra } from "@/lib/api";
import { PageHeader } from "@/components/shell";
import { ConfirmDialog } from "@/components/confirm-dialog";
import { MoneyValue } from "@/components/financial";
import { Attachments } from "@/components/attachments";
import { SkeletonDetail } from "@/components/skeletons";
import { Button, Card, ErrorNotice, Field, Input, Select, StatusChip } from "@/components/ui";
import { formatDate, formatTime } from "@/lib/format";

/**
 * One transaction, in full.
 *
 * The amount and the account are shown but not editable here: moving money
 * between accounts is a transfer, and changing an amount after the fact is an
 * edit the ledger records rather than a field to type over. Description,
 * category and notes are what people actually come back to fix.
 */
export default function TransactionDetail() {
  const router = useRouter();
  const { id } = useParams<{ id: string }>();

  const [txn, setTxn] = useState<Transaction | null>(null);
  const [categories, setCategories] = useState<Category[]>([]);
  const [form, setForm] = useState({ description: "", merchant: "", category_id: "", notes: "" });
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [confirming, setConfirming] = useState(false);

  useEffect(() => {
    montra
      .transaction(id)
      .then((t) => {
        setTxn(t);
        setForm({
          description: t.description ?? "",
          merchant: t.merchant ?? "",
          category_id: t.category?.id ?? "",
          notes: t.notes ?? "",
        });
      })
      .catch(() => setTxn(null));
  }, [id]);

  useEffect(() => {
    if (!txn) return;
    const kind = txn.transaction_type === "INCOME" ? "INCOME" : "EXPENSE";
    montra.categories(kind).then(setCategories).catch(() => setCategories([]));
  }, [txn]);

  async function save(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const updated = await montra.updateTransaction(id, {
        description: form.description || null,
        merchant: form.merchant || null,
        category_id: form.category_id || null,
        notes: form.notes || null,
      });
      setTxn(updated);
      router.refresh();
    } catch (err) {
      setError(err instanceof MontraApiError ? err.message : "Could not save the changes.");
    } finally {
      setBusy(false);
    }
  }

  async function remove() {
    try {
      await montra.deleteTransaction(id);
      router.push("/transactions");
      router.refresh();
    } catch (err) {
      setError(err instanceof MontraApiError ? err.message : "Could not delete it.");
    }
  }

  if (!txn) return <SkeletonDetail rows={4} />;

  // A real transfer leg, as opposed to a loan payment that merely posts as a
  // transfer: the ledger refuses to edit one side of a movement on its own.
  const isTransferSide = txn.transfer_id !== null;
  const isTransfer = txn.transaction_type === "TRANSFER";

  return (
    <>
      <PageHeader title="Transaction" icon="list" />

      <Card className="mb-5">
        <div className="flex items-start justify-between gap-4">
          <div className="min-w-0">
            <p className="text-xs uppercase tracking-wide text-content-muted">
              {txn.transaction_type}
            </p>
            <p className="mt-1">
              <MoneyValue
                amount={txn.amount}
                currency={txn.currency}
                size="value"
                tone={
                  txn.transaction_type === "INCOME"
                    ? "income"
                    : txn.transaction_type === "EXPENSE"
                      ? "expense"
                      : "transfer"
                }
              />
            </p>
          </div>
          <StatusChip tone="neutral">{txn.status}</StatusChip>
        </div>

        <dl className="mt-5 grid grid-cols-2 gap-4 border-t border-line/5 pt-5 text-sm">
          {txn.fee_for_transaction_id && (
            <div className="col-span-2">
              <dt className="text-xs uppercase tracking-wide text-content-muted">Fee on</dt>
              <dd className="mt-1">
                <Link
                  href={`/transactions/${txn.fee_for_transaction_id}`}
                  className="pressable text-accent"
                >
                  The charge this fee was taken for
                </Link>
              </dd>
            </div>
          )}
          <div>
            <dt className="text-xs uppercase tracking-wide text-content-muted">Account</dt>
            <dd className="mt-1 text-content-primary">{txn.account?.name ?? "—"}</dd>
          </div>
          <div>
            <dt className="text-xs uppercase tracking-wide text-content-muted">When it happened</dt>
            <dd className="mt-1 text-content-primary">
              {formatDate(txn.occurred_at)}, {formatTime(txn.occurred_at)}
            </dd>
          </div>
          {txn.created_at && (
            <div>
              {/* Recorded after the fact is ordinary; showing both dates means
                  nobody has to wonder which one they are looking at. */}
              <dt className="text-xs uppercase tracking-wide text-content-muted">Recorded</dt>
              <dd className="mt-1 text-content-secondary">
                {formatDate(txn.created_at)}, {formatTime(txn.created_at)}
              </dd>
            </div>
          )}
          {txn.reference && (
            <div>
              <dt className="text-xs uppercase tracking-wide text-content-muted">Reference</dt>
              <dd className="mt-1 text-content-secondary">{txn.reference}</dd>
            </div>
          )}
        </dl>
      </Card>

      <h2 className="mb-3 text-section">Details</h2>
      <Card className="mb-5">
        {isTransferSide ? (
          <p className="text-sm text-content-secondary">
            This is one side of a transfer. Editing it alone would leave the two
            sides disagreeing, so change it by cancelling the transfer and
            making it again.
          </p>
        ) : (
        <form onSubmit={save} className="space-y-4">
          {error && <ErrorNotice message={error} />}
          <Field label="Description">
            <Input
              value={form.description}
              onChange={(e) => setForm((f) => ({ ...f, description: e.target.value }))}
            />
          </Field>
          <Field label="Merchant">
            <Input
              value={form.merchant}
              onChange={(e) => setForm((f) => ({ ...f, merchant: e.target.value }))}
            />
          </Field>
          {!isTransfer && (
            <Field label="Category">
              <Select
                value={form.category_id}
                onChange={(e) => setForm((f) => ({ ...f, category_id: e.target.value }))}
              >
                <option value="">Uncategorised</option>
                {categories.map((c) => (
                  <option key={c.id} value={c.id}>
                    {c.name}
                  </option>
                ))}
              </Select>
            </Field>
          )}
          <Field label="Notes">
            <Input
              value={form.notes}
              onChange={(e) => setForm((f) => ({ ...f, notes: e.target.value }))}
            />
          </Field>
          <div className="flex gap-3">
            <Button type="submit" disabled={busy} className="flex-1">
              {busy ? "Saving…" : "Save"}
            </Button>
            <Button variant="secondary" onClick={() => router.back()}>
              Back
            </Button>
          </div>
        </form>
        )}
      </Card>

      <h2 className="mb-3 text-section">Receipts</h2>
      <div className="mb-5">
        <Attachments transactionId={id} />
      </div>

      <Button variant="destructive" onClick={() => setConfirming(true)}>
        Delete transaction
      </Button>

      <ConfirmDialog
        open={confirming}
        onClose={() => setConfirming(false)}
        title="Delete transaction"
      >
        <p className="text-section text-content-primary">Delete this transaction?</p>
        <p className="mt-2 text-sm text-content-secondary">
          {/* Deleting is not a correction to a number on a screen; the
              account's balance is derived from these rows and will move. */}
          The account balance will change to match. This cannot be undone.
        </p>
        <div className="mt-5 flex gap-3">
          <Button variant="destructive" onClick={remove} className="flex-1">
            Delete
          </Button>
          <Button variant="secondary" onClick={() => setConfirming(false)}>
            Cancel
          </Button>
        </div>
      </ConfirmDialog>
    </>
  );
}
