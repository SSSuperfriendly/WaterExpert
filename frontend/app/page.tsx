"use client";

import Link from "next/link";
import { useT } from "@/lib/i18n/use-t";
import { useApi } from "@/lib/hooks/use-api";
import { endpoints } from "@/lib/api/endpoints";
import { integratedScope } from "@/lib/hooks/use-artifact-scope";
import {
  translateModel,
  translateRiskMetric,
  translateJobStatus,
  translateDataType,
} from "@/lib/domain";
import { formatNumber, formatMaybeDate, formatDateTime } from "@/lib/format";
import { AppShell } from "@/components/waterexpert/app-shell";
import { StatCard } from "@/components/waterexpert/stat-card";
import { LoadingState, ErrorState } from "@/components/waterexpert/ui-states";
import { ScenarioHighPriorityTable, ScenarioCountBadges } from "@/components/waterexpert/scenario-feed";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Database01Icon, Activity01Icon, Flag01Icon, Target01Icon } from "@hugeicons/core-free-icons";

export default function OverviewPage() {
  const { t } = useT();
  const { data, loading, error, reload } = useApi(() => endpoints.dashboard(integratedScope()));

  const recentJobs = useApi(() => endpoints.jobs());
  const qualityAlerts = useApi(() => endpoints.datasetQualityAlerts(5));
  const caseSummary = useApi(() => endpoints.caseSummary());

  const station = data?.station_profile;
  const testModels = data?.test_models ?? {};
  const best = data?.best_model_summary ?? {};
  const risk = data?.threshold_risk_snapshot ?? {};

  const modelEntries = Object.entries(testModels);

  return (
    <AppShell title={t("nav.overview")}>

      {loading ? (
        <LoadingState />
      ) : error ? (
        <ErrorState error={error} onRetry={reload} />
      ) : data ? (
        <>
          <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
            <StatCard
              label={t("overview.product")}
              value={String(data.product_name ?? "—")}
              icon={Database01Icon}
            />
            <StatCard
              label={t("overview.algorithmCore")}
              value={String(data.algorithm_core ?? "—")}
              icon={Activity01Icon}
            />
            <StatCard
              label={t("overview.dailyRows")}
              value={formatNumber(station?.daily_rows, 0)}
              hint={`${formatMaybeDate(station?.date_start)} ~ ${formatMaybeDate(station?.date_end)}`}
              icon={Flag01Icon}
            />
            <StatCard
              label={t("overview.matchedModelRows")}
              value={formatNumber(station?.matched_model_rows, 0)}
              icon={Target01Icon}
            />
          </div>

          <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
            <Card>
              <CardHeader className="flex-row items-center justify-between">
                <CardTitle>{t("overview.recentTasks")}</CardTitle>
                <Link href="/tasks" className="text-muted-foreground text-xs hover:underline">
                  {t("overview.viewAll")}
                </Link>
              </CardHeader>
              <CardContent className="space-y-2 text-sm">
                {recentJobs.data && recentJobs.data.length > 0 ? (
                  recentJobs.data.slice(0, 5).map((j) => (
                    <div key={j.job_id} className="flex items-center justify-between gap-2">
                      <span className="truncate font-medium">{translateModel(t, j.model_name)}</span>
                      <span className="text-muted-foreground shrink-0 text-xs">
                        {translateJobStatus(t, j.status)} · {formatDateTime(j.created_at)}
                      </span>
                    </div>
                  ))
                ) : (
                  <p className="text-muted-foreground text-xs">{t("overview.noRecentTasks")}</p>
                )}
              </CardContent>
            </Card>

            <Card>
              <CardHeader className="flex-row items-center justify-between">
                <CardTitle>{t("overview.qualityAlerts")}</CardTitle>
                <Link href="/database" className="text-muted-foreground text-xs hover:underline">
                  {t("overview.viewAll")}
                </Link>
              </CardHeader>
              <CardContent className="space-y-2 text-sm">
                {qualityAlerts.data && qualityAlerts.data.length > 0 ? (
                  qualityAlerts.data.map((d) => (
                    <div key={d.version_id} className="flex items-center justify-between gap-2">
                      <span className="truncate">
                        {translateDataType(t, d.data_type)} · {d.source_name ?? d.version}
                      </span>
                      <span className="text-muted-foreground shrink-0 text-xs">
                        {translateJobStatus(t, d.status)}
                      </span>
                    </div>
                  ))
                ) : (
                  <p className="text-muted-foreground text-xs">{t("overview.noQualityAlerts")}</p>
                )}
              </CardContent>
            </Card>

            <Card>
              <CardHeader className="flex-row items-center justify-between">
                <CardTitle>{t("overview.pendingCases")}</CardTitle>
                <Link href="/cases" className="text-muted-foreground text-xs hover:underline">
                  {t("overview.viewAll")}
                </Link>
              </CardHeader>
              <CardContent className="space-y-2 text-sm">
                <Row label={t("case.total")} value={formatNumber(caseSummary.data?.total, 0)} />
                <Row label={t("case.pending")} value={formatNumber(caseSummary.data?.pending_count, 0)} />
                <Row label={t("case.staleCount")} value={formatNumber(caseSummary.data?.stale_count, 0)} />
              </CardContent>
            </Card>
          </div>

          <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
            <Card>
              <CardHeader>
                <CardTitle>{t("overview.stationProfile")}</CardTitle>
              </CardHeader>
              <CardContent className="space-y-2 text-sm">
                <Row label={t("common.station")} value={`${station?.station_name ?? "—"} (${station?.station_code ?? ""})`} />
                <Row label={t("overview.river")} value={String(station?.river ?? "—")} />
                <Row label={t("overview.basin")} value={String(station?.basin ?? "—")} />
                <Row
                  label={t("overview.location")}
                  value={`${formatNumber(station?.longitude, 4)}, ${formatNumber(station?.latitude, 4)}`}
                />
                <Row label={t("overview.purpose")} value={String(data.purpose ?? "—")} />
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle>{t("overview.bestModel")}</CardTitle>
              </CardHeader>
              <CardContent className="space-y-2 text-sm">
                <Row
                  label={t("prediction.predictedTurbidity")}
                  value={translateModel(t, String(best.best_test_turbidity_model ?? ""))}
                />
                <Row
                  label={t("prediction.predictedClearness")}
                  value={translateModel(t, String(best.best_test_clearness_model ?? ""))}
                />
                <p className="text-muted-foreground pt-2 text-xs">{t("overview.artifactScope")}: {String(data.artifact_scope ?? "—")}</p>
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle>{t("overview.thresholdRisk")}</CardTitle>
              </CardHeader>
              <CardContent className="space-y-1.5 text-sm">
                {Object.entries(risk).length === 0 ? (
                  <p className="text-muted-foreground text-xs">{t("common.noData")}</p>
                ) : (
                  Object.entries(risk).map(([key, value]) => (
                    <Row key={key} label={translateRiskMetric(t, key)} value={formatNumber(value, 3)} />
                  ))
                )}
              </CardContent>
            </Card>
          </div>

          <Card>
            <CardHeader>
              <CardTitle>{t("overview.testModels")}</CardTitle>
            </CardHeader>
            <CardContent>
              {modelEntries.length === 0 ? (
                <p className="text-muted-foreground text-sm">{t("common.noData")}</p>
              ) : (
                <div className="overflow-x-auto">
                  <Table>
                    <TableHeader>
                      <TableRow>
                        <TableHead>{t("prediction.modelName")}</TableHead>
                        <TableHead className="text-right">{t("prediction.r2")}</TableHead>
                        <TableHead className="text-right">{t("prediction.rmse")}</TableHead>
                        <TableHead className="text-right">{t("prediction.r2")} · {t("prediction.predictedClearness")}</TableHead>
                        <TableHead className="text-right">{t("prediction.rmse")} · {t("prediction.predictedClearness")}</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {modelEntries.map(([model, metrics]) => (
                        <TableRow key={model}>
                          <TableCell className="font-medium">{translateModel(t, model)}</TableCell>
                          <TableCell className="text-right font-mono tabular-nums">
                            {formatNumber(metrics.turbidity_r2, 3)}
                          </TableCell>
                          <TableCell className="text-right font-mono tabular-nums">
                            {formatNumber(metrics.turbidity_rmse, 3)}
                          </TableCell>
                          <TableCell className="text-right font-mono tabular-nums">
                            {formatNumber(metrics.clearness_r2, 3)}
                          </TableCell>
                          <TableCell className="text-right font-mono tabular-nums">
                            {formatNumber(metrics.clearness_rmse, 3)}
                          </TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                </div>
              )}
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>{t("overview.scenarioCounts")}</CardTitle>
            </CardHeader>
            <CardContent>
              <ScenarioCountBadges counts={data.scenario_counts ?? {}} />
            </CardContent>
          </Card>

          {data.high_priority_days && data.high_priority_days.length > 0 && (
            <Card>
              <CardHeader>
                <CardTitle>{t("overview.highPriorityDays")}</CardTitle>
              </CardHeader>
              <CardContent>
                <ScenarioHighPriorityTable days={data.high_priority_days} />
              </CardContent>
            </Card>
          )}
        </>
      ) : null}
    </AppShell>
  );
}

function Row({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="flex items-start justify-between gap-4">
      <span className="text-muted-foreground shrink-0 text-xs">{label}</span>
      <span className="min-w-0 text-right text-sm leading-snug">{value}</span>
    </div>
  );
}
