"use client";

import * as React from "react";
import { useT } from "@/lib/i18n/use-t";
import { useApi } from "@/lib/hooks/use-api";
import { endpoints } from "@/lib/api/endpoints";
import { translateEventStatus, translateSeverity, describeApiError } from "@/lib/domain";
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
import type { EventRecord, EventSummary } from "@/lib/api/contracts";

const SEVERITIES = ["info", "low", "medium", "high", "critical"] as const;

function severityVariant(sev: string): "default" | "secondary" | "destructive" | "outline" {
  if (sev === "critical" || sev === "high") return "destructive";
  if (sev === "medium") return "secondary";
  return "outline";
}

function statusVariant(status: string): "default" | "secondary" | "destructive" | "outline" {
  if (status === "closed") return "default";
  if (status === "false_positive") return "outline";
  if (status === "open") return "destructive";
  return "secondary";
}

export default function EventsPage() {
  const { t } = useT();
  const events = useApi<EventRecord[]>(() => endpoints.events());
  const summary = useApi<EventSummary>(() => endpoints.eventSummary());

  const [title, setTitle] = React.useState("");
  const [description, setDescription] = React.useState("");
  const [severity, setSeverity] = React.useState("medium");
  const [targetDate, setTargetDate] = React.useState("");
  const [caseId, setCaseId] = React.useState("");
  const [creating, setCreating] = React.useState(false);
  const [formError, setFormError] = React.useState<string | null>(null);
  const [selectedId, setSelectedId] = React.useState<string | null>(null);

  const reload = () => Promise.all([events.reload(), summary.reload()]);

  const handleCreate = async () => {
    if (!title.trim() || !description.trim()) return;
    setCreating(true);
    setFormError(null);
    try {
      await endpoints.createEvent({
        title: title.trim(),
        description: description.trim(),
        severity,
        target_date: targetDate || undefined,
        case_id: caseId.trim() || undefined,
      });
      setTitle("");
      setDescription("");
      setTargetDate("");
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

  const prompt = (message: string, required = true): string | null => {
    const value = window.prompt(message);
    if (required && (!value || !value.trim())) return null;
    return value;
  };

  const rows = events.data ?? [];
  const selected = rows.find((e) => e.event_id === selectedId) ?? null;

  return (
    <AppShell title={t("events.title")}>
      {summary.loading ? (
        <LoadingState />
      ) : summary.error ? null : summary.data ? (
        <div className="grid grid-cols-2 gap-3 lg:grid-cols-3">
          <StatCard label={t("events.total")} value={summary.data.total} />
          <StatCard label={t("events.open")} value={summary.data.open} />
          <StatCard
            label={t("events.bySeverity")}
            value={
              summary.data.by_severity
                ? `${t("enums.severity.critical")} ${summary.data.by_severity["critical"] ?? 0} · ${t("enums.severity.high")} ${summary.data.by_severity["high"] ?? 0}`
                : "—"
            }
          />
        </div>
      ) : null}

      <Card>
        <CardHeader>
          <CardTitle>{t("events.createTitle")}</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
            <div className="space-y-1.5">
              <Label>{t("events.titleField")}</Label>
              <Input
                value={title}
                onChange={(e) => setTitle(e.target.value)}
                placeholder={t("events.titlePlaceholder")}
              />
            </div>
            <div className="space-y-1.5">
              <Label>{t("events.severity")}</Label>
              <select
                className="bg-background border-input ring-offset-background focus-visible:ring-ring flex h-9 w-full rounded-md border px-3 py-1 text-sm focus-visible:ring-2 focus-visible:ring-offset-2"
                value={severity}
                onChange={(e) => setSeverity(e.target.value)}
              >
                {SEVERITIES.map((s) => (
                  <option key={s} value={s}>
                    {translateSeverity(t, s)}
                  </option>
                ))}
              </select>
            </div>
            <div className="space-y-1.5">
              <Label>{t("events.targetDate")}</Label>
              <Input
                type="date"
                value={targetDate}
                onChange={(e) => setTargetDate(e.target.value)}
              />
            </div>
          </div>
          <div className="space-y-1.5">
            <Label>{t("events.description")}</Label>
            <Textarea
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              rows={2}
            />
          </div>
          {formError && <p className="text-destructive text-xs">{formError}</p>}
          <Button onClick={handleCreate} disabled={creating || !title.trim() || !description.trim()}>
            {creating ? t("common.loading") : t("events.create")}
          </Button>
        </CardContent>
      </Card>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
        <Card className="lg:col-span-2">
          <CardHeader>
            <CardTitle>{t("events.listTitle")}</CardTitle>
          </CardHeader>
          <CardContent>
            {events.loading ? (
              <LoadingState rows={5} />
            ) : events.error ? (
              <ErrorState error={events.error} onRetry={events.reload} />
            ) : rows.length === 0 ? (
              <p className="text-muted-foreground text-sm">{t("events.noEvents")}</p>
            ) : (
              <div className="overflow-x-auto">
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>{t("events.titleField")}</TableHead>
                      <TableHead>{t("events.severity")}</TableHead>
                      <TableHead>{t("common.status")}</TableHead>
                      <TableHead>{t("events.assignee")}</TableHead>
                      <TableHead>{t("events.targetDate")}</TableHead>
                      <TableHead>{t("common.actions")}</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {rows.map((e) => (
                      <TableRow
                        key={e.event_id}
                        className={selectedId === e.event_id ? "bg-muted/40" : undefined}
                      >
                        <TableCell className="max-w-[16rem] truncate font-medium">
                          {e.title}
                          {e.escalated && (
                            <Badge variant="destructive" className="ml-2">
                              {t("events.escalated")}
                            </Badge>
                          )}
                        </TableCell>
                        <TableCell>
                          <Badge variant={severityVariant(e.severity)}>
                            {translateSeverity(t, e.severity)}
                          </Badge>
                        </TableCell>
                        <TableCell>
                          <Badge variant={statusVariant(e.status)}>
                            {translateEventStatus(t, e.status)}
                          </Badge>
                        </TableCell>
                        <TableCell className="text-xs">{e.assignee ?? "—"}</TableCell>
                        <TableCell className="text-xs">{e.target_date ?? "—"}</TableCell>
                        <TableCell>
                          <div className="flex flex-wrap items-center gap-1">
                            <Button variant="ghost" size="sm" onClick={() => setSelectedId(e.event_id)}>
                              {t("common.details")}
                            </Button>
                            {e.status === "open" && (
                              <>
                                <Button
                                  variant="outline"
                                  size="sm"
                                  onClick={() => {
                                    const assignee = prompt(t("events.assigneePlaceholder"));
                                    if (assignee) act(() => endpoints.assignEvent(e.event_id, assignee));
                                  }}
                                >
                                  {t("events.assign")}
                                </Button>
                                <Button
                                  variant="ghost"
                                  size="sm"
                                  onClick={() => act(() => endpoints.escalateEvent(e.event_id))}
                                >
                                  {t("events.escalate")}
                                </Button>
                              </>
                            )}
                            {e.status === "assigned" && (
                              <Button
                                variant="outline"
                                size="sm"
                                onClick={() => act(() => endpoints.acknowledgeEvent(e.event_id))}
                              >
                                {t("events.acknowledge")}
                              </Button>
                            )}
                            {e.status === "acknowledged" && (
                              <Button
                                variant="outline"
                                size="sm"
                                onClick={() => act(() => endpoints.handleEvent(e.event_id))}
                              >
                                {t("events.handle")}
                              </Button>
                            )}
                            {e.status === "handling" && (
                              <>
                                <Button
                                  variant="outline"
                                  size="sm"
                                  onClick={() => act(() => endpoints.reviewEvent(e.event_id))}
                                >
                                  {t("events.review")}
                                </Button>
                                <Button
                                  variant="outline"
                                  size="sm"
                                  onClick={() => {
                                    const post = prompt(t("events.postMortemPlaceholder"));
                                    if (post) act(() => endpoints.closeEvent(e.event_id, post));
                                  }}
                                >
                                  {t("events.close")}
                                </Button>
                              </>
                            )}
                            {e.status === "reviewing" && (
                              <>
                                <Button
                                  variant="outline"
                                  size="sm"
                                  onClick={() => act(() => endpoints.handleEvent(e.event_id))}
                                >
                                  {t("events.handle")}
                                </Button>
                                <Button
                                  variant="outline"
                                  size="sm"
                                  onClick={() => {
                                    const post = prompt(t("events.postMortemPlaceholder"));
                                    if (post) act(() => endpoints.closeEvent(e.event_id, post));
                                  }}
                                >
                                  {t("events.close")}
                                </Button>
                              </>
                            )}
                            {e.status !== "closed" && e.status !== "false_positive" && (
                              <Button
                                variant="ghost"
                                size="sm"
                                onClick={() => {
                                  const reason = prompt(t("events.reasonPlaceholder"));
                                  if (reason) act(() => endpoints.falsePositiveEvent(e.event_id, reason));
                                }}
                              >
                                {t("events.falsePositive")}
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
                <div>
                  <p className="text-muted-foreground text-xs">{t("events.creator")}</p>
                  <p className="font-medium">{selected.creator ?? "—"}</p>
                </div>
                <div>
                  <p className="text-muted-foreground text-xs">{t("events.description")}</p>
                  <p className="whitespace-pre-wrap">{selected.description}</p>
                </div>
                {selected.post_mortem && (
                  <div>
                    <p className="text-muted-foreground text-xs">{t("events.postMortem")}</p>
                    <p className="bg-muted whitespace-pre-wrap rounded-md p-2 text-xs">
                      {selected.post_mortem}
                    </p>
                  </div>
                )}
                {selected.history && selected.history.length > 0 && (
                  <div>
                    <p className="text-muted-foreground mb-1 text-xs">{t("events.history")}</p>
                    <ul className="space-y-1">
                      {selected.history.map((h, i) => (
                        <li key={i} className="text-xs">
                          <Badge variant="outline" className="mr-1">
                            {translateEventStatus(t, h.status)}
                          </Badge>
                          <span className="text-muted-foreground">
                            {h.at ? formatDateTime(h.at) : ""} {h.by ?? ""}
                          </span>
                        </li>
                      ))}
                    </ul>
                  </div>
                )}
              </div>
            )}
          </CardContent>
        </Card>
      </div>
    </AppShell>
  );
}
