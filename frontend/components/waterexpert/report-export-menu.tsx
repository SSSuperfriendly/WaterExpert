"use client";

import * as React from "react";
import { useT } from "@/lib/i18n/use-t";
import { useAppStore } from "@/lib/stores/app-store";
import { endpoints, REPORT_FORMATS } from "@/lib/api/endpoints";
import { absoluteAssetUrl } from "@/lib/api/client";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { HugeiconsIcon } from "@hugeicons/react";
import { Download01Icon, CheckmarkCircle01Icon } from "@hugeicons/core-free-icons";
import type { ReportFormat } from "@/lib/api/contracts";

/**
 * Report export dropdown. Downloads the generated report for the current job
 * (or the default scope) in the selected format.
 */
export function ReportExportMenu({ jobId }: { jobId?: string | null }) {
  const { t } = useT();
  const [busyFormat, setBusyFormat] = React.useState<ReportFormat | null>(null);
  const [doneFormat, setDoneFormat] = React.useState<ReportFormat | null>(null);

  const triggerDownload = React.useCallback(
    async (format: ReportFormat) => {
      setBusyFormat(format);
      setDoneFormat(null);
      try {
        const result = await endpoints.exportReport(format, jobId ?? undefined);
        const url = absoluteAssetUrl(result.download_url);
        const link = document.createElement("a");
        link.href = url;
        link.download = result.filename;
        document.body.appendChild(link);
        link.click();
        link.remove();
        setDoneFormat(format);
      } catch (err) {
        console.error("Report export failed:", err);
      } finally {
        setBusyFormat(null);
        setTimeout(() => setDoneFormat(null), 2500);
      }
    },
    [jobId]
  );

  return (
    <DropdownMenu>
      <DropdownMenuTrigger
        render={
          <Button variant="outline" size="sm" className="gap-2">
            <HugeiconsIcon icon={Download01Icon} className="size-4" />
            <span className="hidden sm:inline">{t("report.exportReport")}</span>
          </Button>
        }
      />
      <DropdownMenuContent align="end" className="w-56">
        <DropdownMenuLabel>{t("report.exportFormat")}</DropdownMenuLabel>
        <DropdownMenuSeparator />
        {REPORT_FORMATS.map((f) => (
          <DropdownMenuItem
            key={f.value}
            disabled={busyFormat !== null}
            onClick={() => triggerDownload(f.value)}
          >
            <span className="flex-1">
              {t(f.labelKey)} <span className="text-muted-foreground">({f.extension})</span>
            </span>
            {busyFormat === f.value ? (
              <span className="text-muted-foreground text-xs">{t("report.exporting")}</span>
            ) : doneFormat === f.value ? (
              <HugeiconsIcon icon={CheckmarkCircle01Icon} className="text-emerald-500 size-4" />
            ) : null}
          </DropdownMenuItem>
        ))}
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
