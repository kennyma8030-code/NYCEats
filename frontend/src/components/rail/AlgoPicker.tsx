import type { Algo } from "../../api/types";

interface Props {
  value: Algo;
  onChange: (a: Algo) => void;
}

const ALGOS: { a: Algo; label: string; hint: string }[] = [
  { a: "v1", label: "Original", hint: "Mentions over all time, opinions averaged evenly" },
  {
    a: "v2",
    label: "New",
    hint: "People in the last two years, bad experiences count double, flags places many people had a bad time at",
  },
];

/** Which scoring the ledger uses. Kept side by side so the two can be compared. */
export function AlgoPicker({ value, onChange }: Props) {
  return (
    <div className="wins algo" role="group" aria-label="Ranking">
      {ALGOS.map((x) => (
        <button key={x.a} type="button" title={x.hint} aria-pressed={x.a === value} onClick={() => onChange(x.a)}>
          {x.label}
        </button>
      ))}
    </div>
  );
}
