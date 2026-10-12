interface Props {
  current: number[];
  previous: number[];
}

const W = 120;
const H = 34;

// Both periods share one y scale so the comparison is honest.
function path(values: number[], max: number) {
  const step = W / Math.max(1, values.length - 1);
  return values.map((v, i) => `${i ? "L" : "M"}${(i * step).toFixed(1)} ${(32 - (v / max) * 28).toFixed(1)}`).join("");
}

export function Sparkline({ current, previous }: Props) {
  if (!current.length) return <svg className="spark" viewBox={`0 0 ${W} ${H}`} aria-hidden="true" />;
  const max = Math.max(1, ...current, ...previous);
  const a = path(current, max);
  return (
    <svg className="spark" viewBox={`0 0 ${W} ${H}`} aria-hidden="true">
      {previous.length > 0 && <path className="p" d={path(previous, max)} />}
      <path className="a" d={`${a}L${W} ${H}L0 ${H}Z`} />
      <path className="l" d={a} />
    </svg>
  );
}
