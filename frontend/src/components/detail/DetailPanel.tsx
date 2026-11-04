import { useEffect, useRef, useState } from "react";
import type { Algo, LedgerItem, WindowDays } from "../../api/types";
import { Analytics } from "./Analytics";
import { CommentList } from "./CommentList";
import { VoiceList, type VoiceView } from "./VoiceList";
import "./DetailPanel.css";

interface Props {
  item: LedgerItem | null;
  open: boolean;
  window: WindowDays;
  algo: Algo;
  onClose: () => void;
}

/** A full-screen panel: analytics fixed on the left, comments scrolling on the right. */
export function DetailPanel({ item, open, window, algo, onClose }: Props) {
  const ref = useRef<HTMLDivElement>(null);
  // The comments behind a clicked number, shown in place of the comment list.
  // They belong to one place: another one, or closing, drops them.
  const [voices, setVoices] = useState<VoiceView | null>(null);
  useEffect(() => setVoices(null), [item?.entity_key, open]);

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
          <Analytics item={item} window={window} open={open} algo={algo} onBack={onClose} onVoices={setVoices} />
          {voices ? (
            <VoiceList entityKey={item.entity_key} view={voices} onBack={() => setVoices(null)} />
          ) : (
            <CommentList entityKey={item.entity_key} />
          )}
        </>
      )}
    </div>
  );
}
