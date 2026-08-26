import type { Config } from "tailwindcss";

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
        // Typography scale, UI/UX section 11.
        value: ["2rem", { lineHeight: "2.25rem", fontWeight: "700" }],
        "value-lg": ["2.5rem", { lineHeight: "2.75rem", fontWeight: "700" }],
        title: ["1.4rem", { lineHeight: "1.85rem", fontWeight: "600" }],
        section: ["1.05rem", { lineHeight: "1.5rem", fontWeight: "600" }],
      },
      spacing: {
        safe: "env(safe-area-inset-bottom)",
      },
    },
  },
  plugins: [],
};

export default config;
