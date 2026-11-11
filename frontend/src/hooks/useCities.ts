import { api } from "../api/client";
import { useFetch } from "./useFetch";

export function useCities() {
  return useFetch("cities", (signal) => api.cities(signal));
}
