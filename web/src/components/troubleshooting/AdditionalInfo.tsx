"use client";

import { PaperPlaneRight } from "@phosphor-icons/react";
import { useId, useState } from "react";

import { postJSON } from "@/lib/api";
import { clock, date } from "@/lib/format";

import { Button } from "../ui/Button";
import { Field, TextArea } from "../ui/Form";
import { Notice } from "../ui/States";

export type InfoNote = { at: string; by: string; text: string };

/** Notes added to an escalation after the packet was built, oldest first. */
export function AdditionalInfoList({ items }: { items?: InfoNote[] }) {
  if (!items?.length) return null;
  return (
    <ul className="flex flex-col gap-2.5">
      {items.map((n, i) => (
        <li key={`${n.at}-${i}`} className="border-l-[3px] border-amber pl-3.5">
          <p className="max-w-[72ch] text-[14.5px] leading-relaxed [overflow-wrap:anywhere] whitespace-pre-line text-ink">{n.text}</p>
          <p className="num mt-0.5 text-[12.5px] text-ink-3">
            {n.by}, {date(n.at)} {clock(n.at)}
          </p>
        </li>
      ))}
    </ul>
  );
}

/**
 * Free-text box for anything the next tier should know that the packet cannot infer
 * (who is affected, what changed, what the user saw). Posts to the escalation that already exists.
 */
export function AdditionalInfoForm({
  target,
  author,
  onAdded,
  label = "Anything else the next engineer should know?",
  hint = "Optional. It is added to the escalation packet and read with everything else.",
  submitLabel = "Add to escalation",
}: {
  target: { session_id?: string; escalation_id?: number };
  author: string;
  onAdded: (notes: InfoNote[]) => void;
  label?: string;
  hint?: string;
  submitLabel?: string;
}) {
  const id = useId();
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const tooShort = text.trim().length < 3;

  async function submit() {
    setBusy(true);
    setError(null);
    try {
      const res = await postJSON<{ additional_info: InfoNote[] }>("/incidents/escalation-info", {
        ...target,
        info: text.trim(),
        author,
      });
      setText("");
      onAdded(res.additional_info);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <form
      onSubmit={(ev) => {
        ev.preventDefault();
        if (!tooShort && !busy) submit();
      }}
      className="flex flex-col gap-3"
    >
      <Field label={label} htmlFor={id} hint={hint}>
        <TextArea
          id={id}
          rows={3}
          maxLength={2000}
          value={text}
          onChange={(ev) => setText(ev.target.value)}
          placeholder="e.g. Only the Leeds office is affected, it started after Tuesday's patch window, and finance closes the month tomorrow."
        />
      </Field>
      {error && (
        <Notice tone="error" title="The information was not added">
          {error}
        </Notice>
      )}
      <div>
        <Button type="submit" loading={busy} disabled={tooShort} icon={<PaperPlaneRight size={16} />}>
          {submitLabel}
        </Button>
      </div>
    </form>
  );
}
