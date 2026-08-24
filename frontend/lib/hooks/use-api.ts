"use client";

import * as React from "react";
import { ApiError } from "@/lib/api/client";

type State<T> = {
  data: T | null;
  loading: boolean;
  error: string | null;
};

/**
 * Lightweight data-fetching hook for backend GET endpoints. Re-runs whenever
 * `deps` change. Returns the data, loading flag, error message, and a `reload`
 * function.
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
      const message =
        err instanceof ApiError && err.status === 0
          ? "Network error"
          : err instanceof Error
            ? err.message
            : "Request failed";
      setState({ data: null, loading: false, error: message });
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
