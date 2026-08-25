"use client";

/**
 * Transaction filters (Implementation Plan Phase 26).
 *
 * One set of controls, two surfaces: stacked inside a bottom sheet on a phone,
 * laid out in a row on a wide screen. The state lives with the caller so both
 * surfaces edit the same thing and neither has a copy to fall out of step.
 */

import { Account, Category, FamilyMember } from "@/lib/api";
import { BottomSheet } from "@/components/sheet";
import { Button, Field, Input, Select } from "@/components/ui";

export type Filters = {
  account_id: string;
  category_id: string;
  owner_id: string;
  type: string;
  date_from: string;
  date_to: string;
  min_amount: string;
  max_amount: string;
};

export const EMPTY_FILTERS: Filters = {
  account_id: "",
  category_id: "",
  owner_id: "",
  type: "",
  date_from: "",
  date_to: "",
  min_amount: "",
  max_amount: "",
};

/** How many are narrowing the view — for the badge on the Filters button. */
export function activeCount(filters: Filters): number {
  return Object.values(filters).filter(Boolean).length;
}

type ControlProps = {
  filters: Filters;
  onChange: (next: Filters) => void;
  accounts: Account[];
  categories: Category[];
  members: FamilyMember[];
  layout?: "inline" | "stacked";
};

export function FilterControls({
  filters,
  onChange,
  accounts,
  categories,
  members,
  layout = "stacked",
}: ControlProps) {
  const set = (key: keyof Filters, value: string) => onChange({ ...filters, [key]: value });
  const inline = layout === "inline";

  return (
    <div className={inline ? "grid grid-cols-2 gap-3 xl:grid-cols-4" : "space-y-4"}>
      <Field label="Account">
        <Select value={filters.account_id} onChange={(e) => set("account_id", e.target.value)}>
          <option value="">All accounts</option>
          {accounts.map((a) => (
            <option key={a.id} value={a.id}>
              {a.name}
            </option>
          ))}
        </Select>
      </Field>

      <Field label="Category">
        <Select value={filters.category_id} onChange={(e) => set("category_id", e.target.value)}>
          <option value="">All categories</option>
          {categories.map((c) => (
            <option key={c.id} value={c.id}>
              {c.name}
            </option>
          ))}
        </Select>
      </Field>

      <Field label="Type">
        <Select value={filters.type} onChange={(e) => set("type", e.target.value)}>
          <option value="">All types</option>
          <option value="INCOME">Income</option>
          <option value="EXPENSE">Expense</option>
          <option value="TRANSFER">Transfer</option>
          <option value="ADJUSTMENT">Adjustment</option>
        </Select>
      </Field>

      {/* Only a household has more than one person's spending in view. */}
      {members.length > 0 && (
        <Field label="Person">
          <Select value={filters.owner_id} onChange={(e) => set("owner_id", e.target.value)}>
            <option value="">Everyone</option>
            {members.map((m) => (
              <option key={m.user_id} value={m.user_id}>
                {m.display_name ?? m.email}
              </option>
            ))}
          </Select>
        </Field>
      )}

      <Field label="From">
        <Input
          type="date"
          value={filters.date_from}
          onChange={(e) => set("date_from", e.target.value)}
        />
      </Field>
      <Field label="To">
        <Input
          type="date"
          value={filters.date_to}
          onChange={(e) => set("date_to", e.target.value)}
        />
      </Field>

      <Field label="Least">
        <Input
          type="number"
          inputMode="decimal"
          min={0}
          placeholder="0"
          value={filters.min_amount}
          onChange={(e) => set("min_amount", e.target.value)}
        />
      </Field>
      <Field label="Most">
        <Input
          type="number"
          inputMode="decimal"
          min={0}
          placeholder="Any"
          value={filters.max_amount}
          onChange={(e) => set("max_amount", e.target.value)}
        />
      </Field>
    </div>
  );
}

export function FilterSheet({
  open,
  onClose,
  ...controls
}: ControlProps & { open: boolean; onClose: () => void }) {
  return (
    <BottomSheet open={open} onClose={onClose} title="Filters">
      <FilterControls {...controls} />
      <div className="mt-5 flex gap-3">
        <Button className="flex-1" onClick={onClose}>
          Show results
        </Button>
        <Button
          variant="secondary"
          onClick={() => {
            controls.onChange(EMPTY_FILTERS);
            onClose();
          }}
        >
          Clear
        </Button>
      </div>
    </BottomSheet>
  );
}
