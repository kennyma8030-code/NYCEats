import { useEffect, useRef } from "react";
import type { Algo, AspectKey, Aspects, LedgerItem, WindowDays } from "../../api/types";
import { useRestaurant } from "../../hooks/useRestaurant";
import { ASPECTS } from "../../lib/format";
import { Figures } from "./Figures";
import { TrendChart } from "./TrendChart";
import { AspectBubbles } from "./AspectBubbles";
import { DishChips } from "./DishChips";
import { StandoutNegatives } from "./StandoutNegatives";
import "./Analytics.css";

interface Props {
  item: LedgerItem;
  window: WindowDays;
  open: boolean;
  algo: Algo;
}

export function Analytics({ item, window, open, algo }: Props) {
  const { data } = useRestaurant(item.entity_key, algo);
  const nameRef = useRef<HTMLHeadingElement>(null);

  useEffect(() => {
    if (open) nameRef.current?.focus({ preventScroll: true });
  }, [open, item.entity_key]);

  // Prefer the detail endpoint's per-aspect scores; the ledger row's copy
  // shows until it arrives.
  const aspects: Aspects = { ...item.aspects };
  if (data) {
    for (const a of data.aspects) {
      if ((ASPECTS as string[]).includes(a.aspect)) aspects[a.aspect as AspectKey] = a.aspect_score;
    }
  }
  const eyebrow = [item.cuisine, item.borough].filter(Boolean).join(" · ");

  return (
    <section className="an">
      <div>
        {eyebrow && <p className="sh-eye">{eyebrow}</p>}
        <h2 className="sh-name" id="sh-name" tabIndex={-1} ref={nameRef}>
          {item.name}
        </h2>
        {item.neighborhood && <p className="sh-sub">{item.neighborhood}</p>}
      </div>
      <Figures item={item} window={window} />
      <TrendChart current={item.series} previous={item.previous_series} window={window} />
      <AspectBubbles aspects={aspects} />
      {algo === "v2" && <StandoutNegatives item={item} />}
      <DishChips dishes={data ? data.top_dishes.slice(0, 5).map((d) => d.name) : null} />
    </section>
  );
}
