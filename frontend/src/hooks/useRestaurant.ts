import { api } from "../api/client";
import type { Algo } from "../api/types";
import { useFetch } from "./useFetch";

export function useRestaurant(entityKey: string | null, algo: Algo = "v1") {
  const state = useFetch(entityKey && `${entityKey}|${algo}`, (signal) =>
    api.restaurant(entityKey as string, algo, signal),
  );
  // useFetch keeps the last result while loading; never show one
  // restaurant's details under another's name.
  const data = state.data && state.data.entity_key === entityKey ? state.data : null;
  return { ...state, data };
}
