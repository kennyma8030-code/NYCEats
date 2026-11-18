import { ATTRIBUTION } from "../map/style";

/** Who the map's tiles and data are from. The licences require it wherever
 *  the map shows; each screen places it where nothing covers it. */
export function MapCredit() {
  return (
    <p className="map-credit">
      {ATTRIBUTION.map((a, i) => (
        <span key={a.href}>
          {i > 0 && " "}
          <a href={a.href} target="_blank" rel="noopener noreferrer">{a.label}</a>
        </span>
      ))}
    </p>
  );
}
