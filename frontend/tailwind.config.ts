import type { Config } from "tailwindcss";

/**
 * Density.
 *
 * The layout is deliberately compact: spacing and type are scaled at the token
 * level rather than per component, so `p-4` and `gap-3` mean the same thing
 * everywhere and one number moves the whole app. Raise TIGHTEN towards 1 for a
 * roomier layout.
 *
 * Touch targets are written as arbitrary pixel values (`min-h-[44px]`) and so
 * are deliberately *not* on this scale — density must never shrink a thumb
 * target below the 44px floor.
 */
const TIGHTEN = 0.875;

const STEPS = [
  0.5, 1, 1.5, 2, 2.5, 3, 3.5, 4, 5, 6, 7, 8, 9, 10, 11, 12, 14, 16, 20, 24,
  28, 32, 36, 40, 44, 48, 52, 56, 60, 64, 72, 80, 96,
];

const spacing: Record<string, string> = {
  0: "0px",
  px: "1px",
  // Not a length we control; the notch is whatever the device says it is.
  safe: "env(safe-area-inset-bottom)",
};
for (const step of STEPS) {
  spacing[String(step)] = `${+(step * 0.25 * TIGHTEN).toFixed(5)}rem`;
}

/**
 * Design tokens from the UI/UX Specification (sections 6-14, 96).
 * Components reference tokens, never raw hex.
 */
const config: Config = {
  // Hover styles only where a real pointer exists, so a tap never leaves one
  // stuck on a touch device.
  future: { hoverOnlyWhenSupported: true },
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}"],
  theme: {
    spacing,
    extend: {
      // Every colour resolves through a CSS variable defined in globals.css,
      // so the light theme is a different set of values rather than a
      // different set of class names. <alpha-value> keeps the opacity
      // modifiers working: bg-surface-primary/60 still means what it says.
      colors: {
        background: {
          primary: "rgb(var(--background-primary) / <alpha-value>)",
          secondary: "rgb(var(--background-secondary) / <alpha-value>)",
        },
        surface: {
          primary: "rgb(var(--surface-primary) / <alpha-value>)",
          elevated: "rgb(var(--surface-elevated) / <alpha-value>)",
        },
        content: {
          primary: "rgb(var(--content-primary) / <alpha-value>)",
          secondary: "rgb(var(--content-secondary) / <alpha-value>)",
          muted: "rgb(var(--content-muted) / <alpha-value>)",
        },
        accent: {
          DEFAULT: "rgb(var(--accent) / <alpha-value>)",
          muted: "rgb(var(--accent) / 0.12)",
        },
        semantic: {
          income: "rgb(var(--semantic-income) / <alpha-value>)",
          expense: "rgb(var(--semantic-expense) / <alpha-value>)",
          warning: "rgb(var(--semantic-warning) / <alpha-value>)",
          transfer: "rgb(var(--semantic-transfer) / <alpha-value>)",
          neutral: "rgb(var(--semantic-neutral) / <alpha-value>)",
        },
        // Hairlines and subtle fills. Replaces the literal white/N utilities,
        // which are invisible on a light ground.
        line: "rgb(var(--line) / <alpha-value>)",
      },
      borderRadius: {
        card: "18px",
        control: "12px",
      },
      fontFamily: {
        sans: ["Inter", "system-ui", "-apple-system", "Segoe UI", "sans-serif"],
      },
      fontSize: {
        // Typography scale, UI/UX section 11, taken down a step for density.
        // Line height is trimmed harder than the size: leading is where the
        // airiness lives, and it costs less legibility than the glyphs do.
        value: ["1.75rem", { lineHeight: "2rem", fontWeight: "700" }],
        "value-lg": ["2.125rem", { lineHeight: "2.375rem", fontWeight: "700" }],
        title: ["1.25rem", { lineHeight: "1.6rem", fontWeight: "600" }],
        section: ["1rem", { lineHeight: "1.375rem", fontWeight: "600" }],

        // The stock steps, re-cut on the same basis. xs stops at 11px: it
        // carries hints and captions, and below that they stop being readable
        // on a phone rather than merely small.
        xs: ["0.6875rem", { lineHeight: "0.9375rem" }],
        sm: ["0.8125rem", { lineHeight: "1.125rem" }],
        base: ["0.9375rem", { lineHeight: "1.375rem" }],
        lg: ["1.0625rem", { lineHeight: "1.5rem" }],
        xl: ["1.1875rem", { lineHeight: "1.625rem" }],
        "2xl": ["1.375rem", { lineHeight: "1.8125rem" }],
        "3xl": ["1.6875rem", { lineHeight: "2.0625rem" }],
      },
    },
  },
  plugins: [],
};

export default config;
