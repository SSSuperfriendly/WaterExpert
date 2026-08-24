"use client";

import * as React from "react";
import { useT } from "@/lib/i18n/use-t";
import { useApi } from "@/lib/hooks/use-api";
import { endpoints } from "@/lib/api/endpoints";
import { formatNumber, formatDelta } from "@/lib/format";
import { AppShell } from "@/components/waterexpert/app-shell";
import { StatCard } from "@/components/waterexpert/stat-card";
import { PageHeading, LoadingState, ErrorState } from "@/components/waterexpert/ui-states";
import { TimeSeriesChart } from "@/components/waterexpert/time-series-chart";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Label } from "@/components/ui/label";

export default function VisualizationPage() {
  const { t } = useT();
  const [indicator, setIndicator] = React.useState("turbidity");
  const [limit, setLimit] = React.useState(180);

  const { data, loading, error, reload } = useApi(
    () => endpoints.visualization("2586", indicator, limit),
    [indicator, limit]
  );

  const series = (data?.series ?? []) as { date: string; value: number }[];
  const stats = data?.stats ?? {};
  const available = data?.available_indicators ?? [];

  return (
    <AppShell title={t("nav.visualization")}>
      <PageHeading title={t("visualization.title")} subtitle={t("visualization.subtitle")} />

      <div className="flex flex-wrap items-end gap-3">
        <div className="space-y-1.5">
          <Label>{t("visualization.indicatorSelector")}</Label>
          <Select value={indicator} onValueChange={(v) => setIndicator(v as string)}>
            <SelectTrigger className="w-48">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {available.length > 0
                ? available.map((ind) => (
                    <SelectItem key={ind.key} value={ind.key}>
                      {ind.label ?? ind.key}
                    </SelectItem>
                  ))
                : ["turbidity", "secchi_depth_sd_m", "dissolved_oxygen", "water_temp", "ph"].map(
                    (k) => (
                      <SelectItem key={k} value={k}>
                        {k}
                      </SelectItem>
                    )
                  )}
            </SelectContent>
          </Select>
        </div>
        <div className="space-y-1.5">
          <Label>{t("visualization.limitSelector")}</Label>
          <Select value={String(limit)} onValueChange={(v) => setLimit(Number(v))}>
            <SelectTrigger className="w-40">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {[30, 90, 180, 365].map((n) => (
                <SelectItem key={n} value={String(n)}>
                  {n}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
      </div>

      {loading ? (
        <LoadingState />
      ) : error ? (
        <ErrorState message={error} onRetry={reload} />
      ) : data ? (
        <>
          <div className="grid grid-cols-2 gap-3 lg:grid-cols-5">
            <StatCard label={t("visualization.mean")} value={formatNumber(stats.mean, 2)} />
            <StatCard label={t("visualization.min")} value={formatNumber(stats.min, 2)} />
            <StatCard label={t("visualization.max")} value={formatNumber(stats.max, 2)} />
            <StatCard label={t("visualization.latest")} value={formatNumber(stats.latest, 2)} />
            <StatCard label={t("visualization.delta")} value={formatDelta(stats.delta, 2)} />
          </div>

          <Card>
            <CardHeader>
              <CardTitle>
                {data.indicator_label ?? indicator} · {t("visualization.series")}
              </CardTitle>
            </CardHeader>
            <CardContent>
              <TimeSeriesChart
                data={series.map((s) => ({ date: s.date, value: s.value }))}
                series={[
                  {
                    key: "value",
                    label: data.indicator_label ?? indicator,
                    color: "#0ea5e9",
                  },
                ]}
                height={340}
              />
            </CardContent>
          </Card>

          {data.correlations && data.correlations.length > 0 && (
            <Card>
              <CardHeader>
                <CardTitle>{t("visualization.correlations")}</CardTitle>
              </CardHeader>
              <CardContent>
                <ul className="grid grid-cols-1 gap-2 sm:grid-cols-2 lg:grid-cols-3">
                  {data.correlations.map((c, i) => (
                    <li
                      key={i}
                      className="flex items-center justify-between rounded-md border px-3 py-2 text-sm"
                    >
                      <span className="truncate">{c.label ?? c.indicator}</span>
                      <span className="font-mono tabular-nums">{formatNumber(c.value, 3)}</span>
                    </li>
                  ))}
                </ul>
              </CardContent>
            </Card>
          )}
        </>
      ) : null}
    </AppShell>
  );
}
