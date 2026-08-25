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
  return (
    <html lang="en">
      <head>
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
