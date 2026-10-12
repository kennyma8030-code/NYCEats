import type { Category } from "../../api/types";
import { CATEGORIES } from "../../state/filters";

interface Props {
  value: Category;
  onChange: (c: Category) => void;
}

export function CategoryPicker({ value, onChange }: Props) {
  return (
    <div className="cats" role="group" aria-label="Category">
      {CATEGORIES.map((c) => (
        <button key={c.k} type="button" title={c.hint} aria-pressed={c.k === value} onClick={() => onChange(c.k)}>
          {c.label}
        </button>
      ))}
    </div>
  );
}
