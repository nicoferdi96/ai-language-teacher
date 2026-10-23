"use client";

import { useActionState, useState } from "react";
import { Flag } from "@/components/Flag";
import { FormError } from "@/components/FormError";
import { saveTargetLanguage } from "@/lib/actions";
import { findTargetLanguage, TARGET_LANGUAGES } from "@/lib/languages";

/** Single-choice picker for the one language the learner will study. */
export function LanguageForm({ current }: { current: string | null }) {
  const [error, formAction, pending] = useActionState(saveTargetLanguage, null);
  const [picked, setPicked] = useState(current);
  const language = findTargetLanguage(picked);
  return (
    <form action={formAction} className="form form--docked">
      <fieldset className="choices choices--lang" aria-describedby={error ? "language-error" : undefined}>
        <legend className="sr-only">Language to learn</legend>
        {TARGET_LANGUAGES.map((option) => (
          <label key={option.code} className="choice choice--lang">
            <input
              type="radio"
              name="language"
              value={option.code}
              defaultChecked={option.code === current}
              onChange={() => setPicked(option.code)}
              required
            />
            <Flag code={option.code} className="choice__flag" />
            <span className="choice__name">{option.name}</span>
            <span className="choice__sub" lang={option.code}>
              {option.nativeName}
            </span>
          </label>
        ))}
      </fieldset>
      <FormError id="language-error" message={error} />
      <div className="dock">
        <p className="dock__note" aria-live="polite">
          {language ? (
            <span key={language.code} className="dock__hello">
              <span lang={language.code}>{language.hello}</span> Great pick.
            </span>
          ) : null}
        </p>
        <button type="submit" className="btn" disabled={pending || !language}>
          {pending ? "Saving…" : "Continue"}
        </button>
      </div>
    </form>
  );
}
