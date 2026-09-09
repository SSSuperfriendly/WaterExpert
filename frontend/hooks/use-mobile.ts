import * as React from "react";

const MOBILE_BREAKPOINT = 768;

// Lazily created on the client; kept at module scope so the snapshot below
// always reads the same MediaQueryList (useSyncExternalStore requires a stable
// snapshot between notifications).
let mql: MediaQueryList | null = null;

function getMql(): MediaQueryList {
  if (mql === null) {
    mql = window.matchMedia(`(max-width: ${MOBILE_BREAKPOINT - 1}px)`);
  }
  return mql;
}

export function useIsMobile() {
  const isMobile = React.useSyncExternalStore(
    (onStoreChange) => {
      const media = getMql();
      media.addEventListener("change", onStoreChange);
      return () => media.removeEventListener("change", onStoreChange);
    },
    () => getMql().matches,
    () => false
  );
  return isMobile;
}
