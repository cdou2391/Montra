"use client";

/**
 * Profile avatar.
 *
 * No image upload exists yet, so this derives initials from the display name,
 * falling back to the email local part.
 */

import Link from "next/link";

import { CurrentUser } from "@/lib/api";

export function initialsFor(user: Pick<CurrentUser, "display_name" | "email">): string {
  const source = user.display_name?.trim() || user.email.split("@")[0] || "";
  const words = source.split(/[\s._-]+/).filter(Boolean);
  if (words.length === 0) return "?";
  if (words.length === 1) return words[0].slice(0, 2).toUpperCase();
  return (words[0][0] + words[words.length - 1][0]).toUpperCase();
}

export function Avatar({
  user,
  size = "md",
}: {
  user: Pick<CurrentUser, "display_name" | "email">;
  size?: "md" | "lg";
}) {
  const dimensions = size === "lg" ? "h-16 w-16 text-xl" : "h-10 w-10 text-sm";
  return (
    <span
      aria-hidden
      className={`flex shrink-0 items-center justify-center rounded-full bg-accent-muted font-semibold text-accent ${dimensions}`}
    >
      {initialsFor(user)}
    </span>
  );
}

/** Avatar as a link to the profile, for use in a page header. */
export function ProfileAvatarLink({
  user,
}: {
  user: Pick<CurrentUser, "display_name" | "email">;
}) {
  return (
    <Link
      href="/profile"
      aria-label="Your profile"
      className="flex h-11 w-11 shrink-0 items-center justify-center rounded-full transition hover:bg-white/5 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/60"
    >
      <Avatar user={user} />
    </Link>
  );
}
