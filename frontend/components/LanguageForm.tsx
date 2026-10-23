"use client";

import { useActionState } from "react";
import { FormError } from "@/components/FormError";
import { saveTargetLanguage } from "@/lib/actions";
import { TARGET_LANGUAGES } from "@/lib/languages";

/** Single-choice picker for the one language the learner will study. */
export function LanguageForm({ current }: { current: string | null }) {
  const [error, formAction, pending] = useActionState(saveTargetLanguage, null);
  return (
    <form action={formAction} className="form">
      <fieldset className="choices" aria-describedby={error ? "language-error" : undefined}>
        <legend className="goal__state">Language to learn</legend>
        {TARGET_LANGUAGES.map((language) => (
          <label key={language.code} className="choice">
            <input
              type="radio"
              name="language"
              value={language.code}
              defaultChecked={language.code === current}
              required
            />
            <span className="choice__hello" aria-hidden="true">
              {language.hello}
            </span>
            <span className="choice__flag" aria-hidden="true">
              {language.flag}
            </span>
            <span className="choice__name">{language.name}</span>
            <span className="choice__sub" lang={language.code}>
              {language.nativeName}
            </span>
          </label>
        ))}
      </fieldset>
      <FormError id="language-error" message={error} />
      <button type="submit" className="btn btn--block" disabled={pending}>
        {pending ? "Saving…" : "Continue"}
      </button>
    </form>
  );
}
