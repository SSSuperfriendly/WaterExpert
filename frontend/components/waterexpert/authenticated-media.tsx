"use client";

import * as React from "react";
import { absoluteAssetUrl } from "@/lib/api/client";
import { getStoredToken } from "@/lib/auth-token";

interface MediaState {
  path: string;
  url?: string;
  failed?: boolean;
}

/**
 * Render a protected backend media file.
 *
 * Every non-``/api/v1/auth/`` route requires a bearer token, and a bare
 * ``<img src>`` never sends one — so the image is fetched with the token, turned
 * into an object URL, and revoked on unmount. ``path`` is the backend-relative
 * URL the API returned (e.g. the cross-modal media endpoint).
 *
 * The loaded state is keyed by ``path`` so a changed source shows the loading
 * placeholder immediately, without a synchronous state reset inside the effect.
 */
export function AuthenticatedMedia({
  path,
  alt,
  className,
  fallbackLabel,
}: {
  path: string;
  alt: string;
  className?: string;
  fallbackLabel?: string;
}) {
  const [media, setMedia] = React.useState<MediaState>({ path });

  React.useEffect(() => {
    let objectUrl: string | null = null;
    let cancelled = false;

    const token = getStoredToken();
    fetch(absoluteAssetUrl(path), {
      headers: token ? { Authorization: `Bearer ${token}` } : {},
    })
      .then((response) => {
        if (!response.ok) throw new Error(String(response.status));
        return response.blob();
      })
      .then((blob) => {
        if (cancelled) return;
        objectUrl = URL.createObjectURL(blob);
        setMedia({ path, url: objectUrl });
      })
      .catch(() => {
        if (!cancelled) setMedia({ path, failed: true });
      });

    return () => {
      cancelled = true;
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  }, [path]);

  const current = media.path === path ? media : { path };

  if (current.failed) {
    return (
      <div
        className={`bg-muted text-muted-foreground flex items-center justify-center text-xs ${className ?? ""}`}
      >
        {fallbackLabel ?? "—"}
      </div>
    );
  }

  if (!current.url) {
    return <div className={`bg-muted animate-pulse ${className ?? ""}`} aria-hidden />;
  }

  // eslint-disable-next-line @next/next/no-img-element -- the source is a runtime object URL from an authenticated fetch; next/image cannot optimize it
  return <img src={current.url} alt={alt} className={className} />;
}
