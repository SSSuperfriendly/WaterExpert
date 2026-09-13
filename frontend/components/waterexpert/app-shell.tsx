"use client";

import * as React from "react";
import { useRouter, usePathname } from "next/navigation";
import { SidebarInset, SidebarProvider } from "@/components/ui/sidebar";
import { AppSidebar } from "@/components/waterexpert/app-sidebar";
import { AppHeader } from "@/components/waterexpert/app-header";
import { CaseContextBar } from "@/components/waterexpert/case-context-bar";
import { useAppStore } from "@/lib/stores/app-store";
import { Skeleton } from "@/components/ui/skeleton";

/**
 * Authenticated application shell: sidebar + header + content. Because the app
 * is a static export, auth is a client-side gate backed by sessionStorage
 * (mirroring the legacy static frontend).
 */
export function AppShell({
  title,
  children,
}: {
  title?: string;
  children: React.ReactNode;
}) {
  const session = useAppStore((s) => s.session);
  const router = useRouter();
  const pathname = usePathname();
  const [mounted, setMounted] = React.useState(false);

  React.useEffect(() => {
    // Hydration fence: the auth session lives in sessionStorage, so it can only
    // be read after first client paint. Mounting the real shell (vs. the
    // skeleton) on that paint is the canonical two-phase client-only gate.
    // eslint-disable-next-line react-hooks/set-state-in-effect -- client-only session gate; skeleton until after first client paint
    setMounted(true);
  }, []);

  React.useEffect(() => {
    if (mounted && !session) {
      router.replace("/login");
    }
  }, [mounted, session, router, pathname]);

  if (!mounted) {
    return (
      <div className="flex min-h-svh items-center justify-center p-6">
        <div className="w-full max-w-md space-y-4">
          <Skeleton className="h-10 w-full" />
          <Skeleton className="h-40 w-full" />
        </div>
      </div>
    );
  }

  if (!session) {
    // Auth gate redirecting to /login.
    return null;
  }

  return (
    <SidebarProvider>
      <AppSidebar />
      <SidebarInset className="min-w-0">
        <AppHeader title={title} />
        <div className="flex min-w-0 flex-1 flex-col gap-4 p-4 sm:p-6">
          <CaseContextBar />
          <div className="flex min-w-0 flex-col gap-6">{children}</div>
        </div>
      </SidebarInset>
    </SidebarProvider>
  );
}
