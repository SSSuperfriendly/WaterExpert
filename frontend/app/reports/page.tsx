"use client";

import * as React from "react";
import { useT } from "@/lib/i18n/use-t";
import { useApi } from "@/lib/hooks/use-api";
import { endpoints, REPORT_FORMATS } from "@/lib/api/endpoints";
import { downloadAuthenticated } from "@/lib/api/client";
import { translateReportStatus, describeApiError } from "@/lib/domain";
import { formatDateTime } from "@/lib/format";
import { AppShell } from "@/components/waterexpert/app-shell";
import { LoadingState, ErrorState } from "@/components/waterexpert/ui-states";
import { StatCard } from "@/components/waterexpert/stat-card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
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
import type { ReportRecord, ReportSummary } from "@/lib/api/contracts";

function statusVariant(status: string): "default" | "secondary" | "destructive" | "outline" {
  if (status === "approved") return "default";
  if (status === "pending_review") return "secondary";
  if (status === "rejected") return "destructive";
  return "outline";
}

export default function ReportsPage() {
  const { t } = useT();
  const reports = useApi<ReportRecord[]>(() => endpoints.reports());
  const summary = useApi<ReportSummary>(() => endpoints.reportSummary());

  const [title, setTitle] = React.useState("");
  const [projectName, setProjectName] = React.useState("");
  const [caseId, setCaseId] = React.useState("");
  const [format, setFormat] = React.useState("html");
  const [creating, setCreating] = React.useState(false);
  const [formError, setFormError] = React.useState<string | null>(null);

  const reload = () => Promise.all([reports.reload(), summary.reload()]);

  const handleCreate = async () => {
    if (!title.trim()) return;
    setCreating(true);
    setFormError(null);
    try {
      await endpoints.createReport({
        title: title.trim(),
        project_name: projectName.trim() || undefined,
        case_id: caseId.trim() || undefined,
        format,
      });
      setTitle("");
      setProjectName("");
      setCaseId("");
      await reload();
    } catch (err) {
      setFormError(describeApiError(t, err));
    } finally {
      setCreating(false);
    }
  };

  const act = async (fn: () => Promise<unknown>) => {
    try {
      await fn();
      await reload();
    } catch {
      // Refusals surface via the list reload.
    }
  };

  const rows = reports.data ?? [];

  return (
    <AppShell title={t("reports.title")}>
      {summary.loading ? (
        <LoadingState />
      ) : summary.error ? null : summary.data ? (
        <div className="grid grid-cols-2 gap-3 lg:grid-cols-3">
          <StatCard label={t("reports.total")} value={summary.data.total} />
          <StatCard label={t("reports.pendingReview")} value={summary.data.pending_review} />
          <StatCard
            label={t("reports.generated")}
            value={summary.data.by_status["approved"] ?? 0}
          />
        </div>
      ) : null}

      <Card>
        <CardHeader>
          <CardTitle>{t("reports.createTitle")}</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-4">
            <div className="space-y-1.5 sm:col-span-2">
              <Label>{t("reports.titleField")}</Label>
              <Input
                value={title}
                onChange={(e) => setTitle(e.target.value)}
                placeholder={t("reports.titlePlaceholder")}
              />
            </div>
            <div className="space-y-1.5">
              <Label>{t("reports.projectName")}</Label>
              <Input value={projectName} onChange={(e) => setProjectName(e.target.value)} />
            </div>
            <div className="space-y-1.5">
              <Label>{t("reports.caseId")}</Label>
              <Input value={caseId} onChange={(e) => setCaseId(e.target.value)} placeholder="case_…" />
            </div>
          </div>
          <div className="flex flex-wrap items-end gap-3">
            <div className="space-y-1.5">
              <Label>{t("reports.format")}</Label>
              <select
                className="bg-background border-input ring-offset-background focus-visible:ring-ring flex h-9 w-full rounded-md border px-3 py-1 text-sm focus-visible:ring-2 focus-visible:ring-offset-2"
                value={format}
                onChange={(e) => setFormat(e.target.value)}
              >
                {REPORT_FORMATS.map((rf) => (
                  <option key={rf.value} value={rf.value}>
                    {t(rf.labelKey)}
                  </option>
                ))}
              </select>
            </div>
            <Button onClick={handleCreate} disabled={creating || !title.trim()}>
              {creating ? t("common.loading") : t("reports.create")}
            </Button>
          </div>
          {formError && <p className="text-destructive text-xs">{formError}</p>}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>{t("reports.listTitle")}</CardTitle>
        </CardHeader>
        <CardContent>
          {reports.loading ? (
            <LoadingState rows={5} />
          ) : reports.error ? (
            <ErrorState error={reports.error} onRetry={reports.reload} />
          ) : rows.length === 0 ? (
            <p className="text-muted-foreground text-sm">{t("reports.noReports")}</p>
          ) : (
            <div className="overflow-x-auto">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>{t("reports.titleField")}</TableHead>
                    <TableHead>{t("common.status")}</TableHead>
                    <TableHead>{t("reports.author")}</TableHead>
                    <TableHead>{t("reports.version")}</TableHead>
                    <TableHead>{t("reports.format")}</TableHead>
                    <TableHead>{t("prediction.createdAt")}</TableHead>
                    <TableHead>{t("common.actions")}</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {rows.map((r) => (
                    <TableRow key={r.report_id}>
                      <TableCell className="max-w-[18rem] truncate font-medium">
                        {r.title}
                      </TableCell>
                      <TableCell>
                        <Badge variant={statusVariant(r.status)}>
                          {translateReportStatus(t, r.status)}
                        </Badge>
                      </TableCell>
                      <TableCell className="text-xs">{r.author ?? "—"}</TableCell>
                      <TableCell className="font-mono text-xs">v{r.version ?? 1}</TableCell>
                      <TableCell className="text-xs uppercase">{r.format ?? "html"}</TableCell>
                      <TableCell className="text-muted-foreground text-xs">
                        {formatDateTime(r.created_at)}
                      </TableCell>
                      <TableCell>
                        <div className="flex flex-wrap items-center gap-1">
                          {(r.status === "draft" || r.status === "rejected") && (
                            <Button
                              variant="outline"
                              size="sm"
                              onClick={() => act(() => endpoints.submitReport(r.report_id))}
                            >
                              {t("reports.submit")}
                            </Button>
                          )}
                          {r.status === "pending_review" && (
                            <>
                              <Button
                                variant="outline"
                                size="sm"
                                onClick={() => act(() => endpoints.reviewReport(r.report_id, true))}
                              >
                                {t("reports.approve")}
                              </Button>
                              <Button
                                variant="outline"
                                size="sm"
                                onClick={() => act(() => endpoints.reviewReport(r.report_id, false))}
                              >
                                {t("reports.reject")}
                              </Button>
                            </>
                          )}
                          {r.status === "approved" && !r.download_url && (
                            <Button
                              variant="outline"
                              size="sm"
                              onClick={() => act(() => endpoints.generateReport(r.report_id))}
                            >
                              {t("reports.generate")}
                            </Button>
                          )}
                          {r.download_url && (
                            <Button
                              variant="outline"
                              size="sm"
                              onClick={() =>
                                downloadAuthenticated(r.download_url!, r.filename ?? undefined).catch(() => {})
                              }
                            >
                              {t("reports.download")}
                            </Button>
                          )}
                          {r.status !== "archived" && r.status !== "approved" && (
                            <Button
                              variant="ghost"
                              size="sm"
                              onClick={() => act(() => endpoints.archiveReport(r.report_id))}
                            >
                              {t("reports.archive")}
                            </Button>
                          )}
                          {r.status !== "approved" && r.status !== "pending_review" && (
                            <Button
                              variant="ghost"
                              size="sm"
                              onClick={() => act(() => endpoints.deleteReport(r.report_id))}
                            >
                              {t("reports.delete")}
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
    </AppShell>
  );
}
