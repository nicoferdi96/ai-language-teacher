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
  const [picked, setPicked] = useState(isListed ? current : null);
  const [other, setOther] = useState(isListed ? "" : (current ?? ""));
  const ready = Boolean(picked || other.trim());
  return (
    <form action={formAction} className="form form--docked">
      <fieldset className="chips" aria-describedby={error ? "native-error" : undefined}>
        <legend className="sr-only">Native language</legend>
        {options.map((name) => (
          <label key={name} className="chip">
            <input
              type="radio"
              name="native"
              value={name}
              checked={picked === name}
              onChange={() => {
                setPicked(name);
                setOther("");
              }}
            />
            {name}
          </label>
        ))}
      </fieldset>
      <div className="field-group">
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
          onChange={(event) => {
            setOther(event.target.value);
            if (event.target.value.trim()) setPicked(null);
          }}
          aria-invalid={error ? "true" : undefined}
        />
      </div>
      <FormError id="native-error" message={error} />
      <div className="dock">
        <p className="dock__note">Pick one, or type it in the box.</p>
        <button type="submit" className="btn" disabled={pending || !ready}>
          {pending ? "Saving…" : "Continue"}
        </button>
      </div>
    </form>
  );
}
