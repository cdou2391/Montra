import type { MetadataRoute } from "next";

/**
 * What makes the app installable.
 *
 * There was no manifest before this, so the app could not be added to a home
 * screen at all — the icon had nowhere to live.
 *
 * Two icon purposes, deliberately: `any` is the icon as drawn, and `maskable`
 * is a full-bleed version whose mark sits inside the middle 80%, because
 * Android crops to its own shape and would otherwise clip the corners off a
 * rounded tile.
 */
export default function manifest(): MetadataRoute.Manifest {
  return {
    name: "Montra",
    short_name: "Montra",
    description: "Personal and household finance tracking.",
    start_url: "/",
    display: "standalone",
    // Matches the app's own background, so the splash and the status bar do
    // not flash a colour the app never uses.
    background_color: "#08111C",
    theme_color: "#08111C",
    orientation: "portrait",
    icons: [
      { src: "/icon-192.png", sizes: "192x192", type: "image/png", purpose: "any" },
      { src: "/icon-512.png", sizes: "512x512", type: "image/png", purpose: "any" },
      {
        src: "/icon-maskable-512.png",
        sizes: "512x512",
        type: "image/png",
        purpose: "maskable",
      },
    ],
  };
}
