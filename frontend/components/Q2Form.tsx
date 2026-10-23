"use client";

import { useActionState, useState } from "react";
import { FormError } from "@/components/FormError";
import { Icon } from "@/components/Icon";
import { saveLearningGoal } from "@/lib/actions";

const IDEAS = [
  "Lots of conversation",
  "Grammar explained first",
  "For travel",
  "For work meetings",
  "Total beginner",
  "I know the basics",
];

/** Open-ended learning style, with idea chips that append to the answer. */
export function Q2Form({ languageName }: { languageName: string }) {
  const [error, formAction, pending] = useActionState(saveLearningGoal, null);
  const [text, setText] = useState("");
  const addIdea = (idea: string) =>
    setText((value) => (value.trim() ? `${value.trim().replace(/[.,]$/, "")}, ${idea.toLowerCase()}` : idea));
  return (
    <form action={formAction} className="form form--docked">
      <div className="chips" role="group" aria-label="Add an idea">
        {IDEAS.map((idea) => {
          const added = text.toLowerCase().includes(idea.toLowerCase());
          return (
            <button key={idea} type="button" className="chip" aria-pressed={added} onClick={() => addIdea(idea)}>
              {added ? <Icon name="check" size={16} className="chip__check" /> : <span className="chip__plus" aria-hidden="true" />}
              {idea}
            </button>
          );
        })}
      </div>
      <div className="field-group">
        <label className="label" htmlFor="answer">
          In your own words
        </label>
        <textarea
          id="answer"
          name="answer"
          required
          rows={4}
          value={text}
          onChange={(event) => setText(event.target.value)}
          placeholder={`e.g. I'm moving abroad and want to chat in ${languageName} with my neighbours.`}
          aria-invalid={error ? "true" : undefined}
          aria-describedby={error ? "q2-error" : undefined}
          className="field field--area"
        />
      </div>
      <FormError id="q2-error" message={error} />
      <div className="dock">
        <p className="dock__note">Tap ideas or write freely. Both work.</p>
        <button type="submit" className="btn btn--sun" disabled={pending || !text.trim()}>
          {pending ? "Saving…" : "Build my plan"}
        </button>
      </div>
    </form>
  );
}
