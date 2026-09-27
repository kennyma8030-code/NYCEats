import { useEffect, useRef } from "react";
import type { LedgerItem, WindowDays } from "../../api/types";
import { Analytics } from "./Analytics";
import { CommentList } from "./CommentList";
import "./DetailPanel.css";

interface Props {
  item: LedgerItem | null;
  open: boolean;
  window: WindowDays;
  onClose: () => void;
}

/** One panel on the right: analytics fixed on the left, comments scrolling on the right. */
export function DetailPanel({ item, open, window, onClose }: Props) {
  const ref = useRef<HTMLDivElement>(null);

  // React 18 does not know `inert`, so set it directly. A closed panel is
  // still in the DOM (for the slide-out) and must not take focus.
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    if (open) el.removeAttribute("inert");
    else el.setAttribute("inert", "");
    if (open) el.scrollTop = 0;
  }, [open, item?.entity_key]);

  return (
    <div
      className={`sheet${open ? " on" : ""}`}
      ref={ref}
      role="dialog"
      aria-labelledby="sh-name"
      aria-hidden={!open}
    >
      {item && (
        <>
          <Analytics item={item} window={window} open={open} />
          <CommentList entityKey={item.entity_key} onClose={onClose} />
        </>
      )}
    </div>
  );
}
