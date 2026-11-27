const PATHS = {
  search: ["M21 21l-4.3-4.3"],
  arrow: ["M5 12h14", "M13 6l6 6-6 6"],
  down: ["M6 9l6 6 6-6"],
  left: ["M15 18l-6-6 6-6"],
  right: ["M9 18l6-6-6-6"],
  close: ["M6 6l12 12", "M18 6L6 18"],
  check: ["M5 12.5l4.5 4.5L19 7.5"],
  up: ["M12 19V5", "M6 11l6-6 6 6"],
} as const;

interface Props {
  name: keyof typeof PATHS;
  size?: number;
  stroke?: number;
  className?: string;
}

/** The app's few line icons, drawn alike. Always decorative: the control
 *  that holds one carries the words. */
export function Icon({ name, size = 16, stroke = 2.2, className }: Props) {
  return (
    <svg
      className={className} aria-hidden="true" width={size} height={size} viewBox="0 0 24 24" fill="none"
      stroke="currentColor" strokeWidth={stroke} strokeLinecap="round" strokeLinejoin="round"
    >
      {name === "search" && <circle cx="11" cy="11" r="7" />}
      {PATHS[name].map((d) => <path key={d} d={d} />)}
    </svg>
  );
}
