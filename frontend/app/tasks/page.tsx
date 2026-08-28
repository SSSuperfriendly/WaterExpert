"use client";

import * as React from "react";
import { useT } from "@/lib/i18n/use-t";
import { useApi } from "@/lib/hooks/use-api";
import { endpoints } from "@/lib/api/endpoints";
import { downloadAuthenticated } from "@/lib/api/client";
import { translateJobStatus, translateFailureCategory, translateModel } from "@/lib/domain";
import { formatNumber, formatDateTime } from "@/lib/format";
import { AppShell } from "@/components/waterexpert/app-shell";
import { LoadingState, ErrorState } from "@/components/waterexpert/ui-states";
import { StatCard } from "@/components/waterexpert/stat-card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import type { JobQueueSnapshot, PredictionJob, JobArtifact } from "@/lib/api/contracts";

function statusVariant(status: string): "default" | "secondary" | "destructive" | "outline" {
  if (status === "running" || status === "cancelling") return "secondary";
  if (status === "failed" || status === "timeout" || status === "orphaned") return "destructive";
  if (status === "completed") return "default";
  return "outline";
}

function ProgressBar({ value }: { value: number }) {
  const pct = Math.max(0, Math.min(100, Math.round(value)));
  return (
    <div className="flex items-center gap-2">
      <div className="bg-muted h-1.5 w-20 overflow-hidden rounded-full">
        <div
          className="bg-primary h-full rounded-full transition-all"
          style={{ width: `${pct}%` }}
        />
      </div>
      <span className="font-mono text-xs tabular-nums">{pct}%</span>
    </div>
  );
}

export default function TasksPage() {
  const { t } = useT();
  const queue = useApi<JobQueueSnapshot>(() => endpoints.jobQueue());
  const jobs = useApi<PredictionJob[]>(() => endpoints.jobs());
  const [selected, setSelected] = React.useState<PredictionJob | null>(null);

  // Keep the selected job's fresh copy in sync with the list.
  React.useEffect(() => {
    if (!selected) return;
    const fresh = jobs.data?.find((j) => j.job_id === selected.job_id);
    if (fresh) setSelected(fresh);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [jobs.data]);

  const selectedArtifacts = useApi<JobArtifact[]>(
    () => (selected ? endpoints.jobArtifacts(selected.job_id) : Promise.resolve([])),
    [selected?.job_id]
  );

  const act = async (fn: () => Promise<PredictionJob>) => {
    try {
      await fn();
      await Promise.all([queue.reload(), jobs.reload()]);
    } catch {
      // Localized by the surrounding list; nothing to do here.
    }
  };

  const rows = jobs.data ?? [];

  return (
    <AppShell title={t("tasks.title")}>
      {queue.loading ? (
        <LoadingState />
      ) : queue.error ? (
        <ErrorState error={queue.error} onRetry={queue.reload} />
      ) : queue.data ? (
        <div className="grid grid-cols-2 gap-3 lg:grid-cols-5">
          <StatCard label={t("tasks.maxConcurrent")} value={queue.data.max_concurrent_jobs} />
          <StatCard label={t("tasks.runningCount")} value={queue.data.running} />
          <StatCard label={t("tasks.queuedCount")} value={queue.data.queued} />
          <StatCard label={t("tasks.freeSlots")} value={queue.data.free_slots} />
          <StatCard label={t("tasks.timeout")} value={`${queue.data.job_timeout_seconds}s`} />
        </div>
      ) : null}

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
        <Card className="lg:col-span-2">
          <CardHeader>
            <CardTitle>{t("tasks.jobs")}</CardTitle>
          </CardHeader>
          <CardContent>
            {jobs.loading ? (
              <LoadingState rows={5} />
            ) : jobs.error ? (
              <ErrorState error={jobs.error} onRetry={jobs.reload} />
            ) : rows.length === 0 ? (
              <p className="text-muted-foreground text-sm">{t("tasks.noJobs")}</p>
            ) : (
              <div className="overflow-x-auto">
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>{t("common.status")}</TableHead>
                      <TableHead>{t("prediction.modelName")}</TableHead>
                      <TableHead>{t("tasks.progress")}</TableHead>
                      <TableHead>{t("prediction.effectiveRange")}</TableHead>
                      <TableHead>{t("prediction.createdAt")}</TableHead>
                      <TableHead>{t("common.actions")}</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {rows.map((job) => (
                      <TableRow
                        key={job.job_id}
                        className={selected?.job_id === job.job_id ? "bg-muted/40" : undefined}
                      >
                        <TableCell>
                          <Badge variant={statusVariant(job.status)}>
                            {translateJobStatus(t, job.status)}
                          </Badge>
                        </TableCell>
                        <TableCell className="font-medium">
                          {translateModel(t, job.model_name)}
                        </TableCell>
                        <TableCell>
                          <ProgressBar value={job.progress ?? 0} />
                        </TableCell>
                        <TableCell className="text-muted-foreground text-xs">
                          {job.start_date && job.end_date
                            ? `${job.start_date} → ${job.end_date}`
                            : "—"}
                        </TableCell>
                        <TableCell className="text-muted-foreground text-xs">
                          {formatDateTime(job.created_at)}
                        </TableCell>
                        <TableCell>
                          <div className="flex items-center gap-1">
                            <Button
                              variant="ghost"
                              size="sm"
                              onClick={() => setSelected(job)}
                            >
                              {t("common.details")}
                            </Button>
                            {(job.status === "queued" || job.status === "running") && (
                              <Button
                                variant="outline"
                                size="sm"
                                onClick={() => act(() => endpoints.cancelJob(job.job_id))}
                              >
                                {t("tasks.cancel")}
                              </Button>
                            )}
                            {(job.status === "failed" ||
                              job.status === "timeout" ||
                              job.status === "cancelled" ||
                              job.status === "orphaned") && (
                              <Button
                                variant="outline"
                                size="sm"
                                onClick={() => act(() => endpoints.retryJob(job.job_id))}
                              >
                                {t("tasks.retry")}
                              </Button>
                            )}
                          </div>
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
            <CardTitle>{t("common.details")}</CardTitle>
          </CardHeader>
          <CardContent>
            {!selected ? (
              <p className="text-muted-foreground text-sm">{t("common.noData")}</p>
            ) : (
              <div className="space-y-4 text-sm">
                <div className="font-mono text-xs">{selected.job_id}</div>
                <div className="grid grid-cols-2 gap-2 text-xs">
                  <div>
                    <p className="text-muted-foreground">{t("tasks.stage")}</p>
                    <p className="font-medium">{String(selected.stage ?? "—")}</p>
                  </div>
                  <div>
                    <p className="text-muted-foreground">{t("tasks.elapsed")}</p>
                    <p className="font-medium">
                      {selected.elapsed_seconds != null ? `${selected.elapsed_seconds}s` : "—"}
                    </p>
                  </div>
                  <div>
                    <p className="text-muted-foreground">{t("tasks.remaining")}</p>
                    <p className="font-medium">
                      {selected.estimated_remaining_seconds != null
                        ? `${selected.estimated_remaining_seconds}s`
                        : "—"}
                    </p>
                  </div>
                  <div>
                    <p className="text-muted-foreground">{t("tasks.failureCategory")}</p>
                    <p className="font-medium">
                      {translateFailureCategory(t, selected.failure_category)}
                    </p>
                  </div>
                </div>

                {selected.effective_parameters && (
                  <div>
                    <p className="text-muted-foreground mb-1 text-xs">{t("tasks.effective")}</p>
                    <pre className="bg-muted overflow-x-auto rounded-md p-2 font-mono text-[11px]">
                      {JSON.stringify(selected.effective_parameters, null, 2)}
                    </pre>
                  </div>
                )}

                <div className="space-y-1">
                  <p className="text-muted-foreground text-xs">{t("tasks.logs")}</p>
                  <div className="flex gap-2">
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={() =>
                        downloadAuthenticated(
                          endpoints.jobLogUrl(selected.job_id, "stdout"),
                          `${selected.job_id}.stdout.log`
                        ).catch((e) => console.error("log download failed:", e))
                      }
                    >
                      stdout
                    </Button>
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={() =>
                        downloadAuthenticated(
                          endpoints.jobLogUrl(selected.job_id, "stderr"),
                          `${selected.job_id}.stderr.log`
                        ).catch((e) => console.error("log download failed:", e))
                      }
                    >
                      stderr
                    </Button>
                  </div>
                </div>

                <div className="space-y-1">
                  <p className="text-muted-foreground text-xs">{t("tasks.artifacts")}</p>
                  {selectedArtifacts.loading ? (
                    <p className="text-muted-foreground text-xs">{t("common.loading")}</p>
                  ) : selectedArtifacts.data && selectedArtifacts.data.length > 0 ? (
                    <ul className="space-y-1">
                      {selectedArtifacts.data.map((a) => (
                        <li key={a.relative_path} className="flex justify-between gap-2 text-xs">
                          <span className="font-mono truncate">{a.relative_path}</span>
                          <span className="text-muted-foreground shrink-0">
                            {formatNumber(a.size_bytes, 0)} B
                          </span>
                        </li>
                      ))}
                    </ul>
                  ) : (
                    <p className="text-muted-foreground text-xs">{t("common.noData")}</p>
                  )}
                </div>
              </div>
            )}
          </CardContent>
        </Card>
      </div>
    </AppShell>
  );
}
