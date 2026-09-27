import { api, ledgerParams } from "../api/client";
import type { Filters } from "../state/filters";
import { useFetch } from "./useFetch";

export function useLedger(filters: Filters) {
  return useFetch(ledgerParams(filters), (signal) => api.ledger(filters, signal));
}
