import { api, ledgerParams } from "../api/client";
import type { Filters } from "../state/filters";
import { useFetch } from "./useFetch";

/** `enabled` is false on the boards view, which has its own list. */
export function useLedger(filters: Filters, enabled = true) {
  return useFetch(enabled ? ledgerParams(filters) : null, (signal) => api.ledger(filters, signal));
}
