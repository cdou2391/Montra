"use client";

/**
 * Receipts on a transaction (Implementation Plan Phase 27).
 *
 * The file goes straight from the browser to object storage; this component
 * only asks the API for permission and then tells it the upload landed. No
 * file URL is ever stored — opening one costs a fresh request, which is what
 * keeps a shared link from outliving the permission behind it.
 */

import { ChangeEvent, useEffect, useRef, useState } from "react";

import { Attachment, MontraApiError, montra } from "@/lib/api";
import { Icon } from "@/components/icons";
import { Button, Card, ErrorNotice } from "@/components/ui";

const MAX_BYTES = 10 * 1024 * 1024;

function readableSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${Math.round(bytes / 1024)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

export function Attachments({ transactionId }: { transactionId: string }) {
  const [items, setItems] = useState<Attachment[] | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const picker = useRef<HTMLInputElement>(null);

  useEffect(() => {
    montra
      .attachments(transactionId)
      .then(setItems)
      .catch(() => setItems([]));
  }, [transactionId]);

  async function onPick(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    // Let the same file be picked again after a failure.
    event.target.value = "";
    if (!file) return;

    if (file.size > MAX_BYTES) {
      setError("That file is larger than 10MB.");
      return;
    }

    setBusy(true);
    setError(null);
    try {
      const added = await montra.uploadAttachment(transactionId, file);
      setItems((current) => [...(current ?? []), added]);
    } catch (err) {
      setError(
        err instanceof MontraApiError ? err.message : "The file could not be attached.",
      );
    } finally {
      setBusy(false);
    }
  }

  async function open(attachment: Attachment) {
    try {
      const url = await montra.attachmentUrl(attachment.id);
      window.open(url, "_blank", "noopener,noreferrer");
    } catch {
      setError("That file could not be opened.");
    }
  }

  async function remove(attachment: Attachment) {
    try {
      await montra.deleteAttachment(attachment.id);
      setItems((current) => (current ?? []).filter((a) => a.id !== attachment.id));
    } catch {
      setError("That file could not be removed.");
    }
  }

  return (
    <Card>
      {error && (
        <div className="mb-4">
          <ErrorNotice message={error} />
        </div>
      )}

      {items && items.length > 0 && (
        <ul className="mb-4">
          {items.map((a) => (
            <li
              key={a.id}
              className="flex items-center gap-3 border-b border-white/5 py-3 first:pt-0 last:border-0 last:pb-0"
            >
              <span className="shrink-0 text-content-secondary">
                <Icon name="paperclip" size={16} />
              </span>
              <button
                onClick={() => open(a)}
                className="pressable min-w-0 flex-1 text-left"
              >
                <span className="block truncate text-sm text-content-primary hover:text-accent">
                  {a.file_name}
                </span>
                <span className="block text-xs text-content-muted">
                  {readableSize(a.file_size)}
                </span>
              </button>
              <button
                onClick={() => remove(a)}
                aria-label={`Remove ${a.file_name}`}
                className="pressable shrink-0 text-content-muted hover:text-semantic-expense"
              >
                <Icon name="trash" size={16} />
              </button>
            </li>
          ))}
        </ul>
      )}

      {items && items.length === 0 && (
        <p className="mb-4 text-sm text-content-secondary">
          No receipts attached yet.
        </p>
      )}

      {/* A hidden input driven by a real button, rather than a button nested
          in a label — a nested button swallows the click the label forwards. */}
      <input
        ref={picker}
        type="file"
        accept="image/jpeg,image/png,image/webp,image/heic,application/pdf"
        onChange={onPick}
        disabled={busy}
        className="sr-only"
      />
      <Button variant="secondary" disabled={busy} onClick={() => picker.current?.click()}>
        {busy ? "Attaching…" : "Attach a receipt"}
      </Button>
      <p className="mt-2 text-xs text-content-muted">Images or PDF, up to 10MB.</p>
    </Card>
  );
}
