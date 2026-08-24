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
        -mx-4 flex snap-x snap-mandatory gap-3 overflow-x-auto px-4 pb-2
        [scrollbar-width:none] [&::-webkit-scrollbar]:hidden
        focus:outline-none focus-visible:ring-2 focus-visible:ring-accent/60
        sm:-mx-6 sm:px-6
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

export function CarouselDots({
  accounts,
  index,
  select,
}: {
  accounts: Account[];
  index: number;
  select: (i: number) => void;
}) {
  if (accounts.length < 2) return null;
  return (
    <div className="mt-4 flex items-center justify-center gap-2">
      {accounts.map((account, i) => (
        <button
          key={account.id}
          onClick={() => select(i)}
          aria-label={`Show ${account.name}`}
          aria-current={i === index}
          // Hit area stays 44px tall even though the dot is small.
          className="flex h-11 w-6 items-center justify-center"
        >
          <span
            className={`block rounded-full transition-all ${
              i === index ? "h-2 w-6 bg-accent" : "h-2 w-2 bg-white/20"
            }`}
          />
        </button>
      ))}
    </div>
  );
}

export function CarouselArrows({
  index,
  count,
  select,
}: {
  index: number;
  count: number;
  select: (i: number) => void;
}) {
  if (count < 2) return null;
  const base =
    "flex h-10 w-10 items-center justify-center rounded-full border border-white/10 bg-surface-elevated text-content-secondary transition hover:text-content-primary disabled:opacity-30 disabled:hover:text-content-secondary";
  return (
    <div className="hidden items-center gap-2 sm:flex">
      <button
        onClick={() => select(index - 1)}
        disabled={index === 0}
        aria-label="Previous account"
        className={base}
      >
        ‹
      </button>
      <button
        onClick={() => select(index + 1)}
        disabled={index >= count - 1}
        aria-label="Next account"
        className={base}
      >
        ›
      </button>
    </div>
  );
}
