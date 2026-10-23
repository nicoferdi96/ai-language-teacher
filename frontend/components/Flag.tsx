import type { TargetLanguage } from "@/lib/languages";

/** Rounded flag for each target language, drawn in SVG so it renders the same everywhere. */
export function Flag({ code, className }: { code: TargetLanguage["code"]; className?: string }) {
  return (
    <svg viewBox="0 0 36 26" className={`flag ${className ?? ""}`} aria-hidden="true">
      {code === "es" ? (
        <>
          <rect width="36" height="26" fill="#C60B1E" />
          <rect y="6.5" width="36" height="13" fill="#FFC400" />
        </>
      ) : code === "fr" ? (
        <>
          <rect width="36" height="26" fill="#F4F4F4" />
          <rect width="12" height="26" fill="#1F5CC4" />
          <rect x="24" width="12" height="26" fill="#E8333B" />
        </>
      ) : code === "de" ? (
        <>
          <rect width="36" height="26" fill="#262626" />
          <rect y="8.67" width="36" height="8.67" fill="#DD1F1F" />
          <rect y="17.33" width="36" height="8.67" fill="#FFCE00" />
        </>
      ) : (
        <>
          <rect width="36" height="26" fill="#1D3B8B" />
          <path d="M0 0L36 26M36 0L0 26" stroke="#fff" strokeWidth="5.5" />
          <path d="M0 0L36 26M36 0L0 26" stroke="#D52B3A" strokeWidth="1.8" />
          <path d="M18 0V26M0 13H36" stroke="#fff" strokeWidth="8.5" />
          <path d="M18 0V26M0 13H36" stroke="#D52B3A" strokeWidth="5" />
        </>
      )}
      <rect y="21" width="36" height="5" fill="black" opacity="0.08" />
    </svg>
  );
}
