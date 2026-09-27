import type { WindowDays } from "../../api/types";
import { WINDOWS } from "../../state/filters";

interface Props {
  value: WindowDays;
  onChange: (d: WindowDays) => void;
}

export function PeriodPicker({ value, onChange }: Props) {
  return (
    <div className="wins" role="group" aria-label="Time period">
      {WINDOWS.map((w) => (
        <button
          key={w.d}
          type="button"
          aria-label={`Last ${w.long}`}
          aria-pressed={w.d === value}
          onClick={() => onChange(w.d)}
        >
          {w.short}
        </button>
      ))}
    </div>
  );
}
