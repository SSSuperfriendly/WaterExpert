"use client";

import * as React from "react";
import { useT } from "@/lib/i18n/use-t";
import { useApi } from "@/lib/hooks/use-api";
import { endpoints } from "@/lib/api/endpoints";
import { translateModelStage, describeApiError } from "@/lib/domain";
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
import type { ModelVersion, ModelSummary } from "@/lib/api/contracts";

//: Mirrors MODEL_TRANSITIONS in backend/app/services/model_service.py.
const NEXT_STAGES: Record<string, string[]> = {
  experiment: ["candidate", "retired"],
  candidate: ["in_review", "retired"],
  in_review: ["published", "candidate", "retired"],
  published: ["retired"],
  retired: [],
};

function stageVariant(stage: string): "default" | "secondary" | "destructive" | "outline" {
  if (stage === "published") return "default";
  if (stage === "retired") return "outline";
  if (stage === "in_review") return "secondary";
  return "secondary";
}

export default function ModelsPage() {
  const { t } = useT();
  const models = useApi<ModelVersion[]>(() => endpoints.models());
  const summary = useApi<ModelSummary>(() => endpoints.modelSummary());
  const current = useApi<ModelVersion | null>(() => endpoints.currentModel());

  const [modelKey, setModelKey] = React.useState("");
  const [version, setVersion] = React.useState("");
  const [stationCode, setStationCode] = React.useState("");
  const [configHash, setConfigHash] = React.useState("");
  const [notes, setNotes] = React.useState("");
  const [creating, setCreating] = React.useState(false);
  const [formError, setFormError] = React.useState<string | null>(null);

  const reload = () => Promise.all([models.reload(), summary.reload(), current.reload()]);

  const handleRegister = async () => {
    if (!modelKey.trim() || !version.trim()) return;
    setCreating(true);
    setFormError(null);
    try {
      await endpoints.registerModel({
        model_key: modelKey.trim(),
        version: version.trim(),
        station_code: stationCode.trim() || undefined,
        config_hash: configHash.trim() || undefined,
        notes: notes.trim() || undefined,
      });
      setModelKey("");
      setVersion("");
      setStationCode("");
      setConfigHash("");
      setNotes("");
      await reload();
    } catch (err) {
      setFormError(describeApiError(t, err));
    } finally {
      setCreating(false);
    }
  };

  const handleTransition = async (id: string, toStage: string) => {
    try {
      await endpoints.transitionModel(id, toStage);
      await reload();
    } catch {
      // Refusals surface via the list reload; nothing to echo here.
    }
  };

  const rows = models.data ?? [];
  const serving = !current.loading && current.data ? current.data : null;

  return (
    <AppShell title={t("models.title")}>
      {summary.loading ? (
        <LoadingState />
      ) : summary.error ? null : summary.data ? (
        <div className="grid grid-cols-2 gap-3 lg:grid-cols-3">
          <StatCard label={t("models.total")} value={summary.data.total} />
          <StatCard label={t("models.published")} value={summary.data.published} />
          <StatCard
            label={t("models.currentServing")}
            value={
              serving
                ? `${serving.model_key} · ${serving.version}`
                : t("models.nonePublished")
            }
          />
        </div>
      ) : null}

      <Card>
        <CardHeader>
          <CardTitle>{t("models.registerTitle")}</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-4">
            <div className="space-y-1.5">
              <Label>{t("models.modelKey")}</Label>
              <Input
                value={modelKey}
                onChange={(e) => setModelKey(e.target.value)}
                placeholder={t("models.modelKeyPlaceholder")}
              />
            </div>
            <div className="space-y-1.5">
              <Label>{t("models.version")}</Label>
              <Input
                value={version}
                onChange={(e) => setVersion(e.target.value)}
                placeholder={t("models.versionPlaceholder")}
              />
            </div>
            <div className="space-y-1.5">
              <Label>{t("models.stationCode")}</Label>
              <Input
                value={stationCode}
                onChange={(e) => setStationCode(e.target.value)}
                placeholder="2586"
              />
            </div>
            <div className="space-y-1.5">
              <Label>{t("models.configHash")}</Label>
              <Input
                value={configHash}
                onChange={(e) => setConfigHash(e.target.value)}
                placeholder="sha256:…"
              />
            </div>
          </div>
          <div className="space-y-1.5">
            <Label>{t("models.notes")}</Label>
            <Input value={notes} onChange={(e) => setNotes(e.target.value)} />
          </div>
          {formError && <p className="text-destructive text-xs">{formError}</p>}
          <Button onClick={handleRegister} disabled={creating || !modelKey.trim() || !version.trim()}>
            {creating ? t("common.loading") : t("models.register")}
          </Button>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>{t("models.listTitle")}</CardTitle>
        </CardHeader>
        <CardContent>
          {models.loading ? (
            <LoadingState rows={5} />
          ) : models.error ? (
            <ErrorState error={models.error} onRetry={models.reload} />
          ) : rows.length === 0 ? (
            <p className="text-muted-foreground text-sm">{t("models.noModels")}</p>
          ) : (
            <div className="overflow-x-auto">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>{t("models.modelKey")}</TableHead>
                    <TableHead>{t("models.version")}</TableHead>
                    <TableHead>{t("models.stage")}</TableHead>
                    <TableHead>{t("models.author")}</TableHead>
                    <TableHead>{t("models.createdAt")}</TableHead>
                    <TableHead>{t("models.publishedAt")}</TableHead>
                    <TableHead>{t("models.transition")}</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {rows.map((m) => (
                    <TableRow key={m.model_version_id}>
                      <TableCell className="font-medium">{m.model_key}</TableCell>
                      <TableCell className="font-mono text-xs">{m.version}</TableCell>
                      <TableCell>
                        <Badge variant={stageVariant(m.stage)}>
                          {translateModelStage(t, m.stage)}
                        </Badge>
                      </TableCell>
                      <TableCell className="text-xs">{m.author ?? "—"}</TableCell>
                      <TableCell className="text-muted-foreground text-xs">
                        {formatDateTime(m.created_at)}
                      </TableCell>
                      <TableCell className="text-muted-foreground text-xs">
                        {m.published_at ? formatDateTime(m.published_at) : "—"}
                      </TableCell>
                      <TableCell>
                        <div className="flex flex-wrap items-center gap-1">
                          {(NEXT_STAGES[m.stage] ?? []).map((next) => (
                            <Button
                              key={next}
                              variant="outline"
                              size="sm"
                              onClick={() => handleTransition(m.model_version_id, next)}
                            >
                              {translateModelStage(t, next)}
                            </Button>
                          ))}
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
