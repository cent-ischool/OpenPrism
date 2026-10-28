interface LogoMarkProps {
  size?: number;
}

/** The Open Prism mark: an outlined prism with the refracted half in the accent colour. */
export function LogoMark({ size = 22 }: LogoMarkProps) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" aria-hidden="true">
      <path d="M12 3 21.5 19.5h-19z" fill="none" stroke="currentColor" strokeWidth="1.75" strokeLinejoin="round" />
      <path d="M12 3 16.75 11.25 12 19.5z" fill="var(--accent)" />
    </svg>
  );
}

interface LogoProps {
  size?: number;
  showName?: boolean;
}

export function Logo({ size = 22, showName = true }: LogoProps) {
  return (
    <span className="op-logo">
      <LogoMark size={size} />
      {showName && <span>Open Prism</span>}
    </span>
  );
}
