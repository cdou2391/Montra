"use client";

/**
 * Icon set — Lucide-style stroke geometry on a 24px grid (UI/UX section 16).
 *
 * One family, drawn the same way, so headers and navigation never mix styles.
 * Every icon inherits currentColor and is marked aria-hidden: they label
 * nothing on their own, the adjacent text does.
 */

export type IconName =
  | "alertTriangle"
  | "home"
  | "wallet"
  | "calendar"
  | "repeat"
  | "list"
  | "bell"
  | "user"
  | "plus"
  | "more"
  | "creditCard"
  | "scale"
  | "transfer"
  | "chevronLeft"
  | "chevronRight"
  | "logOut"
  | "handshake"
  | "download"
  | "upload"
  | "star"
  | "starFilled"
  | "landmark"
  | "piggyBank"
  | "banknote"
  | "smartphone"
  | "walletCards"
  | "trendingUp"
  | "shapes"
  | "users";

const PATHS: Record<IconName, string[]> = {
  home: [
    "M15 21v-8a1 1 0 0 0-1-1h-4a1 1 0 0 0-1 1v8",
    "M3 10a2 2 0 0 1 .709-1.528l7-5.999a2 2 0 0 1 2.582 0l7 5.999A2 2 0 0 1 21 10v9a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z",
  ],
  wallet: [
    "M19 7V4a1 1 0 0 0-1-1H5a2 2 0 0 0 0 4h15a1 1 0 0 1 1 1v4h-3a2 2 0 0 0 0 4h3a1 1 0 0 1-1 1v2a1 1 0 0 1-1 1H5a2 2 0 0 1-2-2V5",
  ],
  calendar: ["M8 2v4", "M16 2v4", "M3 10h18", "M5 4h14a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2z"],
  repeat: [
    "m17 2 4 4-4 4",
    "M3 11v-1a4 4 0 0 1 4-4h14",
    "m7 22-4-4 4-4",
    "M21 13v1a4 4 0 0 1-4 4H3",
  ],
  list: ["M3 6h.01", "M3 12h.01", "M3 18h.01", "M8 6h13", "M8 12h13", "M8 18h13"],
  bell: [
    "M10.268 21a2 2 0 0 0 3.464 0",
    "M3.262 15.326A1 1 0 0 0 4 17h16a1 1 0 0 0 .74-1.673C19.41 13.956 18 12.499 18 8A6 6 0 0 0 6 8c0 4.499-1.411 5.956-2.738 7.326",
  ],
  user: ["M19 21v-2a4 4 0 0 0-4-4H9a4 4 0 0 0-4 4v2", "M12 3a4 4 0 1 1 0 8 4 4 0 0 1 0-8z"],
  plus: ["M5 12h14", "M12 5v14"],
  more: ["M5 12h.01", "M12 12h.01", "M19 12h.01"],
  creditCard: ["M4 5h16a2 2 0 0 1 2 2v10a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V7a2 2 0 0 1 2-2z", "M2 10h20"],
  scale: [
    "M12 3v18",
    "M3 7h2c2 0 5-1 7-2 2 1 5 2 7 2h2",
    "M7 21h10",
    "m2 16 3-8 3 8c-.87.65-1.92 1-3 1s-2.13-.35-3-1Z",
    "m16 16 3-8 3 8c-.87.65-1.92 1-3 1s-2.13-.35-3-1Z",
  ],
  transfer: ["M8 3 4 7l4 4", "M4 7h16", "m16 21 4-4-4-4", "M20 17H4"],
  chevronLeft: ["m15 18-6-6 6-6"],
  chevronRight: ["m9 18 6-6-6-6"],
  // Lucide "handshake": lending and being repaid.
  handshake: [
    "m11 17 2 2a1 1 0 1 0 3-3",
    "m14 14 2.5 2.5a1 1 0 1 0 3-3l-3.88-3.88a3 3 0 0 0-4.24 0l-.88.88a1 1 0 1 1-3-3l2.81-2.81a5.79 5.79 0 0 1 7.06-.87l.47.28a2 2 0 0 0 1.42.25L21 4",
    "m21 3 1 11h-2",
    "M3 3 2 14l6.5 6.5a1 1 0 1 0 3-3",
    "M3 4h8",
  ],
  // --- account types ---------------------------------------------------
  landmark: [
    "M3 22h18",
    "M6 18v-7",
    "M10 18v-7",
    "M14 18v-7",
    "M18 18v-7",
    "M11.1 2.2a2 2 0 0 1 1.8 0l8 4a.5.5 0 0 1-.2 1H3.3a.5.5 0 0 1-.2-1z",
  ],
  piggyBank: [
    "M19 10a5 5 0 0 0-2-3.5V4a4 4 0 0 0-3.2 1.6l-.3.4H11a6 6 0 0 0-6 6v1a5 5 0 0 0 2 4v3a1 1 0 0 0 1 1h2a1 1 0 0 0 1-1v-2h3v2a1 1 0 0 0 1 1h2a1 1 0 0 0 1-1v-3a3.2 3.2 0 0 0 2-2h1a1 1 0 0 0 1-1v-2a1 1 0 0 0-1-1z",
    "M16 10h.01",
    "M2 8v1a2 2 0 0 0 2 2h1",
  ],
  banknote: [
    "M4 6h16a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2z",
    "M12 10a2 2 0 1 1 0 4 2 2 0 0 1 0-4z",
    "M6 12h.01",
    "M18 12h.01",
  ],
  smartphone: [
    "M7 2h10a2 2 0 0 1 2 2v16a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2z",
    "M12 18h.01",
  ],
  // A card in front of another: stored value rather than borrowed.
  walletCards: [
    "M4 7h12a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V9a2 2 0 0 1 2-2z",
    "M2 12h16",
    "M8 7V5a2 2 0 0 1 2-2h10a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2h-2",
  ],
  trendingUp: ["M16 7h6v6", "m22 7-8.5 8.5-5-5L2 17"],
  alertTriangle: [
    "M10.3 3.9 1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0z",
    "M12 9v4",
    "M12 17h.01",
  ],
  shapes: [
    "M8.3 10a.7.7 0 0 1-.6-1l4-6.5a.7.7 0 0 1 1.2 0l4 6.5a.7.7 0 0 1-.6 1z",
    "M17.5 14a4.5 4.5 0 1 1 0 9 4.5 4.5 0 0 1 0-9z",
    "M3 15h7v7H3z",
  ],
  users: [
    "M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2",
    "M9 3a4 4 0 1 1 0 8 4 4 0 0 1 0-8z",
    "M22 21v-2a4 4 0 0 0-3-3.87",
    "M16 3.13a4 4 0 0 1 0 7.75",
  ],
  star: ["M11.5 3.1a.6.6 0 0 1 1 0l2.3 4.7 5.2.7a.6.6 0 0 1 .3 1l-3.8 3.6.9 5.2a.6.6 0 0 1-.9.6L12 16.4l-4.6 2.5a.6.6 0 0 1-.9-.6l.9-5.2-3.8-3.6a.6.6 0 0 1 .3-1l5.2-.7z"],
  // Same outline; the fill comes from the caller so one shape serves both states.
  starFilled: ["M11.5 3.1a.6.6 0 0 1 1 0l2.3 4.7 5.2.7a.6.6 0 0 1 .3 1l-3.8 3.6.9 5.2a.6.6 0 0 1-.9.6L12 16.4l-4.6 2.5a.6.6 0 0 1-.9-.6l.9-5.2-3.8-3.6a.6.6 0 0 1 .3-1l5.2-.7z"],
  download: ["M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4", "M7 10l5 5 5-5", "M12 15V3"],
  upload: ["M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4", "M17 8l-5-5-5 5", "M12 3v12"],
  logOut: ["m16 17 5-5-5-5", "M21 12H9", "M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"],
};

export function Icon({
  name,
  size = 22,
  className = "",
  strokeWidth = 1.8,
  filled = false,
}: {
  name: IconName;
  size?: number;
  className?: string;
  strokeWidth?: number;
  /** Fill the shape with currentColor, for on/off states like a star. */
  filled?: boolean;
}) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill={filled ? "currentColor" : "none"}
      stroke="currentColor"
      strokeWidth={strokeWidth}
      strokeLinecap="round"
      strokeLinejoin="round"
      className={className}
      aria-hidden="true"
    >
      {PATHS[name].map((d) => (
        <path key={d} d={d} />
      ))}
    </svg>
  );
}


/**
 * Account type to icon (Data Model section 13).
 *
 * Every type gets a distinct shape, so a glance at a card says what kind of
 * money it holds without reading the label underneath.
 */
export const ACCOUNT_TYPE_ICONS: Record<string, IconName> = {
  CHECKING: "landmark",
  SAVINGS: "piggyBank",
  CASH: "banknote",
  MOBILE_MONEY: "smartphone",
  CREDIT_CARD: "creditCard",
  PREPAID_CARD: "walletCards",
  INVESTMENT: "trendingUp",
  OTHER: "shapes",
};

export function accountTypeIcon(accountType: string): IconName {
  return ACCOUNT_TYPE_ICONS[accountType] ?? "wallet";
}
