"use client";

import { useT } from "@/lib/i18n/use-t";
import { useApi } from "@/lib/hooks/use-api";
import { endpoints } from "@/lib/api/endpoints";
import { formatNumber, formatMaybeDate } from "@/lib/format";
import { StatCard } from "@/components/waterexpert/stat-card";
import { LoadingState, ErrorState } from "@/components/waterexpert/ui-states";
import { Database01Icon } from "@hugeicons/core-free-icons";

export function DatabaseSummaryPanel() {
  const { t } = useT();
  const summary = useApi(() => endpoints.databaseSummary());

  return (
    <div className="flex flex-col gap-6">
      {summary.loading ? (
        <LoadingState />
      ) : summary.error ? (
        <ErrorState error={summary.error} onRetry={summary.reload} />
      ) : summary.data ? (
        <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
          <StatCard
            label={t("database.totalRecords")}
            value={formatNumber(summary.data.total_records, 0)}
            icon={Database01Icon}
          />
          <StatCard
            label={t("database.totalStations")}
            value={formatNumber(summary.data.total_stations, 0)}
          />
          <StatCard label={t("database.dateStart")} value={formatMaybeDate(summary.data.date_start)} />
          <StatCard label={t("database.dateEnd")} value={formatMaybeDate(summary.data.date_end)} />
        </div>
      ) : null}
    </div>
  );
}
