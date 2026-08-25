/**
 * The Montra mark.
 *
 * The same drawing as the favicon and the installed app icon, so the thing in
 * the browser tab, the thing on the home screen and the thing beside the name
 * are recognisably one product.
 *
 * Inline rather than an <img>: it inherits nothing and needs no request, and
 * at 24px a separate round trip to draw a square would be silly.
 */
export function Logo({ size = 32, className = "" }: { size?: number; className?: string }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 64 64"
      role="img"
      aria-label="Montra"
      className={className}
    >
      <rect width="64" height="64" rx="14" fill="#2DD4BF" />
      <path
        d="M19 45V21l13 14 13-14v24"
        fill="none"
        stroke="#08111C"
        strokeWidth="8"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}
