"use client";

/**
 * Account carousel — one account at a time.
 *
 * Built on CSS scroll-snap rather than a carousel library: native momentum
 * scrolling on touch, real trackpad support, and it degrades to a plain
 * scrollable row if JavaScript is slow to hydrate.
 */

import { useCallback, useEffect, useRef, useState } from "react";

import { Account } from "@/lib/api";
import { Icon } from "@/components/icons";

export function useCarousel(count: number) {
  const trackRef = useRef<HTMLDivElement>(null);
  const [index, setIndex] = useState(0);

  // Derive the active slide from scroll position. With mandatory snapping the
  // track settles on exact multiples, so rounding is stable.
  const onScroll = useCallback(() => {
    const track = trackRef.current;
    if (!track) return;
    const slide = track.clientWidth;
    if (slide === 0) return;
    const next = Math.round(track.scrollLeft / slide);
    setIndex((current) => (next === current ? current : Math.min(next, count - 1)));
  }, [count]);

  // Selection is state first, scrolling second. The desktop layout hides the
  // track entirely, where clientWidth is 0 and no scroll event would ever fire
  // to move the index along.
  const select = useCallback(
    (target: number) => {
      const clamped = Math.max(0, Math.min(target, count - 1));
      setIndex(clamped);
      const track = trackRef.current;
      if (track && track.clientWidth > 0) {
        track.scrollTo({ left: clamped * track.clientWidth, behavior: "smooth" });
      }
    },
    [count],
  );

  // Keep the index in range if accounts are archived while the page is open.
  useEffect(() => {
    if (index > count - 1) setIndex(Math.max(count - 1, 0));
  }, [count, index]);

  return { trackRef, index, onScroll, select };
}

export function CarouselTrack({
  trackRef,
  onScroll,
  onKeyDown,
  children,
  label,
}: {
  trackRef: React.RefObject<HTMLDivElement | null>;
  onScroll: () => void;
  onKeyDown?: (e: React.KeyboardEvent) => void;
  children: React.ReactNode;
  label: string;
}) {
  return (
    <div
      ref={trackRef}
      onScroll={onScroll}
      onKeyDown={onKeyDown}
      role="region"
      aria-roledescription="carousel"
      aria-label={label}
      tabIndex={0}
      className="
        flex min-w-0 flex-1 snap-x snap-mandatory gap-3 overflow-x-auto
        [scrollbar-width:none] [&::-webkit-scrollbar]:hidden
        focus:outline-none focus-visible:rounded-card focus-visible:ring-2
        focus-visible:ring-accent/60
      "
    >
      {children}
    </div>
  );
}

export function CarouselSlide({
  children,
  label,
  position,
  total,
}: {
  children: React.ReactNode;
  label: string;
  position: number;
  total: number;
}) {
  return (
    <div
      role="group"
      aria-roledescription="slide"
      aria-label={`${label} — ${position} of ${total}`}
      className="w-full shrink-0 snap-center"
    >
      {children}
    </div>
  );
}

/**
 * A chevron flanking the carousel. Stays mounted when disabled so the track
 * never changes width at either end of the run.
 */
export function CarouselChevron({
  direction,
  disabled,
  onClick,
  label,
}: {
  direction: "left" | "right";
  disabled: boolean;
  onClick: () => void;
  label: string;
}) {
  return (
    <button
      onClick={onClick}
      disabled={disabled}
      aria-label={label}
      className="
        pressable pressable-tint flex h-11 w-7 shrink-0 items-center
        justify-center rounded-control text-content-secondary sm:w-9
        focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/60
        disabled:opacity-20 disabled:active:scale-100
      "
    >
      <Icon name={direction === "left" ? "chevronLeft" : "chevronRight"} />
    </button>
  );
}

/** Compact position readout, announced to screen readers as it changes. */
export function CarouselPosition({
  index,
  count,
  label,
}: {
  index: number;
  count: number;
  label?: string;
}) {
  if (count < 2) return null;
  return (
    <p aria-live="polite" className="mt-3 text-center text-xs text-content-muted">
      <span className="text-content-secondary">{index + 1}</span> of {count}
      {label ? <span className="sr-only"> — {label}</span> : null}
    </p>
  );
}
