"use client";

import { useT } from "@/lib/i18n/use-t";
import { useApi } from "@/lib/hooks/use-api";
import { endpoints } from "@/lib/api/endpoints";
import { formatNumber, formatMaybeDate, formatPercent } from "@/lib/format";
import { AppShell } from "@/components/waterexpert/app-shell";
import { StatCard } from "@/components/waterexpert/stat-card";
import { PageHeading, LoadingState, ErrorState } from "@/components/waterexpert/ui-states";
import { DataTable, type ColumnDef } from "@/components/waterexpert/data-table";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { FilterHorizontalIcon } from "@hugeicons/core-free-icons";

export default function PreprocessPage() {
  const { t } = useT();
  const { data, loading, error, reload } = useApi(() => endpoints.preprocessSummary("2586"));

  const profiles = (data?.feature_profiles ?? []) as Record<string, unknown>[];

  const columns: ColumnDef[] = [
    {
      key: "feature",
      header: t("preprocess.feature"),
      render: (row) => (
        <span className="font-medium">{String(row.feature_label ?? row.feature ?? "—")}</span>
      ),
    },
    {
      key: "missing",
      header: t("preprocess.missing"),
      render: (row) => formatNumber(row.missing, 0),
    },
    {
      key: "outliers",
      header: t("preprocess.outliers"),
      render: (row) => formatNumber(row.outliers, 0),
    },
    {
      key: "completeness",
      header: t("preprocess.completeness"),
      render: (row) =>
        row.completeness !== undefined
          ? formatPercent(Number(row.completeness), 1)
          : row.missing_rate !== undefined
            ? formatPercent(1 - Number(row.missing_rate), 1)
            : "—",
    },
  ];

  return (
    <AppShell title={t("nav.preprocess")}>
      <PageHeading title={t("preprocess.title")} subtitle={t("preprocess.subtitle")} />

      {loading ? (
        <LoadingState />
      ) : error ? (
        <ErrorState message={error} onRetry={reload} />
      ) : data ? (
        <>
          <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
            <StatCard label={t("preprocess.rowsAnalyzed")} value={formatNumber(data.rows_analyzed, 0)} icon={FilterHorizontalIcon} />
            <StatCard label={t("preprocess.totalMissingCells")} value={formatNumber(data.total_missing_cells, 0)} />
            <StatCard label={t("preprocess.totalOutlierFlags")} value={formatNumber(data.total_outlier_flags, 0)} />
            <StatCard
              label={t("common.date")}
              value={`${formatMaybeDate(data.date_start)} ~ ${formatMaybeDate(data.date_end)}`}
            />
          </div>

          <Card>
            <CardHeader>
              <CardTitle>{t("preprocess.featureProfiles")}</CardTitle>
            </CardHeader>
            <CardContent>
              <DataTable columns={columns} rows={profiles} rowKey={(r, i) => String(r.feature ?? i)} />
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>{t("preprocess.recommendations")}</CardTitle>
            </CardHeader>
            <CardContent>
              {data.recommendations && data.recommendations.length > 0 ? (
                <ul className="list-disc space-y-1 pl-5">
                  {data.recommendations.map((rec, i) => (
                    <li key={i} className="text-muted-foreground text-sm leading-snug">
                      {rec}
                    </li>
                  ))}
                </ul>
              ) : (
                <p className="text-muted-foreground text-sm">{t("preprocess.noRecommendations")}</p>
              )}
            </CardContent>
          </Card>
        </>
      ) : null}
    </AppShell>
  );
}
