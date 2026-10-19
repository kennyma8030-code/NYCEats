import { useEffect, useRef, useState } from "react";
import { fetchView, type FetchInner, type FetchState } from "../lib/fresh";

export type { FetchState } from "../lib/fresh";

/**
 * Loads whenever `key` changes and aborts the request it replaces.
 * The previous data stays in place while the next request is in flight,
 * so a list can fade instead of blanking -- but it is labelled with its own
 * key, and a failure clears it: after an error there is nothing from an
 * earlier key left to render under the new one. A null key means "nothing
 * to load".
 */
export function useFetch<T>(key: string | null, load: (signal: AbortSignal) => Promise<T>): FetchState<T> {
  const [state, setState] = useState<FetchInner<T>>({ key: null, data: null, dataKey: null, error: null, loading: false });
  const loadRef = useRef(load);
  loadRef.current = load;

  useEffect(() => {
    if (key === null) {
      setState({ key: null, data: null, dataKey: null, error: null, loading: false });
      return;
    }
    const ctl = new AbortController();
    setState((s) => ({ ...s, key, error: null, loading: true }));
    loadRef.current(ctl.signal).then(
      (data) => {
        if (!ctl.signal.aborted) setState({ key, data, dataKey: key, error: null, loading: false });
      },
      (e: unknown) => {
        if (ctl.signal.aborted) return;
        setState({ key, data: null, dataKey: null, error: e instanceof Error ? e.message : String(e), loading: false });
      },
    );
    return () => ctl.abort();
  }, [key]);

  return fetchView(state, key);
}
