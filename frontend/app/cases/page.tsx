"use client";

import * as React from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { useT } from "@/lib/i18n/use-t";
import { useApi } from "@/lib/hooks/use-api";
import { endpoints } from "@/lib/api/endpoints";
import { useAppStore } from "@/lib/stores/app-store";
import { translateJobStatus } from "@/lib/domain";
import { formatDateTime } from "@/lib/format";
import { AppShell } from "@/components/waterexpert/app-shell";
import { LoadingState, ErrorState } from "@/components/waterexpert/ui-states";
import { StatCard } from "@/components/waterexpert/stat-card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Label } from "@/components/ui/label";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import type { Case, CaseSummary, Provenance } from "@/lib/api/contracts";

function caseVariant(status: string): "default" | "secondary" | "destructive" | "outline" {
  if (status === "ready") return "default";
  if (status === "running") return "secondary";
  if (status === "failed" || status === "stale") return "destructive";
  return "outline";
}

export default function CasesPage() {
  const { t } = useT();
  const router = useRouter();
  const setCaseContext = useAppStore((s) => s.setCaseContext);

  const cases = useApi<Case[]>(() => endpoints.cases());
  const summary = useApi<CaseSummary>(() => endpoints.caseSummary());

  const [creating, setCreating] = React.useState(false);
  const [title, setTitle] = React.useState("");
  const [description, setDescription] = React.useState("");
  const [targetDate, setTargetDate] = React.useState("");
  const [error, setError] = React.useState<string | null>(null);

  const openCase = (c: Case) => {
    setCaseContext(c.case_id, c.target_date ?? null);
    router.push("/prediction");
  };

  const handleCreate = async () => {
    if (!title.trim()) return;
    setCreating(true);
    setError(null);
    try {
      const created = await endpoints.createCase({
        title: title.trim(),
        description: description.trim() || undefined,
        target_date: targetDate || undefined,
      });
      setTitle("");
      setDescription("");
      setTargetDate("");
      await cases.reload();
      await summary.reload();
      openCase(created);
    } catch (err) {
      setError(err instanceof Error ? err.message : t("common.error"));
    } finally {
      setCreating(false);
    }
  };

  const rows = cases.data ?? [];

  return (
    <AppShell title={t("case.listTitle")}>
      {summary.loading ? (
        <LoadingState />
      ) : summary.error ? null : summary.data ? (
        <div className="grid grid-cols-2 gap-3 lg:grid-cols-3">
          <StatCard label={t("case.total")} value={summary.data.total} />
          <StatCard label={t("case.pending")} value={summary.data.pending_count} />
          <StatCard label={t("case.staleCount")} value={summary.data.stale_count} />
        </div>
      ) : null}

      {/* The case named by ``?case=``. Behind a Suspense boundary because it
          reads ``useSearchParams``, which a statically exported route cannot
          resolve at build time; only this block is deferred, so the rest of the
          page still renders in the prerendered HTML. */}
      <React.Suspense fallback={null}>
        <CaseDetail />
      </React.Suspense>

      <Card>
        <CardHeader>
          <CardTitle>{t("case.createTitle")}</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
            <div className="space-y-1.5 sm:col-span-2">
              <Label>{t("case.title")}</Label>
              <Input
                value={title}
                onChange={(e) => setTitle(e.target.value)}
                placeholder={t("case.createPlaceholder")}
              />
            </div>
            <div className="space-y-1.5">
              <Label>{t("case.targetDate")}</Label>
              <Input
                type="date"
                value={targetDate}
                onChange={(e) => setTargetDate(e.target.value)}
              />
            </div>
          </div>
          <div className="space-y-1.5">
            <Label>{t("case.description")}</Label>
            <Textarea
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              rows={2}
            />
          </div>
          {error && <p className="text-destructive text-xs">{error}</p>}
          <Button onClick={handleCreate} disabled={creating || !title.trim()}>
            {creating ? t("common.loading") : t("case.create")}
          </Button>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>{t("case.label")}</CardTitle>
        </CardHeader>
        <CardContent>
          {cases.loading ? (
            <LoadingState rows={5} />
          ) : cases.error ? (
            <ErrorState error={cases.error} onRetry={cases.reload} />
          ) : rows.length === 0 ? (
            <p className="text-muted-foreground text-sm">{t("common.noData")}</p>
          ) : (
            <div className="overflow-x-auto">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>{t("case.title")}</TableHead>
                    <TableHead>{t("common.status")}</TableHead>
                    <TableHead>{t("case.targetDate")}</TableHead>
                    <TableHead>{t("case.owner")}</TableHead>
                    <TableHead>{t("prediction.createdAt")}</TableHead>
                    <TableHead>{t("common.actions")}</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {rows.map((c) => (
                    <TableRow key={c.case_id}>
                      <TableCell className="max-w-[16rem] truncate font-medium">
                        {c.title ?? c.case_id}
                        {c.is_stale && (
                          <Badge variant="destructive" className="ml-2">
                            {t("case.stale")}
                          </Badge>
                        )}
                      </TableCell>
                      <TableCell>
                        <Badge variant={caseVariant(c.status)}>
                          {translateJobStatus(t, c.status)}
                        </Badge>
                      </TableCell>
                      <TableCell className="text-xs">{c.target_date ?? "—"}</TableCell>
                      <TableCell className="text-xs">{c.owner ?? "—"}</TableCell>
                      <TableCell className="text-muted-foreground text-xs">
                        {formatDateTime(c.created_at)}
                      </TableCell>
                      <TableCell>
                        <div className="flex gap-2">
                          <Button variant="outline" size="sm" onClick={() => openCase(c)}>
                            {t("case.open")}
                          </Button>
                          <Button
                            variant="ghost"
                            size="sm"
                            onClick={() =>
                              router.replace(`/cases?case=${encodeURIComponent(c.case_id)}`)
                            }
                          >
                            {t("common.details")}
                          </Button>
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
    </AppShell>
  );
}

/**
 * The case named by ``?case=``, with the provenance its results resolve
 * against.
 *
 * Provenance is the reason this block exists. Every result page already
 * resolves against a case or a job, but nothing in the UI could say *which*
 * artifacts an answer was read from — ``endpoints.caseProvenance`` had no
 * caller at all until this.
 */
function CaseDetail() {
  const { t } = useT();
  const router = useRouter();
  const selectedId = useSearchParams().get("case");

  // Both fetches resolve to null when nothing is selected, which keeps the
  // hooks unconditional: the component's shape does not change with the
  // parameter, only its content does.
  const selectedCase = useApi<Case | null>(
    () => (selectedId ? endpoints.case(selectedId) : Promise.resolve(null)),
    [selectedId]
  );
  const provenance = useApi<Provenance | null>(
    () => (selectedId ? endpoints.caseProvenance(selectedId) : Promise.resolve(null)),
    [selectedId]
  );

  if (!selectedId) return null;

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex flex-wrap items-center gap-2">
          {t("case.detailTitle")}
          <span className="font-mono text-xs font-normal">{selectedId}</span>
          <button
            type="button"
            onClick={() => router.replace("/cases")}
            className="text-muted-foreground ml-auto text-xs underline underline-offset-2"
          >
            {t("case.closeDetail")}
          </button>
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-3 text-sm">
        {selectedCase.loading ? (
          <LoadingState rows={2} />
        ) : selectedCase.error ? (
          <ErrorState error={selectedCase.error} onRetry={selectedCase.reload} />
        ) : selectedCase.data ? (
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
            <div>
              <p className="text-muted-foreground text-xs">{t("case.title")}</p>
              <p className="font-medium">{selectedCase.data.title ?? selectedId}</p>
            </div>
            <div>
              <p className="text-muted-foreground text-xs">{t("common.status")}</p>
              <Badge variant={caseVariant(selectedCase.data.status)}>
                {translateJobStatus(t, selectedCase.data.status)}
              </Badge>
            </div>
            <div>
              <p className="text-muted-foreground text-xs">{t("case.targetDate")}</p>
              <p>{selectedCase.data.target_date ?? "—"}</p>
            </div>
            <div>
              <p className="text-muted-foreground text-xs">{t("case.owner")}</p>
              <p>{selectedCase.data.owner ?? "—"}</p>
            </div>
            <div>
              <p className="text-muted-foreground text-xs">{t("case.coverage")}</p>
              <p className="text-xs">
                {selectedCase.data.coverage_start ?? "—"} → {selectedCase.data.coverage_end ?? "—"}
              </p>
            </div>
            <div>
              <p className="text-muted-foreground text-xs">{t("case.datasets")}</p>
              <p className="font-mono text-xs">
                {(selectedCase.data.input_dataset_versions ?? []).join("、") || "—"}
              </p>
            </div>
            {selectedCase.data.description ? (
              <div className="sm:col-span-2">
                <p className="text-muted-foreground text-xs">{t("case.description")}</p>
                <p>{selectedCase.data.description}</p>
              </div>
            ) : null}
          </div>
        ) : null}

        <div className="rounded-md border px-3 py-2">
          <p className="text-muted-foreground mb-2 text-xs">{t("case.provenance")}</p>
          {provenance.loading ? (
            <LoadingState rows={1} />
          ) : provenance.error ? (
            <ErrorState error={provenance.error} onRetry={provenance.reload} />
          ) : provenance.data ? (
            <div className="grid grid-cols-1 gap-2 text-xs sm:grid-cols-3">
              <div>
                <span className="text-muted-foreground">{t("case.scope")}：</span>
                {t(
                  `case.scope${(provenance.data.scope ?? "integrated").replace(/^./, (c) =>
                    c.toUpperCase()
                  )}`
                )}
              </div>
              <div>
                <span className="text-muted-foreground">{t("case.modelVersion")}：</span>
                {provenance.data.model_version ?? "—"}
              </div>
              <div>
                <span className="text-muted-foreground">{t("case.configHash")}：</span>
                <span className="font-mono">{provenance.data.config_hash ?? "—"}</span>
              </div>
              <div>
                <span className="text-muted-foreground">{t("case.generatedAt")}：</span>
                {formatDateTime(provenance.data.generated_at)}
              </div>
              <div>
                <span className="text-muted-foreground">{t("case.job")}：</span>
                <span className="font-mono">{provenance.data.job_id ?? "—"}</span>
              </div>
              <div>
                <span className="text-muted-foreground">{t("prediction.stale")}：</span>
                {provenance.data.is_stale ? t("case.stale") : t("case.notStale")}
              </div>
              {provenance.data.stale_reason ? (
                <div className="sm:col-span-3">
                  <span className="text-muted-foreground">{t("case.staleReason")}：</span>
                  {provenance.data.stale_reason}
                </div>
              ) : null}
            </div>
          ) : null}
        </div>
      </CardContent>
    </Card>
  );
}
