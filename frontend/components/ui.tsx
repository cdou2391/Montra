"use client";

/**
 * Base UI primitives (Implementation Plan Phase 1).
 * Everything reads design tokens; no component hardcodes a hex value.
 */

import { ReactNode } from "react";

export function Card({
  children,
  className = "",
}: {
  children: ReactNode;
  className?: string;
}) {
  return (
    <div
      className={`rounded-card border border-line/5 bg-surface-primary p-4 sm:p-5 ${className}`}
    >
      {children}
    </div>
  );
}

export function Button({
  children,
  variant = "primary",
  type = "button",
  disabled,
  onClick,
  className = "",
}: {
  children: ReactNode;
  variant?: "primary" | "secondary" | "destructive";
  type?: "button" | "submit";
  disabled?: boolean;
  onClick?: () => void;
  className?: string;
}) {
  const styles = {
    primary: "bg-accent text-background-primary hover:brightness-110",
    secondary:
      "bg-transparent text-content-primary border border-line/15 hover:bg-line/5",
    destructive: "bg-semantic-expense/15 text-semantic-expense hover:bg-semantic-expense/25",
  }[variant];

  return (
    <button
      type={type}
      disabled={disabled}
      onClick={onClick}
      // 48px min height keeps every control inside the thumb-friendly target
      // size from UI/UX section 3.5.
      className={`pressable min-h-[48px] rounded-control px-5 text-sm font-semibold disabled:cursor-not-allowed disabled:opacity-50 disabled:active:scale-100 ${styles} ${className}`}
    >
      {children}
    </button>
  );
}

export function Field({
  label,
  children,
  hint,
  error,
}: {
  label: string;
  children: ReactNode;
  hint?: string;
  error?: string;
}) {
  return (
    <label className="block space-y-2">
      <span className="text-sm font-medium text-content-secondary">{label}</span>
      {children}
      {hint && !error && <span className="block text-xs text-content-muted">{hint}</span>}
      {error && <span className="block text-xs text-semantic-expense">{error}</span>}
    </label>
  );
}

const inputClass =
  "w-full min-h-[48px] rounded-control border border-line/10 bg-background-secondary px-4 text-content-primary placeholder:text-content-muted focus:border-accent focus:outline-none";

export function Input(props: React.InputHTMLAttributes<HTMLInputElement>) {
  return <input {...props} className={`${inputClass} ${props.className ?? ""}`} />;
}

export function Select(props: React.SelectHTMLAttributes<HTMLSelectElement>) {
  return <select {...props} className={`${inputClass} ${props.className ?? ""}`} />;
}

/** Numeric keypad on mobile, tabular figures, never a spinner. */
export function AmountInput(props: React.InputHTMLAttributes<HTMLInputElement>) {
  return (
    <input
      {...props}
      inputMode="decimal"
      autoComplete="off"
      className={`${inputClass} tabular text-xl font-semibold ${props.className ?? ""}`}
    />
  );
}

export function StatusChip({
  children,
  tone = "neutral",
}: {
  children: ReactNode;
  tone?: "neutral" | "income" | "expense" | "warning" | "transfer";
}) {
  const tones = {
    neutral: "bg-line/5 text-content-secondary",
    income: "bg-semantic-income/15 text-semantic-income",
    expense: "bg-semantic-expense/15 text-semantic-expense",
    warning: "bg-semantic-warning/15 text-semantic-warning",
    transfer: "bg-semantic-transfer/15 text-semantic-transfer",
  }[tone];
  return (
    <span className={`rounded-full px-2.5 py-1 text-xs font-medium ${tones}`}>{children}</span>
  );
}

export function EmptyState({
  title,
  message,
  action,
}: {
  title: string;
  message: string;
  action?: ReactNode;
}) {
  return (
    <Card className="text-center">
      <p className="text-section text-content-primary">{title}</p>
      <p className="mt-2 text-sm text-content-secondary">{message}</p>
      {action && <div className="mt-5 flex justify-center">{action}</div>}
    </Card>
  );
}

export function Skeleton({ className = "" }: { className?: string }) {
  return <div className={`animate-pulse rounded-control bg-line/5 ${className}`} />;
}

export function ErrorNotice({ message }: { message: string }) {
  return (
    <div className="rounded-control border border-semantic-expense/30 bg-semantic-expense/10 px-4 py-3 text-sm text-semantic-expense">
      {message}
    </div>
  );
}
