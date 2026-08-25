"use client";

/**
 * Choosing receipts before the thing they belong to exists.
 *
 * A transaction has no id until it is saved, so there is nothing to attach to
 * while the form is being filled in. Files are held here and uploaded once the
 * record comes back with an id — which is also why upload failure is reported
 * separately: by then the money is already recorded, and pretending otherwise
 * would be worse than an awkward message.
 */

import { ChangeEvent, useRef } from "react";

import { Icon } from "@/components/icons";
import { Button } from "@/components/ui";

export const MAX_ATTACHMENT_BYTES = 10 * 1024 * 1024;
export const ACCEPTED_TYPES = "image/jpeg,image/png,image/webp,image/heic,application/pdf";

export function readableSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${Math.round(bytes / 1024)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

export function AttachmentPicker({
  files,
  onChange,
  onError,
  disabled,
  label = "Attach a receipt",
}: {
  files: File[];
  onChange: (next: File[]) => void;
  onError: (message: string) => void;
  disabled?: boolean;
  label?: string;
}) {
  const picker = useRef<HTMLInputElement>(null);

  function onPick(event: ChangeEvent<HTMLInputElement>) {
    const chosen = Array.from(event.target.files ?? []);
    // Let the same file be picked again after a rejection.
    event.target.value = "";
    if (chosen.length === 0) return;

    const tooBig = chosen.find((f) => f.size > MAX_ATTACHMENT_BYTES);
    if (tooBig) {
      onError(`${tooBig.name} is larger than 10MB.`);
      return;
    }
    onChange([...files, ...chosen]);
  }

  return (
    <div>
      {files.length > 0 && (
        <ul className="mb-3">
          {files.map((file, index) => (
            <li
              key={`${file.name}-${index}`}
              className="flex items-center gap-3 border-b border-white/5 py-2 first:pt-0 last:border-0"
            >
              <span className="shrink-0 text-content-secondary">
                <Icon name="paperclip" size={14} />
              </span>
              <span className="min-w-0 flex-1 truncate text-sm text-content-primary">
                {file.name}
              </span>
              <span className="shrink-0 text-xs text-content-muted">
                {readableSize(file.size)}
              </span>
              <button
                type="button"
                onClick={() => onChange(files.filter((_, i) => i !== index))}
                aria-label={`Remove ${file.name}`}
                className="pressable shrink-0 text-content-muted hover:text-semantic-expense"
              >
                <Icon name="trash" size={14} />
              </button>
            </li>
          ))}
        </ul>
      )}

      <input
        ref={picker}
        type="file"
        multiple
        accept={ACCEPTED_TYPES}
        onChange={onPick}
        disabled={disabled}
        className="sr-only"
      />
      <Button variant="secondary" disabled={disabled} onClick={() => picker.current?.click()}>
        {files.length > 0 ? "Add another" : label}
      </Button>
    </div>
  );
}
