import { api } from "../api/client";
import { currentCity } from "../state/city";
import { useFetch } from "./useFetch";

export function useRestaurant(entityKey: string | null) {
  const state = useFetch(entityKey && `${currentCity()}|${entityKey}`, () => api.restaurant(entityKey as string));
  // useFetch keeps the last result while loading; never show one
  // restaurant's details under another's name.
  const data = state.current && state.data?.entity_key === entityKey ? state.data : null;
  return { ...state, data };
}
