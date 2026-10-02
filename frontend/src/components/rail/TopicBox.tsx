import { useEffect, useState } from "react";
import "./SearchBox.css";

interface Props {
  value: string;
  onChange: (topic: string) => void;
}

/** "What are you looking for": a category, not a name. Committed after a
 *  pause in typing, so the ledger is not refetched on every keystroke. */
export function TopicBox({ value, onChange }: Props) {
  const [text, setText] = useState(value);

  // Follow outside changes (Clear filters, a shared link).
  useEffect(() => setText(value), [value]);

  useEffect(() => {
    const t = text.trim();
    if (t === value) return;
    const id = setTimeout(() => onChange(t), 400);
    return () => clearTimeout(id);
  }, [text, value, onChange]);

  return (
    <div className="fs">
      <label className="lab" htmlFor="f-topic">Looking for</label>
      <div className="sb-field">
        <input
          id="f-topic"
          type="search"
          placeholder="omakase, french, cheap eats…"
          autoComplete="off"
          spellCheck={false}
          value={text}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") onChange(text.trim());
          }}
        />
      </div>
    </div>
  );
}
