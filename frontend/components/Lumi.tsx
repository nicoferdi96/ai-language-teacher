export type LumiState =
  | "idle"
  | "happy"
  | "speaking"
  | "listening"
  | "thinking"
  | "connecting"
  | "initializing";

type LumiProps = {
  state?: LumiState | string;
  size?: "sm" | "md" | "lg" | "xl";
  className?: string;
};

/**
 * Lumi, the tutor: a speech-bubble character drawn in SVG. Its face follows
 * the voice-assistant state (talks, listens, thinks, beams) and it blinks and
 * breathes when idle. Decorative, so hidden from assistive tech.
 */
export function Lumi({ state = "idle", size = "md", className }: LumiProps) {
  return (
    <span className={`lumi lumi--${size} ${className ?? ""}`} data-state={state} aria-hidden="true">
      <span className="lumi__ring" />
      <svg viewBox="0 0 120 124" className="lumi__svg">
        <defs>
          <radialGradient id="lumi-body" cx="34%" cy="26%" r="80%">
            <stop offset="0" stopColor="oklch(0.8 0.11 196)" />
            <stop offset="0.55" stopColor="oklch(0.62 0.135 207)" />
            <stop offset="1" stopColor="oklch(0.49 0.12 216)" />
          </radialGradient>
        </defs>
        <ellipse className="lumi__shadow" cx="60" cy="117" rx="30" ry="5" />
        <g className="lumi__body">
          <path
            d="M60 10C89 10 107 28 107 56C107 84 89 101 60 101H34C25 101 18 106 12 112C14 103 14 96 14 88V56C14 28 32 10 60 10Z"
            fill="url(#lumi-body)"
          />
          <path
            d="M60 10C89 10 107 28 107 56C107 84 89 101 60 101H34C25 101 18 106 12 112C14 103 14 96 14 88V56C14 28 32 10 60 10Z"
            fill="none"
            stroke="oklch(0.38 0.09 220 / 0.35)"
            strokeWidth="2"
          />
          <ellipse cx="38" cy="26" rx="11" ry="6" fill="white" opacity="0.28" transform="rotate(-28 38 26)" />
          <g className="lumi__cheeks" fill="oklch(0.78 0.14 15)" opacity="0.7">
            <ellipse cx="30" cy="70" rx="6.5" ry="4.5" />
            <ellipse cx="90" cy="70" rx="6.5" ry="4.5" />
          </g>
          <g className="lumi__eyes">
            <g className="lumi__eye-open">
              <ellipse cx="44" cy="52" rx="10.5" ry="12.5" fill="white" />
              <ellipse cx="76" cy="52" rx="10.5" ry="12.5" fill="white" />
              <g className="lumi__pupils" fill="oklch(0.24 0.03 250)">
                <circle cx="46" cy="55" r="6.5" />
                <circle cx="78" cy="55" r="6.5" />
              </g>
              <g fill="white">
                <circle cx="48.5" cy="51.5" r="2.2" />
                <circle cx="80.5" cy="51.5" r="2.2" />
              </g>
            </g>
            <g
              className="lumi__eye-happy"
              fill="none"
              stroke="oklch(0.24 0.03 250)"
              strokeWidth="5"
              strokeLinecap="round"
            >
              <path d="M35 56Q44 44 53 56" />
              <path d="M67 56Q76 44 85 56" />
            </g>
          </g>
          <path
            className="lumi__smile"
            d="M51 74Q60 82 69 74"
            fill="none"
            stroke="oklch(0.24 0.03 250)"
            strokeWidth="4"
            strokeLinecap="round"
          />
          <g className="lumi__mouth">
            <ellipse cx="60" cy="76" rx="7.5" ry="6" fill="oklch(0.28 0.06 20)" />
            <ellipse cx="60" cy="79.5" rx="4.5" ry="2.4" fill="oklch(0.7 0.14 20)" />
          </g>
        </g>
      </svg>
    </span>
  );
}
