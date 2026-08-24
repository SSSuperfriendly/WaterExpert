"use client";

import { SidebarTrigger } from "@/components/ui/sidebar";
import { ThemeToggle } from "@/components/theme-toggle";
import { ReportExportMenu } from "@/components/waterexpert/report-export-menu";
import { useT } from "@/lib/i18n/use-t";
import { useAppStore } from "@/lib/stores/app-store";
import { HugeiconsIcon } from "@hugeicons/react";
import { SidebarLeft01Icon } from "@hugeicons/core-free-icons";

export function AppHeader({ title }: { title?: string }) {
  const { t } = useT();
  const activeJobId = useAppStore((s) => s.activeJobId);

  return (
    <header className="sticky top-0 z-20 flex h-14 w-full items-center gap-3 border-b bg-background px-4 sm:px-6">
      <SidebarTrigger className="lg:hidden">
        <HugeiconsIcon icon={SidebarLeft01Icon} className="size-5" />
      </SidebarTrigger>

      <h1 className="min-w-0 flex-1 truncate text-base font-medium">
        {title ?? t("app.workbench")}
      </h1>

      <div className="flex items-center gap-2">
        <ReportExportMenu jobId={activeJobId} />
        <ThemeToggle />
      </div>
    </header>
  );
}
