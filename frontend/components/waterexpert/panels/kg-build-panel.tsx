"use client";

import * as React from "react";
import { useT } from "@/lib/i18n/use-t";
import { useApi } from "@/lib/hooks/use-api";
import { endpoints } from "@/lib/api/endpoints";
import { LoadingState, ErrorState } from "@/components/waterexpert/ui-states";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Checkbox } from "@/components/ui/checkbox";
import { Badge } from "@/components/ui/badge";
import { HugeiconsIcon } from "@hugeicons/react";
import { NodeMoveUpIcon, RefreshIcon } from "@hugeicons/core-free-icons";
import type { KgBuildJob } from "@/lib/api/contracts";

const POLL_INTERVAL_MS = 5000;

function statusBadge(status: string) {
  if (status === "completed") {
    return <Badge variant="secondary">✓</Badge>;
  }
  if (status === "failed") {
    return <Badge variant="destructive">✕</Badge>;
  }
  if (status === "orphaned") {
    return <Badge variant="outline">!</Badge>;
  }
  return <Badge variant="default">…</Badge>;
}

export function KgBuildPanel() {
  const { t } = useT();
  const texts = useApi(() => endpoints.knowledgeGraph.texts());

  const [jobs, setJobs] = React.useState<KgBuildJob[]>([]);
  const [jobsLoading, setJobsLoading] = React.useState(true);

  const [selected, setSelected] = React.useState<string[]>([]);
  const [maxChars, setMaxChars] = React.useState(1200);
  const [busy, setBusy] = React.useState(false);
  const [message, setMessage] = React.useState<string | null>(null);

  const txtList = texts.data?.txt ?? [];

  const loadJobs = React.useCallback(async () => {
    try {
      setJobs(await endpoints.knowledgeGraph.jobs());
    } catch {
      // jobs listing is best-effort; keep prior list on failure
    } finally {
      setJobsLoading(false);
    }
  }, []);

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

  const toggle = (name: string) => {
    setSelected((prev) =>
      prev.includes(name) ? prev.filter((n) => n !== name) : [...prev, name]
    );
  };

  const handleBuild = async () => {
    if (selected.length === 0) return;
    setBusy(true);
    setMessage(null);
    try {
      await endpoints.knowledgeGraph.build({ files: selected, max_chars: maxChars });
      setMessage(t("kg.buildSuccess"));
      setSelected([]);
      setJobsLoading(true);
      await loadJobs();
    } catch (err) {
      setMessage(err instanceof Error ? err.message : t("common.error"));
    } finally {
      setBusy(false);
    }
  };

  const handleClearKg = async () => {
    setBusy(true);
    setMessage(null);
    try {
      await endpoints.knowledgeGraph.clearKg();
      setMessage(t("kg.buildSuccess"));
    } catch (err) {
      setMessage(err instanceof Error ? err.message : t("common.error"));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="flex flex-col gap-6">
      <p className="text-muted-foreground rounded-lg border border-amber-500/30 bg-amber-500/10 px-3 py-2 text-xs">
        {t("kg.llmWarning")}
      </p>

      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <HugeiconsIcon icon={NodeMoveUpIcon} className="text-muted-foreground size-4" />
            {t("kg.selectText")}
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          {texts.loading ? (
            <LoadingState rows={3} />
          ) : texts.error ? (
            <ErrorState message={texts.error} onRetry={texts.reload} />
          ) : txtList.length === 0 ? (
            <p className="text-muted-foreground text-sm">{t("kg.noTextToBuild")}</p>
          ) : (
            <div className="space-y-2">
              {txtList.map((f) => (
                <label
                  key={f.name}
                  className="flex items-center gap-2 rounded-md border px-3 py-2 text-sm"
                >
                  <Checkbox
                    checked={selected.includes(f.name)}
                    onCheckedChange={() => toggle(f.name)}
                  />
                  <span className="min-w-0 flex-1 truncate">📝 {f.name}</span>
                </label>
              ))}
            </div>
          )}

          <div className="flex flex-wrap items-end gap-4">
            <div className="space-y-1.5">
              <Label>{t("kg.maxChars")}</Label>
              <Input
                type="number"
                min={300}
                max={3000}
                step={100}
                value={maxChars}
                onChange={(e) => setMaxChars(Number(e.target.value) || 1200)}
                className="w-40"
              />
            </div>
            <Button onClick={handleBuild} disabled={busy || selected.length === 0}>
              {t("kg.startBuild")}
            </Button>
            <Button variant="outline" onClick={handleClearKg} disabled={busy}>
              {t("kg.clearKg")}
            </Button>
          </div>

          {message && (
            <p className="text-muted-foreground rounded-lg border px-3 py-2 text-sm">{message}</p>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader className="flex-row flex-wrap items-center justify-between gap-3">
          <CardTitle>{t("kg.buildJobs")}</CardTitle>
          <Button variant="ghost" size="sm" onClick={loadJobs}>
            <HugeiconsIcon icon={RefreshIcon} className="size-4" />
            {t("common.refresh")}
          </Button>
        </CardHeader>
        <CardContent>
          {jobsLoading ? (
            <LoadingState rows={3} />
          ) : jobs.length === 0 ? (
            <p className="text-muted-foreground text-sm">{t("kg.noJobs")}</p>
          ) : (
            <div className="space-y-3">
              {jobs.map((job) => (
                <div key={job.job_id} className="rounded-md border px-3 py-2">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="font-mono text-xs">{job.job_id.slice(0, 12)}</span>
                    {statusBadge(job.status)}
                    <span className="text-muted-foreground text-xs">
                      {job.status === "completed"
                        ? `${t("kg.relationCount")}: ${job.relation_count ?? 0}`
                        : job.status === "failed"
                          ? job.error ?? job.message ?? t("status.failed")
                          : job.current_file
                            ? `${job.current_file} · ${job.progress ?? 0}%`
                            : `${t("kg.jobProgress")} ${job.progress ?? 0}%`}
                    </span>
                  </div>
                  <p className="text-muted-foreground mt-1 truncate text-xs">
                    {t("kg.jobFiles")}: {(job.files ?? []).join(", ")}
                  </p>
                </div>
              ))}
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
