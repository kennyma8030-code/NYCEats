import { api } from "../api/client";
import { useFetch } from "./useFetch";

export function useRestaurant(entityKey: string | null) {
  const state = useFetch(entityKey, (signal) => api.restaurant(entityKey as string, signal));
  // useFetch keeps the last result while loading; never show one
  // restaurant's details under another's name.
  const data = state.data && state.data.entity_key === entityKey ? state.data : null;
  return { ...state, data };
}
