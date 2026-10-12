import { useEffect, useId, useMemo, useRef, useState } from "react";
import { loadNames, search, suggest, type NameHit } from "../../lib/search";
import "./SearchBox.css";

interface Props {
  /** Open this restaurant. */
  onPick: (hit: NameHit) => void;
  /** A result is highlighted; warm its data so the click is instant. */
  onPreview: (key: string) => void;
  /** Set while a picked restaurant's row loads. */
  opening: string | null;
}

type Entries = Awaited<ReturnType<typeof loadNames>>;

export function SearchBox({ onPick, onPreview, opening }: Props) {
  const [q, setQ] = useState("");
  const [entries, setEntries] = useState<Entries | null>(null);
  const [failed, setFailed] = useState(false);
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(0);
  const input = useRef<HTMLInputElement>(null);
  const listId = useId();

  // Fetch the names while the page is idle, so they are usually there before
  // the first keystroke; focusing the box also starts it. A failure is not
  // final: loadNames forgets it, the next focus or keystroke retries, and a
  // retry that works clears the error.
  const ensure = () => {
    if (entries) return;
    loadNames().then(
      (e) => {
        setEntries(e);
        setFailed(false);
      },
      () => setFailed(true),
    );
  };
  useEffect(() => {
    const t = window.setTimeout(ensure, 800);
    return () => window.clearTimeout(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const hits = useMemo(() => (entries ? search(entries, q) : []), [entries, q]);
  const guesses = useMemo(
    () => (entries && hits.length === 0 ? suggest(entries, q) : []),
    [entries, hits.length, q],
  );
  const shown = hits.length ? hits : guesses;

  useEffect(() => setActive(0), [q]);

  // Prefetch what is highlighted, after a beat, so arrowing through the list
  // does not fire a request per row.
  useEffect(() => {
    if (!open || !shown[active]) return;
    const key = shown[active].key;
    const t = window.setTimeout(() => onPreview(key), 120);
    return () => window.clearTimeout(t);
  }, [open, shown, active, onPreview]);

  // "/" focuses search from anywhere that is not already a text field.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const t = e.target as HTMLElement;
      if (e.key !== "/" || e.metaKey || e.ctrlKey || t.closest("input, textarea, select, [contenteditable]")) return;
      e.preventDefault();
      input.current?.focus();
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, []);

  const pick = (hit: NameHit) => {
    onPick(hit);
    setQ("");
    setOpen(false);
    input.current?.blur();
  };

  const onKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === "ArrowDown" || e.key === "ArrowUp") {
      e.preventDefault();
      if (!shown.length) return;
      setOpen(true);
      setActive((i) => (i + (e.key === "ArrowDown" ? 1 : shown.length - 1)) % shown.length);
    } else if (e.key === "Enter") {
      if (shown[active]) {
        e.preventDefault();
        pick(shown[active]);
      }
    } else if (e.key === "Escape") {
      // Handle it here so the app's Escape (close the panel) does not fire.
      e.stopPropagation();
      if (q) setQ("");
      else input.current?.blur();
      setOpen(false);
    }
  };

  const typed = q.trim().length > 0;
  const status = !typed
    ? null
    : failed && !entries
      ? "Couldn't load restaurant names. Keep typing to retry."
      : !entries
        ? "Loading names…"
        : !hits.length && !guesses.length
          ? "No restaurant by that name."
          : null;

  return (
    <div className="sb">
      <div className="sb-field">
        <svg viewBox="0 0 16 16" aria-hidden="true">
          <circle cx="7" cy="7" r="4.6" />
          <path d="M10.4 10.4 14 14" />
        </svg>
        <input
          ref={input}
          id="restaurant-search"
          type="search"
          placeholder="Search restaurants"
          autoComplete="off"
          spellCheck={false}
          role="combobox"
          aria-label="Search restaurants"
          aria-expanded={open && typed}
          aria-controls={listId}
          aria-autocomplete="list"
          aria-activedescendant={open && shown[active] ? `${listId}-${active}` : undefined}
          value={q}
          onChange={(e) => {
            setQ(e.target.value);
            setOpen(true);
            ensure();
          }}
          onFocus={() => {
            ensure();
            setOpen(true);
          }}
          onBlur={() => setOpen(false)}
          onKeyDown={onKeyDown}
        />
        {opening ? <span className="sb-spin" role="status" aria-label="Opening restaurant" /> : <kbd aria-hidden="true">/</kbd>}
      </div>

      {open && typed && (
        <div className="sb-pop">
          {status && <p className="sb-status">{status}</p>}
          {!hits.length && guesses.length > 0 && <p className="sb-status">Did you mean</p>}
          {shown.length > 0 && (
            <ul id={listId} role="listbox" aria-label="Restaurants">
              {shown.map((h, i) => (
                <li
                  key={h.key}
                  id={`${listId}-${i}`}
                  role="option"
                  aria-selected={i === active}
                  // mousedown, not click: keep focus in the input so blur does
                  // not close the list before the click lands.
                  onMouseDown={(e) => {
                    e.preventDefault();
                    pick(h);
                  }}
                  onMouseEnter={() => setActive(i)}
                >
                  <span className="sb-name">{h.name}</span>
                  <span className="sb-meta">
                    {[h.cuisine, h.borough].filter(Boolean).join(" · ")}
                    {h.cuisine || h.borough ? " · " : ""}
                    {h.mentions.toLocaleString()} {h.mentions === 1 ? "mention" : "mentions"}
                    {h.closed && <em> · closed</em>}
                  </span>
                  {h.via && <span className="sb-via">matched “{h.via}”</span>}
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </div>
  );
}
