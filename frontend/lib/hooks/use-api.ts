"use client";

import * as React from "react";
import { ApiError } from "@/lib/api/client";

type State<T> = {
  data: T | null;
  loading: boolean;
  error: unknown | null;
};

/**
 * Lightweight data-fetching hook for backend GET endpoints. Re-runs whenever
 * `deps` change. Returns the data, loading flag, error object, and a `reload`
 * function. The error is kept as the thrown value (an ``ApiError`` carries the
 * stable backend ``code``) so the UI can localize it via
 * ``describeApiError`` rather than render the backend's detail string.
 */
export function useApi<T>(
  fetcher: () => Promise<T>,
  deps: React.DependencyList = []
) {
  const [state, setState] = React.useState<State<T>>({
    data: null,
    loading: true,
    error: null,
  });

  const fetcherRef = React.useRef(fetcher);
  fetcherRef.current = fetcher;

  const load = React.useCallback(async () => {
    setState((s) => ({ ...s, loading: true, error: null }));
    try {
      const data = await fetcherRef.current();
      setState({ data, loading: false, error: null });
    } catch (err) {
      setState({ data: null, loading: false, error: err });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);

  React.useEffect(() => {
    load();
  }, [load]);

  return {
    data: state.data,
    loading: state.loading,
    error: state.error,
    reload: load,
  };
}
