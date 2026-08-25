"use client";

/**
 * Daily spending over the last 30 days.
 *
 * Columns rather than a line: each day is a discrete total, and a line between
 * them would draw spending on days nothing happened. Days with nothing spent
 * are left blank rather than dropped, so the gaps are visible and the dates
 * stay evenly spaced.
 *
 * One series, so no legend — the heading names it. The bars use the app's
 * expense colour, which is what every other spending figure wears.
 *
 * Sized in real pixels from a measured width rather than a stretched viewBox:
 * non-uniform scaling turns a rounded bar end into an ellipse, the same way it
 * flattened the forecast chart's marker.
 */

import { useCallback, useEffect, useLayoutEffect, useRef, useState } from "react";

import { SpendingTrend } from "@/lib/api";
import { formatMoney } from "@/lib/format";

const HEIGHT = 120;
const PAD = { top: 8, bottom: 4 };
const GAP = 2; // Surface gap between adjacent bars.

function shortDate(iso: string): string {
  return new Date(`${iso}T00:00:00`).toLocaleDateString(undefined, {
    day: "numeric",
    month: "short",
  });
}

export function SpendingChart({ trend }: { trend: SpendingTrend }) {
  const wrapper = useRef<HTMLDivElement>(null);
  const [width, setWidth] = useState(0);
  const [active, setActive] = useState<number | null>(null);

  useLayoutEffect(() => {
    const el = wrapper.current;
    if (!el) return;
    const measure = () => setWidth(el.clientWidth);
    measure();
    const observer = new ResizeObserver(measure);
    observer.observe(el);
    return () => observer.disconnect();
  }, []);

  const points = trend.points;
  const values = points.map((p) => Number(p.amount));
  const peak = Math.max(...values, 0);
  const plotHeight = HEIGHT - PAD.top - PAD.bottom;
  const slot = points.length > 0 ? width / points.length : 0;
  const barWidth = Math.max(slot - GAP, 1);
  const average = Number(trend.daily_average);
  const averageY = peak > 0 ? PAD.top + (1 - average / peak) * plotHeight : HEIGHT;

  const pick = useCallback(
    (clientX: number) => {
      const box = wrapper.current?.getBoundingClientRect();
      if (!box || slot === 0) return;
      const index = Math.floor((clientX - box.left) / slot);
      setActive(Math.max(0, Math.min(index, points.length - 1)));
    },
    [slot, points.length],
  );

  useEffect(() => setActive(null), [trend.starts_on]);

  function onKeyDown(event: React.KeyboardEvent<HTMLDivElement>) {
    const step = event.key === "ArrowRight" ? 1 : event.key === "ArrowLeft" ? -1 : 0;
    if (step === 0) return;
    event.preventDefault();
    setActive((current) => {
      const from = current === null ? points.length - 1 : current;
      return Math.max(0, Math.min(from + step, points.length - 1));
    });
  }

  const showing = active === null ? null : points[active];

  return (
    <figure className="m-0">
      <div
        ref={wrapper}
        className="relative touch-none"
        style={{ height: HEIGHT }}
        onPointerMove={(e) => pick(e.clientX)}
        onPointerDown={(e) => pick(e.clientX)}
        onPointerLeave={() => setActive(null)}
        onKeyDown={onKeyDown}
        onBlur={() => setActive(null)}
        tabIndex={0}
        role="application"
        aria-label={`Daily spending over ${trend.days} days. Use the arrow keys to move through the dates.`}
      >
        {width > 0 && (
          <svg width={width} height={HEIGHT} className="block" aria-hidden>
            {/* The average, as a reference rather than as data. */}
            {peak > 0 && average > 0 && (
              <line
                x1={0}
                x2={width}
                y1={averageY}
                y2={averageY}
                stroke="currentColor"
                strokeWidth="1"
                strokeDasharray="3 3"
                className="text-content-muted/60"
              />
            )}

            {points.map((point, index) => {
              const value = Number(point.amount);
              if (value <= 0) return null;
              const barHeight = peak > 0 ? (value / peak) * plotHeight : 0;
              return (
                <rect
                  key={point.date}
                  x={index * slot}
                  y={HEIGHT - PAD.bottom - barHeight}
                  width={barWidth}
                  height={barHeight}
                  rx={Math.min(2, barWidth / 2)}
                  fill="#F87171"
                  // The hovered day comes forward; the rest stay quiet.
                  fillOpacity={active === null || active === index ? 0.95 : 0.45}
                />
              );
            })}
          </svg>
        )}

        {showing && slot > 0 && (
          <div
            role="tooltip"
            className="pointer-events-none absolute z-10 whitespace-nowrap rounded-control bg-surface-elevated px-2.5 py-1.5 text-xs shadow-lg ring-1 ring-white/10"
            style={{
              left: `${((active! + 0.5) / points.length) * 100}%`,
              top: 0,
              transform: `${
                active! < points.length * 0.22
                  ? "translateX(0)"
                  : active! > points.length * 0.78
                    ? "translateX(-100%)"
                    : "translateX(-50%)"
              }`,
            }}
          >
            <span className="tabular block font-semibold text-content-primary">
              {formatMoney(showing.amount, trend.currency)}
            </span>
            <span className="block text-content-secondary">{shortDate(showing.date)}</span>
          </div>
        )}
      </div>

      <figcaption className="mt-2 text-xs text-content-muted">
        <span className="flex items-baseline justify-between gap-3">
          <span>{points[0] ? shortDate(points[0].date) : ""}</span>
          <span>{formatMoney(trend.daily_average, trend.currency)} a day on average</span>
          <span>{points.length > 1 ? shortDate(points[points.length - 1].date) : ""}</span>
        </span>
        {/* Says what the bars count, so the gap between this total and the
            transaction list is explained rather than puzzling. */}
        <span className="mt-1.5 block">
          Money spent. Transfers between your own accounts are not counted.
        </span>
      </figcaption>

      {/* Every value, reachable without a pointer. */}
      <ul className="sr-only">
        {points.map((point) => (
          <li key={point.date}>
            {shortDate(point.date)}: {formatMoney(point.amount, trend.currency)}
          </li>
        ))}
      </ul>
    </figure>
  );
}
