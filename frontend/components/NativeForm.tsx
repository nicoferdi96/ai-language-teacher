"use client";

import { useActionState, useState } from "react";
import { FormError } from "@/components/FormError";
import { saveNativeLanguage } from "@/lib/actions";
import { NATIVE_LANGUAGES } from "@/lib/languages";

/** Native-language picker: common chips plus a free-text fallback. */
export function NativeForm({ current, exclude }: { current: string | null; exclude: string | null }) {
  const [error, formAction, pending] = useActionState(saveNativeLanguage, null);
  const options = NATIVE_LANGUAGES.filter((name) => name !== exclude);
  const isListed = current !== null && options.includes(current);
  const [other, setOther] = useState(isListed ? "" : (current ?? ""));
  return (
    <form action={formAction} className="form">
      <fieldset className="chips" aria-describedby={error ? "native-error" : undefined}>
        <legend className="goal__state">Native language</legend>
        {options.map((name) => (
          <label key={name} className="chip">
            <input
              type="radio"
              name="native"
              value={name}
              defaultChecked={name === current}
              onChange={() => setOther("")}
            />
            {name}
          </label>
        ))}
      </fieldset>
      <label className="label" htmlFor="other">
        Not listed? Type it
      </label>
      <input
        id="other"
        name="other"
        className="field"
        placeholder="e.g. Greek"
        autoComplete="off"
        value={other}
        onChange={(event) => setOther(event.target.value)}
        aria-invalid={error ? "true" : undefined}
      />
      <FormError id="native-error" message={error} />
      <button type="submit" className="btn btn--block" disabled={pending}>
        {pending ? "Saving…" : "Continue"}
      </button>
    </form>
  );
}
