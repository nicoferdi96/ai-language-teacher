"use client";

import { useEffect, useState } from "react";
import { Flag } from "@/components/Flag";
import { Lumi } from "@/components/Lumi";
import { TARGET_LANGUAGES } from "@/lib/languages";

const CYCLE_MS = 2400;

/**
 * Landing hero art: Lumi greets the visitor in each language it teaches, with
 * the matching flag lifting as the bubble changes. Pauses while the tab is hidden.
 */
export function Greetings() {
  const [index, setIndex] = useState(0);

  useEffect(() => {
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
    const timer = setInterval(() => {
      if (!document.hidden) setIndex((value) => (value + 1) % TARGET_LANGUAGES.length);
    }, CYCLE_MS);
    return () => clearInterval(timer);
  }, []);

  const language = TARGET_LANGUAGES[index];
  return (
    <div className="greet" aria-hidden="true">
      <p key={language.code} className="greet__bubble" lang={language.code}>
        {language.hello}
      </p>
      <Lumi state="happy" size="xl" />
      <ul className="greet__flags">
        {TARGET_LANGUAGES.map((option, position) => (
          <li key={option.code} data-active={position === index}>
            <Flag code={option.code} />
          </li>
        ))}
      </ul>
    </div>
  );
}
