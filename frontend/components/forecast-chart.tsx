"use client";

/**
 * Projected balance over time.
 *
 * One series, so there is no legend — the title names it. The line uses the
 * app's accent; the only other colour is the reserved expense red marking the
 * point a balance is projected to cross zero, which ships with a written
 * warning rather than relying on colour alone.
 *
 * A crosshair finds the date, because nobody aims at a 2px line. Every value
 * the tooltip shows is also in the table below it, so hovering is an
 * enhancement and never the only way to read a number.
 */

import { useId, useMemo, useRef, useState } from "react";

import { Forecast } from "@/lib/api";
import { formatMoney } from "@/lib/format";

const HEIGHT = 160;
const PAD = { top: 12, right: 4, bottom: 18, left: 4 };

export function ForecastChart({ forecast }: { forecast: Forecast }) {
  const svgRef = useRef<SVGSVGElement>(null);
  const [active, setActive] = useState<number | null>(null);
  const gradientId = useId();

  const points = forecast.points;
  const geometry = useMemo(() => {
    const values = points.map((p) => Number(p.projected_balance));
    const min = Math.min(...values, 0);
    const max = Math.max(...values, 0);
    const span = max - min || 1;
    const width = 100; // viewBox units, so the SVG scales to its container
    const plotH = HEIGHT - PAD.top - PAD.bottom;

    const xy = values.map((v, i) => ({
      x: PAD.left + (i / Math.max(points.length - 1, 1)) * (width - PAD.left - PAD.right),
      y: PAD.top + (1 - (v - min) / span) * plotH,
      value: v,
    }));
    const zeroY = PAD.top + (1 - (0 - min) / span) * plotH;
    return { xy, zeroY, min, max };
  }, [points]);

  const line = geometry.xy.map((p, i) => `${i === 0 ? "M" : "L"}${p.x},${p.y}`).join(" ");
  const area =
    `M${geometry.xy[0]?.x},${HEIGHT - PAD.bottom} ` +
    geometry.xy.map((p) => `L${p.x},${p.y}`).join(" ") +
    ` L${geometry.xy[geometry.xy.length - 1]?.x},${HEIGHT - PAD.bottom} Z`;

  // The first day any account is projected below zero, if the API found one.
  const warningIndex = forecast.warnings.length
    ? points.findIndex((p) => p.date === forecast.warnings[0].date)
    : -1;

  function onMove(event: React.PointerEvent<SVGSVGElement>) {
    const svg = svgRef.current;
    if (!svg) return;
    const rect = svg.getBoundingClientRect();
    const ratio = (event.clientX - rect.left) / rect.width;
    // Snap to the nearest date rather than the exact pixel.
    const index = Math.round(ratio * (points.length - 1));
    setActive(Math.max(0, Math.min(index, points.length - 1)));
  }

  const shown = active === null ? points.length - 1 : active;
  const showing = points[shown];

  return (
    <figure className="m-0">
      <svg
        ref={svgRef}
        viewBox={`0 0 100 ${HEIGHT}`}
        preserveAspectRatio="none"
        role="img"
        aria-label={`Projected balance over ${forecast.period === "7d" ? "7" : "30"} days`}
        className="h-40 w-full touch-none"
        onPointerMove={onMove}
        onPointerLeave={() => setActive(null)}
      >
        <defs>
          <linearGradient id={gradientId} x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="#2DD4BF" stopOpacity="0.28" />
            <stop offset="100%" stopColor="#2DD4BF" stopOpacity="0" />
          </linearGradient>
        </defs>

        {/* Zero line, recessive: it is a reference, not data. */}
        {geometry.min < 0 && (
          <line
            x1={PAD.left}
            x2={100 - PAD.right}
            y1={geometry.zeroY}
            y2={geometry.zeroY}
            stroke="currentColor"
            strokeWidth="0.5"
            strokeDasharray="2 2"
            className="text-content-muted"
            vectorEffect="non-scaling-stroke"
          />
        )}

        <path d={area} fill={`url(#${gradientId})`} />
        <path
          d={line}
          fill="none"
          stroke="#2DD4BF"
          strokeWidth="2"
          strokeLinecap="round"
          strokeLinejoin="round"
          vectorEffect="non-scaling-stroke"
        />

        {/* The warning belongs to one account, while this line is the total
            across all of them. Marking the date with a rule says "something
            happens here"; a dot on the line would claim the total itself is
            the problem, which it usually is not. */}
        {warningIndex >= 0 && geometry.xy[warningIndex] && (
          <line
            x1={geometry.xy[warningIndex].x}
            x2={geometry.xy[warningIndex].x}
            y1={PAD.top}
            y2={HEIGHT - PAD.bottom}
            stroke="#F87171"
            strokeWidth="1.5"
            strokeDasharray="3 3"
            vectorEffect="non-scaling-stroke"
          />
        )}

        {active !== null && geometry.xy[active] && (
          <>
            <line
              x1={geometry.xy[active].x}
              x2={geometry.xy[active].x}
              y1={PAD.top}
              y2={HEIGHT - PAD.bottom}
              stroke="currentColor"
              strokeWidth="1"
              className="text-content-muted"
              vectorEffect="non-scaling-stroke"
            />
            <circle
              cx={geometry.xy[active].x}
              cy={geometry.xy[active].y}
              r="3.5"
              fill="#2DD4BF"
              stroke="#141E2B"
              strokeWidth="1.5"
            />
          </>
        )}
      </svg>

      {/* Values lead, labels follow. */}
      <figcaption
        aria-live="polite"
        className="mt-2 flex items-baseline justify-between gap-3 text-xs"
      >
        <span className="tabular font-semibold text-content-primary">
          {showing ? formatMoney(showing.projected_balance, forecast.currency) : "—"}
        </span>
        <span className="text-content-secondary">
          {showing
            ? new Date(`${showing.date}T00:00:00`).toLocaleDateString(undefined, {
                day: "numeric",
                month: "short",
              })
            : ""}
        </span>
      </figcaption>
    </figure>
  );
}

/** Every plotted value, reachable without a pointer. */
export function ForecastTable({ forecast }: { forecast: Forecast }) {
  const weekly = forecast.points.filter((_, i) => i % 7 === 0 || i === forecast.points.length - 1);
  return (
    <table className="w-full text-sm">
      <caption className="sr-only">Projected balance by date</caption>
      <thead>
        <tr className="text-left text-xs uppercase tracking-wide text-content-muted">
          <th scope="col" className="pb-2 font-normal">
            Date
          </th>
          <th scope="col" className="pb-2 text-right font-normal">
            Projected
          </th>
        </tr>
      </thead>
      <tbody>
        {weekly.map((point) => (
          <tr key={point.date} className="border-t border-white/5">
            <td className="py-2 text-content-secondary">
              {new Date(`${point.date}T00:00:00`).toLocaleDateString(undefined, {
                day: "numeric",
                month: "short",
              })}
            </td>
            <td
              className={`tabular py-2 text-right font-medium ${
                Number(point.projected_balance) < 0
                  ? "text-semantic-expense"
                  : "text-content-primary"
              }`}
            >
              {formatMoney(point.projected_balance, forecast.currency)}
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
