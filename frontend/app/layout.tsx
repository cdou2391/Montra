import type { Metadata, Viewport } from "next";

import "@/styles/globals.css";

export const metadata: Metadata = {
  title: "Montra",
  description: "Personal and household finance tracking.",
  // Next serves app/icon.svg and app/apple-icon.png automatically; naming the
  // manifest here is what makes the app installable.
  manifest: "/manifest.webmanifest",
  appleWebApp: { capable: true, title: "Montra", statusBarStyle: "black-translucent" },
};

export const viewport: Viewport = {
  themeColor: "#08111C",
  width: "device-width",
  initialScale: 1,
  viewportFit: "cover",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  // suppressHydrationWarning on <html>: the theme script below stamps
  // data-theme and colorScheme on this element before React hydrates, so the
  // server markup and the client deliberately differ here. Without it React
  // reports a mismatch for an attribute it is meant to find already set.
  return (
    <html lang="en" suppressHydrationWarning>
      <head>
        {/*
          Runs before the first paint so the page is never drawn in one theme
          and repainted in the other. Reads the same key the provider writes,
          and falls back to the device. Inline because a fetched script would
          already be too late.
        */}
        <script
          dangerouslySetInnerHTML={{
            __html: `(function(){try{var t=localStorage.getItem('montra.theme')||'SYSTEM';var d=t==='DARK'||(t==='SYSTEM'&&window.matchMedia('(prefers-color-scheme: dark)').matches);document.documentElement.setAttribute('data-theme',d?'dark':'light');document.documentElement.style.colorScheme=d?'dark':'light';}catch(e){document.documentElement.setAttribute('data-theme','dark');}})();`,
          }}
        />
        <link rel="preconnect" href="https://fonts.googleapis.com" />
        <link rel="preconnect" href="https://fonts.gstatic.com" crossOrigin="" />
        <link
          href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap"
          rel="stylesheet"
        />
      </head>
      <body>{children}</body>
    </html>
  );
}
