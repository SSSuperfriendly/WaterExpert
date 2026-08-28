"use client";

import * as React from "react";
import { useT } from "@/lib/i18n/use-t";
import { useAppStore } from "@/lib/stores/app-store";
import { endpoints } from "@/lib/api/endpoints";
import { translateModel } from "@/lib/domain";
import { formatDateTime } from "@/lib/format";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Checkbox } from "@/components/ui/checkbox";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { HugeiconsIcon } from "@hugeicons/react";
import { Activity01Icon, RefreshIcon } from "@hugeicons/core-free-icons";
import type { PredictionJob } from "@/lib/api/contracts";

const MODELS = ["cmfbe_stgcn", "mscim", "mscim_no_kg"] as const;
const POLL_INTERVAL_MS = 5000;

/**
 * The date range the pipeline actually ran on.
 *
 * A job may ask for a window wider than the data covers; the pipeline clips it
 * and reports what it used in `effective_parameters`. Showing that rather than
 * the request keeps the table honest about what produced the results.
 */
function effectiveRange(t: ReturnType<typeof useT>["t"], job: PredictionJob) {
  const effective = job.effective_parameters;
  const start = effective?.effective_start_date ?? job.start_date;
  const end = effective?.effective_end_date ?? job.end_date;
  if (!start && !end) return t("prediction.rangeFullCoverage");
  return `${start ?? "—"} → ${end ?? "—"}`;
}

function statusBadge(t: ReturnType<typeof useT>["t"], status: string) {
  if (status === "completed") {
    return <Badge variant="secondary">{t("status.completed")}</Badge>;
  }
  if (status === "failed") {
    return <Badge variant="destructive">{t("status.failed")}</Badge>;
  }
  if (status === "orphaned") {
    return <Badge variant="outline">{t("status.error")}</Badge>;
  }
  return <Badge variant="default">{t("status.running")}</Badge>;
}

export function JobRunnerPanel({
  onSelectJob,
}: {
  onSelectJob?: (job: PredictionJob) => void;
}) {
  const { t } = useT();
  const activeJobId = useAppStore((s) => s.activeJobId);
  const setActiveJobId = useAppStore((s) => s.setActiveJobId);

  const [jobs, setJobs] = React.useState<PredictionJob[]>([]);
  const [loading, setLoading] = React.useState(true);
  const [creating, setCreating] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);

  // Form state
  const [model, setModel] = React.useState<string>("cmfbe_stgcn");
  const [startDate, setStartDate] = React.useState("");
  const [endDate, setEndDate] = React.useState("");
  const [useExisting, setUseExisting] = React.useState(true);

  const loadJobs = React.useCallback(async () => {
    try {
      const list = await endpoints.jobs();
      setJobs(list);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : t("common.error"));
    } finally {
      setLoading(false);
    }
  }, [t]);

  React.useEffect(() => {
    loadJobs();
  }, [loadJobs]);

  // Poll while any job is running.
  React.useEffect(() => {
    const hasRunning = jobs.some((j) => j.status === "running");
    if (!hasRunning) return;
    const id = setInterval(loadJobs, POLL_INTERVAL_MS);
    return () => clearInterval(id);
  }, [jobs, loadJobs]);

  const handleCreate = async () => {
    setCreating(true);
    setError(null);
    try {
      await endpoints.createJob({
        model_name: model,
        station_code: "2586",
        start_date: startDate || undefined,
        end_date: endDate || undefined,
        use_existing_artifacts: useExisting,
      });
      await loadJobs();
    } catch (err) {
      setError(err instanceof Error ? err.message : t("common.error"));
    } finally {
      setCreating(false);
    }
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <HugeiconsIcon icon={Activity01Icon} className="text-muted-foreground size-4" />
          {t("prediction.jobRunner")}
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4">
          <div className="space-y-1.5">
            <Label>{t("prediction.modelName")}</Label>
            <Select value={model} onValueChange={(v) => setModel(v as string)}>
              <SelectTrigger className="w-full">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {MODELS.map((m) => (
                  <SelectItem key={m} value={m}>
                    {translateModel(t, m)}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          <div className="space-y-1.5">
            <Label>{t("prediction.startDate")}</Label>
            <Input type="date" value={startDate} onChange={(e) => setStartDate(e.target.value)} />
          </div>

          <div className="space-y-1.5">
            <Label>{t("prediction.endDate")}</Label>
            <Input type="date" value={endDate} onChange={(e) => setEndDate(e.target.value)} />
          </div>
        </div>

        <div className="flex flex-wrap items-center justify-between gap-3">
          <label className="flex items-center gap-2 text-sm">
            <Checkbox
              checked={useExisting}
              onCheckedChange={(v) => setUseExisting(v === true)}
            />
            {t("prediction.useExisting")}
          </label>
          <Button onClick={handleCreate} disabled={creating}>
            {creating ? t("prediction.running") : t("prediction.runJob")}
          </Button>
        </div>

        {error && <p className="text-destructive text-xs">{error}</p>}

        <div className="space-y-2">
          <div className="flex items-center justify-between">
            <p className="text-sm font-medium">{t("prediction.jobList")}</p>
            <Button variant="ghost" size="sm" onClick={loadJobs}>
              <HugeiconsIcon icon={RefreshIcon} className="size-4" />
              {t("common.refresh")}
            </Button>
          </div>

          {loading ? (
            <p className="text-muted-foreground text-sm">{t("common.loading")}</p>
          ) : jobs.length === 0 ? (
            <p className="text-muted-foreground text-sm">{t("prediction.noJobs")}</p>
          ) : (
            <div className="overflow-x-auto">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>{t("prediction.jobId")}</TableHead>
                    <TableHead>{t("prediction.modelName")}</TableHead>
                    <TableHead>{t("prediction.effectiveRange")}</TableHead>
                    <TableHead>{t("common.status")}</TableHead>
                    <TableHead>{t("prediction.createdAt")}</TableHead>
                    <TableHead>{t("common.actions")}</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {jobs.map((job) => (
                    <TableRow key={job.job_id}>
                      <TableCell className="font-mono text-xs">{job.job_id.slice(0, 12)}</TableCell>
                      <TableCell>{translateModel(t, job.model_name)}</TableCell>
                      <TableCell className="text-xs">
                        {effectiveRange(t, job)}
                      </TableCell>
                      <TableCell>{statusBadge(t, job.status)}</TableCell>
                      <TableCell className="text-xs">{formatDateTime(job.created_at)}</TableCell>
                      <TableCell>
                        {job.status === "completed" && (
                          <Button
                            variant={activeJobId === job.job_id ? "secondary" : "outline"}
                            size="sm"
                            onClick={() => {
                              setActiveJobId(job.job_id);
                              onSelectJob?.(job);
                            }}
                          >
                            {t("common.view")}
                          </Button>
                        )}
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>
          )}
        </div>
      </CardContent>
    </Card>
  );
}
