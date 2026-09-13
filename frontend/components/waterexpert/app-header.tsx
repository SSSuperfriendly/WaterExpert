"use client";

import { SidebarTrigger } from "@/components/ui/sidebar";
import { ThemeToggle } from "@/components/theme-toggle";
import { ReportExportMenu } from "@/components/waterexpert/report-export-menu";
import { useT } from "@/lib/i18n/use-t";
import { useApi } from "@/lib/hooks/use-api";
import { endpoints } from "@/lib/api/endpoints";
import { useAppStore } from "@/lib/stores/app-store";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { HugeiconsIcon } from "@hugeicons/react";
import { SidebarLeft01Icon } from "@hugeicons/core-free-icons";

export function AppHeader({ title }: { title?: string }) {
  const { t } = useT();
  const activeJobId = useAppStore((s) => s.activeJobId);
  const stationCode = useAppStore((s) => s.stationCode);
  const setStationCode = useAppStore((s) => s.setStationCode);
  const stations = useApi(() => endpoints.databaseStations());

  // The station context every query/visualization/prediction reads. The current
  // code is kept selectable even if the database listing does not mention it.
  const options = (
    (stations.data ?? []) as unknown as Array<Record<string, string>>
  )
    .map((station) => ({
      code: String(station.station_code ?? ""),
      name: String(station.station_name ?? station.station_code ?? ""),
    }))
    .filter((station) => station.code);
  if (!options.some((station) => station.code === stationCode)) {
    options.unshift({ code: stationCode, name: stationCode });
  }

  return (
    <header className="sticky top-0 z-20 flex h-14 w-full items-center gap-3 bg-background px-4 sm:px-6">
      <SidebarTrigger className="md:hidden">
        <HugeiconsIcon icon={SidebarLeft01Icon} className="size-5" />
      </SidebarTrigger>

      <h1 className="border-b pb-1 text-base font-medium leading-tight">
        {title ?? t("app.workbench")}
      </h1>

      <div className="ml-auto flex items-center gap-2">
        {options.length > 0 && (
          <Select
            value={stationCode}
            onValueChange={(value) => value && setStationCode(value)}
          >
            <SelectTrigger className="w-44" aria-label={t("database.stationCode")}>
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {options.map((station) => (
                <SelectItem key={station.code} value={station.code}>
                  {station.name}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        )}
        <ReportExportMenu jobId={activeJobId} />
        <ThemeToggle />
      </div>
    </header>
  );
}
