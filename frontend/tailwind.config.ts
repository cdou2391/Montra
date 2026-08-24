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
      colors: {
        background: {
          primary: "#08111C",
          secondary: "#0C1522",
        },
        surface: {
          primary: "#141E2B",
          elevated: "#192431",
        },
        content: {
          primary: "#F8FAFC",
          secondary: "#94A3B8",
          muted: "#64748B",
        },
        accent: {
          DEFAULT: "#2DD4BF",
          muted: "rgba(45, 212, 191, 0.12)",
        },
        semantic: {
          income: "#22C55E",
          expense: "#F87171",
          warning: "#F59E0B",
          transfer: "#60A5FA",
          neutral: "#94A3B8",
        },
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
