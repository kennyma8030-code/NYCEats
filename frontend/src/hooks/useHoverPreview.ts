import { useEffect, useMemo, useRef, useState } from "react";
import { hoverIntent } from "../lib/hover";

/** The row whose preview is up, and where that row is on the screen. */
export interface Previewed {
  key: string;
  top: number;
}

const rowTop = (key: string): number | null =>
  document.querySelector<HTMLElement>(`.row[data-key="${CSS.escape(key)}"]`)?.getBoundingClientRect().top ?? null;

/**
 * Which list row's preview is showing. The timing is lib/hover.ts; this
 * holds its answer as state and remembers where the row was, so the preview
 * can be drawn level with it. While `enabled` is false (a restaurant is
 * open, or the screen is a phone's) nothing opens.
 */
export function useHoverPreview(enabled: boolean) {
  const [shown, setShown] = useState<Previewed | null>(null);
  const on = useRef(enabled);
  on.current = enabled;

  const hover = useMemo(() => {
    const intent = hoverIntent((key) => {
      const top = key === null ? null : rowTop(key);
      setShown(key !== null && top !== null ? { key, top } : null);
    });
    return {
      /** The mouse came onto a row. */
      enter: (key: string) => {
        if (on.current) intent.enter(key);
      },
      /** The mouse left a row or the preview; focus left a row. */
      leave: intent.leave,
      /** The mouse is on the preview. */
      hold: intent.hold,
      /** The keyboard's focus is on a row. */
      focus: (key: string) => {
        if (on.current) intent.now(key);
      },
      cancel: intent.cancel,
      /** The list scrolled under the preview: follow the row. */
      follow: () => setShown((s) => {
        const top = s ? rowTop(s.key) : null;
        return s && top !== null && top !== s.top ? { key: s.key, top } : s;
      }),
    };
  }, []);

  useEffect(() => {
    if (!enabled) hover.cancel();
  }, [enabled, hover]);
  useEffect(() => hover.cancel, [hover]);

  return { shown: enabled ? shown : null, hover };
}

export type RowHover = ReturnType<typeof useHoverPreview>["hover"];
