import type { CSSProperties } from "react";
import type { Aspects } from "../../api/types";
import { ASPECTS, ASPECT_LABEL, bubblesFilled } from "../../lib/format";

interface Props {
  aspects: Aspects;
}

function Dots({ score }: { score: number | null }) {
  const filled = score == null ? 0 : bubblesFilled(score);
  return (
    <span className="dots">
      {[0, 1, 2, 3, 4].map((i) => (
        <span
          key={i}
          className="dot"
          style={{ "--p": `${Math.round(Math.max(0, Math.min(1, filled - i)) * 100)}%` } as CSSProperties}
        />
      ))}
    </span>
  );
}

export function AspectBubbles({ aspects }: Props) {
  return (
    <div className="asp">
      {ASPECTS.map((k) => {
        const v = aspects[k];
        const label = ASPECT_LABEL[k];
        return (
          <div
            key={k}
            className={`ar${v == null ? " none" : ""}`}
            role="img"
            aria-label={v == null ? `${label}: no data` : `${label}: ${bubblesFilled(v).toFixed(1)} of 5`}
          >
            <span>{label}</span>
            <Dots score={v} />
          </div>
        );
      })}
    </div>
  );
}
