import { api } from "../api/client";
import { useFetch } from "./useFetch";

export function useFacets() {
  return useFetch("facets", (signal) => api.facets(signal));
}
