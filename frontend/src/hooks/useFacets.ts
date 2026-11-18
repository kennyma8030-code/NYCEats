import { api } from "../api/client";
import { useFetch } from "./useFetch";

/** One city's filter values; null while on the landing page, which has no filters. */
export function useFacets(city: string | null) {
  return useFetch(city && `facets|${city}`, (signal) => api.facets(signal));
}
