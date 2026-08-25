"use client";

import * as React from "react";
import { useT } from "@/lib/i18n/use-t";
import { useApi } from "@/lib/hooks/use-api";
import { useAppStore } from "@/lib/stores/app-store";
import { endpoints } from "@/lib/api/endpoints";
import { translateModel } from "@/lib/domain";
import { formatNumber } from "@/lib/format";
import { LoadingState, ErrorState } from "@/components/waterexpert/ui-states";
import { TimeSeriesChart } from "@/components/waterexpert/time-series-chart";
import { JobRunnerPanel } from "@/components/waterexpert/job-runner-panel";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Label } from "@/components/ui/label";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import type { PredictionJob } from "@/lib/api/contracts";

type MetricView = "turbidity" | "clearness" | "probability";

export function PredictionPanel() {
  const { t } = useT();
  const activeJobId = useAppStore((s) => s.activeJobId);
  const setActiveJobId = useAppStore((s) => s.setActiveJobId);

  const [model, setModel] = React.useState<string>("");
  const [split, setSplit] = React.useState<string>("test");
  const [metricView, setMetricView] = React.useState<MetricView>("turbidity");

  const { data, loading, error, reload } = useApi(
    () =>
      endpoints.predictions({
        model: model || undefined,
        split,
        job_id: activeJobId || undefined,
      }),
    [model, split, activeJobId]
  );

  const series = (data?.series ?? []) as Record<string, unknown>[];
  const availableModels = data?.available_models ?? [];
  const availableSplits = data?.available_splits ?? [];
  const comparison = (data?.model_comparison ?? []) as Record<string, unknown>[];

  // Default the model selector to the payload's selected model on first load.
  React.useEffect(() => {
    if (!model && data?.selected_model) setModel(String(data.selected_model));
  }, [data, model]);

  const chartSeries = React.useMemo(() => {
    if (metricView === "turbidity") {
      return [
        { key: "actual_turbidity", label: t("prediction.actualTurbidity"), color: "#0ea5e9" },
        { key: "predicted_turbidity", label: t("prediction.predictedTurbidity"), color: "#f59e0b", dashed: true },
      ];
    }
    if (metricView === "clearness") {
      return [
        { key: "actual_clearness", label: t("prediction.actualClearness"), color: "#10b981" },
        { key: "predicted_clearness", label: t("prediction.predictedClearness"), color: "#8b5cf6", dashed: true },
      ];
    }
    return [
      { key: "predicted_self_purification_failure_prob", label: t("prediction.selfPurificationFailure"), color: "#ef4444" },
      { key: "predicted_turbidity_surge_prob", label: t("prediction.turbiditySurge"), color: "#f59e0b" },
      { key: "predicted_critical_transition_prob", label: t("prediction.criticalTransition"), color: "#8b5cf6" },
    ];
  }, [metricView, t]);

  return (
    <div className="flex flex-col gap-6">
      <JobRunnerPanel
        onSelectJob={(job: PredictionJob) => {
          setActiveJobId(job.job_id);
          if (job.model_name) setModel(job.model_name);
        }}
      />

      <Card>
        <CardHeader className="flex-row flex-wrap items-end justify-between gap-3">
          <CardTitle>{t("prediction.predictionSeries")}</CardTitle>
          <div className="flex flex-wrap items-end gap-3">
            {availableModels.length > 0 && (
              <div className="space-y-1.5">
                <Label>{t("prediction.modelName")}</Label>
                <Select value={model} onValueChange={(v) => setModel(v as string)}>
                  <SelectTrigger className="w-56">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {availableModels.map((m) => (
                      <SelectItem key={m} value={m}>
                        {translateModel(t, m)}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
            )}
            {availableSplits.length > 0 && (
              <div className="space-y-1.5">
                <Label>{t("prediction.availableSplits")}</Label>
                <Select value={split} onValueChange={(v) => setSplit(v as string)}>
                  <SelectTrigger className="w-32">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {availableSplits.map((s) => (
                      <SelectItem key={s} value={s}>
                        {s}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
            )}
            <div className="space-y-1.5">
              <Label>{t("common.indicator")}</Label>
              <Select value={metricView} onValueChange={(v) => setMetricView(v as MetricView)}>
                <SelectTrigger className="w-40">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="turbidity">{t("prediction.predictedTurbidity")}</SelectItem>
                  <SelectItem value="clearness">{t("prediction.predictedClearness")}</SelectItem>
                  <SelectItem value="probability">{t("prediction.criticalTransition")}</SelectItem>
                </SelectContent>
              </Select>
            </div>
          </div>
        </CardHeader>
        <CardContent>
          {loading ? (
            <LoadingState />
          ) : error ? (
            <ErrorState message={error} onRetry={reload} />
          ) : series.length > 0 ? (
            <TimeSeriesChart data={series} series={chartSeries} height={360} />
          ) : (
            <p className="text-muted-foreground text-sm">{t("common.noData")}</p>
          )}
        </CardContent>
      </Card>

      {comparison.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle>{t("prediction.modelComparison")}</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="overflow-x-auto">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>{t("prediction.modelName")}</TableHead>
                    <TableHead className="text-right">{t("prediction.r2")}</TableHead>
                    <TableHead className="text-right">{t("prediction.rmse")}</TableHead>
                    <TableHead className="text-right">{t("prediction.mae")}</TableHead>
                    <TableHead className="text-right">{t("prediction.successRate")}</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {comparison.map((row, i) => (
                    <TableRow key={i}>
                      <TableCell className="font-medium">
                        {translateModel(t, String(row.model ?? row.model_name ?? ""))}
                      </TableCell>
                      <TableCell className="text-right font-mono tabular-nums">
                        {formatNumber(row.r2 ?? row.turbidity_r2, 3)}
                      </TableCell>
                      <TableCell className="text-right font-mono tabular-nums">
                        {formatNumber(row.rmse ?? row.turbidity_rmse, 3)}
                      </TableCell>
                      <TableCell className="text-right font-mono tabular-nums">
                        {formatNumber(row.mae, 3)}
                      </TableCell>
                      <TableCell className="text-right font-mono tabular-nums">
                        {formatNumber(row.success_rate, 3)}
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
