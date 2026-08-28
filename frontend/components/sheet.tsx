"use client";

/**
 * Bottom sheet (UI/UX section 41).
 *
 * For short, contextual choices where the user should not lose screen context.
 * Longer forms stay full-screen pages.
 */

import { PointerEvent as ReactPointerEvent, ReactNode, useEffect, useRef, useState } from "react";

export function BottomSheet({
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

  // Drag-to-dismiss. The handle has always looked draggable; this makes it so.
  const [dragY, setDragY] = useState(0);
  const [dragging, setDragging] = useState(false);
  const startY = useRef(0);
  const startedAt = useRef(0);

  function onPointerDown(e: ReactPointerEvent<HTMLDivElement>) {
    // Captured, so a finger that slides off the handle keeps dragging the
    // sheet rather than dropping it half-open.
    e.currentTarget.setPointerCapture(e.pointerId);
    startY.current = e.clientY;
    startedAt.current = Date.now();
    setDragging(true);
  }

  function onPointerMove(e: ReactPointerEvent<HTMLDivElement>) {
    if (!dragging) return;
    // Downwards only. Dragging up would lift the sheet off the bottom edge,
    // which is not a thing it can do.
    setDragY(Math.max(0, e.clientY - startY.current));
  }

  function onPointerUp(e: ReactPointerEvent<HTMLDivElement>) {
    if (!dragging) return;
    setDragging(false);

    const distance = Math.max(0, e.clientY - startY.current);
    const elapsed = Math.max(Date.now() - startedAt.current, 1);
    const height = panelRef.current?.offsetHeight ?? 0;

    // Far enough, or fast enough to read as a flick. Distance alone would
    // make a quick short flick spring back, which feels like the gesture was
    // refused; speed alone would close on a twitch.
    const farEnough = distance > Math.min(120, height * 0.3);
    const fastEnough = distance / elapsed > 0.5 && distance > 24;

    if (farEnough || fastEnough) {
      onClose();
    }
    setDragY(0);
  }

  useEffect(() => {
    if (!open) return;

    restoreFocusTo.current = document.activeElement as HTMLElement | null;

    // The page behind must not scroll while the sheet is up.
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";

    function onKeyDown(e: KeyboardEvent) {
      if (e.key === "Escape") {
        e.preventDefault();
        onClose();
        return;
      }
      if (e.key !== "Tab" || !panelRef.current) return;

      // Keep focus inside the sheet while it is modal.
      const focusable = panelRef.current.querySelectorAll<HTMLElement>(
        'a[href], button:not([disabled]), input, [tabindex]:not([tabindex="-1"])',
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
    // Move focus in on the next frame, once the panel is mounted.
    const raf = requestAnimationFrame(() => {
      panelRef.current
        ?.querySelector<HTMLElement>('a[href], button:not([disabled])')
        ?.focus();
    });

    // A sheet reopened after being dragged shut must start where it belongs.
    setDragY(0);
    setDragging(false);

    return () => {
      document.removeEventListener("keydown", onKeyDown);
      cancelAnimationFrame(raf);
      document.body.style.overflow = previousOverflow;
      restoreFocusTo.current?.focus();
    };
  }, [open, onClose]);

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-40 lg:hidden">
      <button
        aria-label="Close menu"
        onClick={onClose}
        className="absolute inset-0 h-full w-full bg-black/60 motion-safe:animate-[fade_150ms_ease-out]"
      />
      <div
        ref={panelRef}
        role="dialog"
        aria-modal="true"
        aria-label={title}
        className={`absolute inset-x-0 bottom-0 rounded-t-[20px] border-t border-line/10 bg-background-secondary pb-safe ${
          // The entrance animation also moves transform, so it only runs on a
          // sheet that has not been dragged.
          dragY === 0 && !dragging ? "motion-safe:animate-[sheet_200ms_ease-out]" : ""
        } ${dragging ? "" : "motion-safe:transition-transform motion-safe:duration-200"}`}
        style={dragY ? { transform: `translateY(${dragY}px)` } : undefined}
      >
        {/* Grab handle. Drag it down to dismiss; the strip is the target
            rather than the line itself, which is too thin for a thumb.
            touch-action none so the browser does not claim the gesture for
            scrolling before it reaches us. */}
        <div
          onPointerDown={onPointerDown}
          onPointerMove={onPointerMove}
          onPointerUp={onPointerUp}
          onPointerCancel={onPointerUp}
          style={{ touchAction: "none" }}
          className="flex cursor-grab justify-center pb-2 pt-3 active:cursor-grabbing"
        >
          <span aria-hidden className="h-1 w-9 rounded-full bg-line/20" />
        </div>
        <div className="px-4 pb-4 pt-2">{children}</div>
      </div>
    </div>
  );
}
