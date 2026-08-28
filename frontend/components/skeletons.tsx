import { Card, Skeleton } from "@/components/ui";

/**
 * Loading states shaped like what replaces them.
 *
 * A single grey slab holds space without predicting anything, so the page
 * visibly rearranges the moment the data lands. These mirror the real
 * structure instead: a card where a card goes, a row of tiles where tiles go,
 * repeated lines where a list goes.
 *
 * They are deliberately plain. A placeholder that reproduces every border and
 * label becomes a second copy of the layout to keep in step, and the point is
 * the shape rather than the detail.
 */

/** A heading and its trailing link, as most sections carry. */
function SectionHeading({ wide = false }: { wide?: boolean }) {
  return (
    <div className="mb-3 flex items-center justify-between">
      <Skeleton className={`h-4 ${wide ? "w-40" : "w-28"}`} />
      <Skeleton className="h-3 w-14" />
    </div>
  );
}

/** Repeated lines: a title over a subtitle, with an amount on the right. */
export function SkeletonRows({ rows = 4 }: { rows?: number }) {
  return (
    <Card>
      {Array.from({ length: rows }).map((_, i) => (
        <div
          key={i}
          className="flex items-center justify-between gap-4 border-b border-line/5 py-4 last:border-0"
        >
          <div className="min-w-0 flex-1 space-y-2">
            <Skeleton className="h-4 w-1/2" />
            <Skeleton className="h-3 w-3/4" />
          </div>
          <Skeleton className="h-4 w-20 shrink-0" />
        </div>
      ))}
    </Card>
  );
}

/** The Home dashboard: net worth, the two metrics, accounts, chart, lists. */
export function HomeSkeleton() {
  return (
    <>
      <Card className="mb-4">
        <Skeleton className="h-4 w-24" />
        <Skeleton className="mt-3 h-8 w-56" />
      </Card>

      <div className="mb-6 grid grid-cols-2 gap-3">
        {[0, 1].map((i) => (
          <Card key={i}>
            <Skeleton className="h-4 w-16" />
            <Skeleton className="mt-3 h-6 w-24" />
          </Card>
        ))}
      </div>

      <section className="mb-6">
        <SectionHeading />
        {/* The tiles scroll sideways, so the row is what is shown rather than
            a full-width block. */}
        <div className="flex gap-3 overflow-hidden">
          {[0, 1, 2].map((i) => (
            <Skeleton key={i} className="h-[76px] w-44 shrink-0" />
          ))}
        </div>
      </section>

      <section className="mb-6">
        <SectionHeading />
        <Skeleton className="h-44 w-full" />
      </section>

      <section className="mb-6">
        <SectionHeading />
        <SkeletonRows rows={3} />
      </section>

      <section>
        <SectionHeading />
        <SkeletonRows rows={4} />
      </section>
    </>
  );
}

/** Accounts: the carousel card, then the activity beneath it. */
export function AccountsSkeleton() {
  return (
    <>
      <div className="mb-2 flex items-center gap-1">
        <Skeleton className="h-8 w-6 shrink-0" />
        <Skeleton className="h-[168px] flex-1" />
        <Skeleton className="h-8 w-6 shrink-0" />
      </div>

      <section className="mt-8">
        <SectionHeading />
        <div className="mb-4 grid grid-cols-2 gap-3">
          <Skeleton className="h-12" />
          <Skeleton className="h-12" />
        </div>
        <SkeletonRows rows={5} />
      </section>
    </>
  );
}

/** A list page: budgets, goals, loans, upcoming. */
export function ListSkeleton({ cards = 3 }: { cards?: number }) {
  return (
    <>
      {Array.from({ length: cards }).map((_, i) => (
        <Card key={i} className="mb-3">
          <div className="flex items-baseline justify-between gap-4">
            <Skeleton className="h-4 w-32" />
            <Skeleton className="h-4 w-24" />
          </div>
          <Skeleton className="mt-3 h-2 w-full" />
          <Skeleton className="mt-3 h-3 w-40" />
          <div className="mt-4 flex gap-2">
            <Skeleton className="h-9 w-28" />
            <Skeleton className="h-9 w-24" />
          </div>
        </Card>
      ))}
    </>
  );
}

/** Grouped sections of rows: the upcoming screen and anything like it. */
export function SkeletonGroups({ groups = 2, rows = 2 }: { groups?: number; rows?: number }) {
  return (
    <div className="space-y-6">
      {Array.from({ length: groups }).map((_, g) => (
        <section key={g}>
          <div className="mb-2 flex items-center gap-2">
            <Skeleton className="h-4 w-24" />
            <Skeleton className="h-5 w-6 rounded-full" />
          </div>
          <Card>
            {Array.from({ length: rows }).map((_, i) => (
              <div key={i} className="border-b border-line/5 py-4 last:border-0">
                <div className="flex items-start justify-between gap-4">
                  <div className="min-w-0 flex-1 space-y-2">
                    <Skeleton className="h-4 w-2/5" />
                    <Skeleton className="h-3 w-4/5" />
                  </div>
                  <Skeleton className="h-4 w-24 shrink-0" />
                </div>
                {/* The action pills each row carries. */}
                <div className="mt-3 flex gap-2">
                  <Skeleton className="h-9 w-28 rounded-full" />
                  <Skeleton className="h-9 w-24 rounded-full" />
                  <Skeleton className="h-9 w-20 rounded-full" />
                </div>
              </div>
            ))}
          </Card>
        </section>
      ))}
    </div>
  );
}

/** A form: labelled fields and the button that submits them. */
export function SkeletonForm({ fields = 4 }: { fields?: number }) {
  return (
    <Card>
      <div className="space-y-4">
        {Array.from({ length: fields }).map((_, i) => (
          <div key={i} className="space-y-2">
            <Skeleton className="h-3 w-24" />
            <Skeleton className="h-11 w-full" />
          </div>
        ))}
        <Skeleton className="h-12 w-full" />
      </div>
    </Card>
  );
}

/** A record: the figure at the top, then the detail beneath it. */
export function SkeletonDetail({ rows = 5 }: { rows?: number }) {
  return (
    <>
      <Card className="mb-4">
        <Skeleton className="h-3 w-24" />
        <Skeleton className="mt-3 h-8 w-48" />
        <Skeleton className="mt-3 h-3 w-32" />
      </Card>
      <div className="mb-6 flex flex-wrap gap-2">
        <Skeleton className="h-11 w-32 rounded-full" />
        <Skeleton className="h-11 w-28 rounded-full" />
      </div>
      <SkeletonRows rows={rows} />
    </>
  );
}

/** A headline figure over a chart. */
export function SkeletonChart() {
  return (
    <Card className="mb-4">
      <div className="flex items-baseline justify-between gap-4">
        <Skeleton className="h-6 w-40" />
        <Skeleton className="h-4 w-20" />
      </div>
      <Skeleton className="mt-4 h-40 w-full" />
      <div className="mt-3 flex items-center justify-between">
        <Skeleton className="h-3 w-14" />
        <Skeleton className="h-3 w-14" />
      </div>
    </Card>
  );
}

/** Toggle rows: a label over a hint, with the switch on the right. */
export function SkeletonToggles({ rows = 2 }: { rows?: number }) {
  return (
    <>
      {Array.from({ length: rows }).map((_, i) => (
        <div
          key={i}
          className="flex items-center justify-between gap-4 border-b border-line/5 py-4 last:border-0"
        >
          <div className="min-w-0 flex-1 space-y-2">
            <Skeleton className="h-4 w-40" />
            <Skeleton className="h-3 w-56" />
          </div>
          <Skeleton className="h-6 w-11 shrink-0 rounded-full" />
        </div>
      ))}
    </>
  );
}

/** A short list of counts, as the reset warning shows. */
export function SkeletonCounts({ rows = 4 }: { rows?: number }) {
  return (
    <div className="space-y-2">
      {Array.from({ length: rows }).map((_, i) => (
        <div key={i} className="flex items-center justify-between gap-4">
          <Skeleton className="h-3 w-28" />
          <Skeleton className="h-3 w-10" />
        </div>
      ))}
    </div>
  );
}
