import { useEffect, useRef, useState } from "react";

export interface FetchState<T> {
  data: T | null;
  error: string | null;
  loading: boolean;
}

/**
 * Loads whenever `key` changes and aborts the request it replaces.
 * The previous data stays in place while the next request is in flight,
 * so a list can fade instead of blanking. A null key means "nothing to load".
 */
export function useFetch<T>(key: string | null, load: (signal: AbortSignal) => Promise<T>): FetchState<T> {
  const [state, setState] = useState<FetchState<T>>({ data: null, error: null, loading: key !== null });
  const loadRef = useRef(load);
  loadRef.current = load;

  useEffect(() => {
    if (key === null) {
      setState({ data: null, error: null, loading: false });
      return;
    }
    const ctl = new AbortController();
    setState((s) => ({ data: s.data, error: null, loading: true }));
    loadRef.current(ctl.signal).then(
      (data) => {
        if (!ctl.signal.aborted) setState({ data, error: null, loading: false });
      },
      (e: unknown) => {
        if (ctl.signal.aborted) return;
        setState((s) => ({ data: s.data, error: e instanceof Error ? e.message : String(e), loading: false }));
      },
    );
    return () => ctl.abort();
  }, [key]);

  return state;
}
