"use client";

/**
 * Destructive confirmation (UI/UX sections 68, 81).
 *
 * Bottom sheet on mobile, centred dialog on desktop — the spec is explicit
 * that desktop-style modals should not be forced onto narrow screens.
 */

import { ReactNode, useEffect, useRef } from "react";

export function ConfirmDialog({
  open,
  onClose,
  title,
  children,
}: {
  open: boolean;
  onClose: () => void;
  title: string;
  children: ReactNode;
}) {
  const panelRef = useRef<HTMLDivElement>(null);
  const restoreFocusTo = useRef<HTMLElement | null>(null);

  useEffect(() => {
    if (!open) return;
    restoreFocusTo.current = document.activeElement as HTMLElement | null;
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";

    function onKeyDown(e: KeyboardEvent) {
      if (e.key === "Escape") {
        e.preventDefault();
        onClose();
        return;
      }
      if (e.key !== "Tab" || !panelRef.current) return;
      const focusable = panelRef.current.querySelectorAll<HTMLElement>(
        'a[href], button:not([disabled]), input:not([disabled]), [tabindex]:not([tabindex="-1"])',
      );
      if (focusable.length === 0) return;
      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      if (e.shiftKey && document.activeElement === first) {
        e.preventDefault();
        last.focus();
      } else if (!e.shiftKey && document.activeElement === last) {
        e.preventDefault();
        first.focus();
      }
    }

    document.addEventListener("keydown", onKeyDown);
    // Focus the first input rather than a button, so a destructive action is
    // never one stray Enter away.
    const raf = requestAnimationFrame(() => {
      const target =
        panelRef.current?.querySelector<HTMLElement>("input") ??
        panelRef.current?.querySelector<HTMLElement>("button");
      target?.focus();
    });

    return () => {
      document.removeEventListener("keydown", onKeyDown);
      cancelAnimationFrame(raf);
      document.body.style.overflow = previousOverflow;
      restoreFocusTo.current?.focus();
    };
  }, [open, onClose]);

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-end justify-center lg:items-center">
      <button
        aria-label="Cancel"
        onClick={onClose}
        className="absolute inset-0 h-full w-full bg-black/70 motion-safe:animate-[fade_150ms_ease-out]"
      />
      <div
        ref={panelRef}
        role="alertdialog"
        aria-modal="true"
        aria-label={title}
        className="
          relative w-full max-w-lg rounded-t-[20px] border-t border-white/10
          bg-background-secondary pb-safe motion-safe:animate-[sheet_200ms_ease-out]
          lg:rounded-card lg:border lg:pb-0 lg:motion-safe:animate-[fade_150ms_ease-out]
        "
      >
        <div className="flex justify-center pb-1 pt-3 lg:hidden">
          <span aria-hidden className="h-1 w-9 rounded-full bg-white/20" />
        </div>
        <div className="p-5">{children}</div>
      </div>
    </div>
  );
}
