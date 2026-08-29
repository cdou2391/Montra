"use client";

/**
 * Base UI primitives.
 * Everything reads design tokens; no component hardcodes a hex value.
 */

import { ReactNode, useState } from "react";

import { Icon } from "@/components/icons";

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
      // 44px is the thumb-target floor from UI/UX section 3.5. The layout is
      // dense, but a full-width control never goes under it — only inline
      // chips, which are secondary by construction, sit smaller.
      className={`pressable min-h-[44px] rounded-control px-5 text-sm font-semibold disabled:cursor-not-allowed disabled:opacity-50 disabled:active:scale-100 ${styles} ${className}`}
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
  "w-full min-h-[44px] rounded-control border border-line/10 bg-background-secondary px-4 text-content-primary placeholder:text-content-muted focus:border-accent focus:outline-none";

export function Input(props: React.InputHTMLAttributes<HTMLInputElement>) {
  return <input {...props} className={`${inputClass} ${props.className ?? ""}`} />;
}

/**
 * A password field that can be read back.
 *
 * Typing a passphrase blind on a phone keyboard is how people end up locked
 * out of their own money, so the field can be revealed. It starts hidden, and
 * the toggle is a button rather than a checkbox so it never submits the form
 * it sits in.
 */
export function PasswordInput({
  className = "",
  ...props
}: React.InputHTMLAttributes<HTMLInputElement>) {
  const [shown, setShown] = useState(false);
  return (
    <div className="relative">
      <Input
        {...props}
        type={shown ? "text" : "password"}
        // Room for the button, so a long password never runs under it.
        className={`pr-12 ${className}`}
      />
      <button
        type="button"
        onClick={() => setShown((v) => !v)}
        // Disabled with the field: revealing a password while the form is
        // submitting achieves nothing and the input is already frozen.
        disabled={props.disabled}
        aria-label={shown ? "Hide password" : "Show password"}
        title={shown ? "Hide password" : "Show password"}
        className="pressable absolute inset-y-0 right-0 flex w-12 items-center justify-center text-content-secondary disabled:opacity-40"
      >
        <Icon name={shown ? "eyeOff" : "eye"} size={18} />
      </button>
    </div>
  );
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

/**
 * A labelled on/off switch.
 *
 * A button with role="switch" rather than a checkbox: the whole row is the
 * hit target, which is what a thumb needs, and the state is still announced.
 */
export function Toggle({
  label,
  hint,
  checked,
  onChange,
  disabled,
}: {
  label: string;
  hint?: string;
  checked: boolean;
  onChange: (next: boolean) => void;
  disabled?: boolean;
}) {
  return (
    <button
      // Without this it defaults to submit, and a toggle inside a form would
      // save the form every time it is flipped.
      type="button"
      role="switch"
      aria-checked={checked}
      disabled={disabled}
      onClick={() => onChange(!checked)}
      className="pressable pressable-surface flex w-full items-center justify-between gap-4 border-b border-line/5 py-4 text-left last:border-0 disabled:opacity-50"
    >
      <span className="min-w-0">
        <span className="block text-sm font-medium text-content-primary">{label}</span>
        {hint && <span className="mt-0.5 block text-xs text-content-secondary">{hint}</span>}
      </span>
      <span
        aria-hidden
        className={`relative h-6 w-11 shrink-0 rounded-full transition ${
          checked ? "bg-accent" : "bg-line/15"
        }`}
      >
        {/* The knob travels by its own width rather than a fixed pixel offset,
            so it lands correctly at any density: the track is inset by 0.5 on
            both sides and is exactly two knobs wide. */}
        <span
          className={`absolute left-0.5 top-0.5 h-5 w-5 rounded-full bg-background-primary transition-transform ${
            checked ? "translate-x-full" : "translate-x-0"
          }`}
        />
      </span>
    </button>
  );
}
