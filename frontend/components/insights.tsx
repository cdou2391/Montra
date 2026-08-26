"use client";

/**
 * Insight list (Implementation Plan Phase 25).
 *
 * Each row is one deterministic statement. Tone is carried by an icon and the
 * wording as well as by colour, so the meaning survives for a reader who
 * cannot separate the hues.
 */

import { Insight } from "@/lib/api";
import { Icon, IconName } from "@/components/icons";
import { Card } from "@/components/ui";

const TONES: Record<Insight["tone"], { icon: IconName; className: string }> = {
  negative: { icon: "alertTriangle", className: "text-semantic-expense" },
  warning: { icon: "bell", className: "text-semantic-warning" },
  neutral: { icon: "list", className: "text-content-secondary" },
  positive: { icon: "trendingUp", className: "text-semantic-income" },
};

export function InsightList({ insights }: { insights: Insight[] }) {
  if (insights.length === 0) return null;

  return (
    <Card>
      {insights.map((insight) => {
        const tone = TONES[insight.tone] ?? TONES.neutral;
        return (
          <div
            key={`${insight.code}-${insight.title}`}
            className="flex items-start gap-3 border-b border-line/5 py-3 first:pt-0 last:border-0 last:pb-0"
          >
            <span className={`mt-0.5 shrink-0 ${tone.className}`}>
              <Icon name={tone.icon} size={18} />
            </span>
            <div className="min-w-0">
              {/* Text stays in ink tokens; the icon beside it carries the tone. */}
              <p className="text-sm font-medium text-content-primary">{insight.title}</p>
              <p className="mt-0.5 text-xs text-content-secondary">{insight.detail}</p>
            </div>
          </div>
        );
      })}
    </Card>
  );
}
