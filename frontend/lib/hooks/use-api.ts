"use client";

import * as React from "react";

type State<T> = {
  data: T | null;
  loading: boolean;
  error: unknown | null;
};

function depsEqual(a: React.DependencyList, b: React.DependencyList): boolean {
  if (a.length !== b.length) return false;
  return a.every((value, index) => Object.is(value, b[index]));
}

/**
 * Lightweight data-fetching hook for backend GET endpoints. Re-runs whenever
 * `deps` change. Returns the data, loading flag, error object, and a `reload`
 * function. The error is kept as the thrown value (an ``ApiError`` carries the
 * stable backend ``code``) so the UI can localize it via
 * ``describeApiError`` rather than render the backend's detail string.
 *
 * The latest `fetcher`/`deps` live in refs that are updated inside effects (not
 * during render, per ``react-hooks/refs``), and the caller-supplied ``deps``
 * array is never passed as another hook's dependency list (per
 * ``react-hooks/use-memo``) — the trigger effect diffs it against the previous
 * one on every commit instead. That keeps the new compiler-era lint rules happy
 * without callers having to wrap every fetcher in ``useCallback``.
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
  const depsRef = React.useRef<React.DependencyList | null>(null);
  const requestIdRef = React.useRef(0);

  // Keep the freshest fetcher reachable from request() and the trigger effect
  // below without writing a ref during render.
  React.useEffect(() => {
    fetcherRef.current = fetcher;
  });

  const request = React.useCallback((withSpinner: boolean): Promise<void> => {
    const requestId = ++requestIdRef.current;
    if (withSpinner) {
      setState((s) => ({ ...s, loading: true, error: null }));
    }
    return fetcherRef
      .current()
      .then((data) => {
        if (requestId !== requestIdRef.current) return;
        setState({ data, loading: false, error: null });
      })
      .catch((err) => {
        if (requestId !== requestIdRef.current) return;
        setState({ data: null, loading: false, error: err });
      });
  }, []);

  // Invalidate any in-flight response when the component unmounts.
  React.useEffect(() => {
    return () => {
      requestIdRef.current += 1;
    };
  }, []);

  // Fetch on mount and whenever the caller's deps change. The array is diffed
  // here rather than handed to a hook, so state is only ever written once the
  // promise settles — never synchronously from this effect.
  React.useEffect(() => {
    const previous = depsRef.current;
    depsRef.current = deps;
    if (previous !== null && depsEqual(previous, deps)) return;
    void request(false);
  });

  const reload = React.useCallback(() => request(true), [request]);

  return {
    data: state.data,
    loading: state.loading,
    error: state.error,
    reload,
  };
}
