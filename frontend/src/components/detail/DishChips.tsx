interface Props {
  /** null while loading. */
  dishes: string[] | null;
}

export function DishChips({ dishes }: Props) {
  if (dishes && dishes.length === 0) return null;
  return (
    <div>
      <p className="sh-eye dish-lab">People order</p>
      <div className="dishes">
        {dishes
          ? dishes.map((d) => <span key={d}>{d}</span>)
          : [0, 1, 2].map((i) => <span key={i} className="skel" aria-hidden="true" />)}
      </div>
    </div>
  );
}
