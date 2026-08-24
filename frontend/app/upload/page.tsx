"use client";

import * as React from "react";
import { useT } from "@/lib/i18n/use-t";
import { useApi } from "@/lib/hooks/use-api";
import { endpoints } from "@/lib/api/endpoints";
import { formatDateTime } from "@/lib/format";
import { AppShell } from "@/components/waterexpert/app-shell";
import { PageHeading, LoadingState, ErrorState } from "@/components/waterexpert/ui-states";
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
import { HugeiconsIcon } from "@hugeicons/react";
import { Upload01Icon, FileImportIcon } from "@hugeicons/core-free-icons";

const DATA_TYPES = [
  { value: "water_quality", labelKey: "upload.waterQuality" },
  { value: "weather", labelKey: "upload.weather" },
  { value: "hydrodynamics", labelKey: "upload.hydrodynamics" },
  { value: "water_control", labelKey: "upload.waterControl" },
  { value: "boundary_labels", labelKey: "upload.boundaryLabels" },
  { value: "spatial", labelKey: "upload.spatial" },
];

export default function UploadPage() {
  const { t } = useT();
  const history = useApi(() => endpoints.imports());

  const [dataType, setDataType] = React.useState("water_quality");
  const [timeGranularity, setTimeGranularity] = React.useState("daily");
  const [sourceName, setSourceName] = React.useState("");
  const [filePath, setFilePath] = React.useState("");
  const [files, setFiles] = React.useState<File[]>([]);
  const [busy, setBusy] = React.useState(false);
  const [message, setMessage] = React.useState<string | null>(null);

  const handleFiles = (list: FileList | null) => {
    if (!list) return;
    setFiles(Array.from(list));
  };

  const handleUpload = async () => {
    if (files.length === 0) return;
    setBusy(true);
    setMessage(null);
    try {
      const formData = new FormData();
      formData.set("data_type", dataType);
      formData.set("station_code", "2586");
      formData.set("time_granularity", timeGranularity);
      files.forEach((f) => formData.append("files", f));
      await endpoints.uploadData(formData);
      setMessage(t("upload.uploadSuccess"));
      setFiles([]);
      history.reload();
    } catch (err) {
      setMessage(err instanceof Error ? err.message : t("common.error"));
    } finally {
      setBusy(false);
    }
  };

  const handleImport = async () => {
    setBusy(true);
    setMessage(null);
    try {
      await endpoints.importData({
        data_type: dataType,
        source_name: sourceName,
        file_path: filePath,
        time_granularity: timeGranularity,
        station_code: "2586",
      });
      setMessage(t("upload.importSuccess"));
      history.reload();
    } catch (err) {
      setMessage(err instanceof Error ? err.message : t("common.error"));
    } finally {
      setBusy(false);
    }
  };

  const imports = (history.data ?? []) as Record<string, unknown>[];

  return (
    <AppShell title={t("nav.upload")}>
      <PageHeading title={t("upload.title")} subtitle={t("upload.subtitle")} />

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <HugeiconsIcon icon={Upload01Icon} className="text-muted-foreground size-4" />
              {t("upload.selectFiles")}
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-1.5">
                <Label>{t("upload.dataType")}</Label>
                <Select value={dataType} onValueChange={(v) => setDataType(v as string)}>
                  <SelectTrigger className="w-full">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {DATA_TYPES.map((dt) => (
                      <SelectItem key={dt.value} value={dt.value}>
                        {t(dt.labelKey)}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <div className="space-y-1.5">
                <Label>{t("upload.timeGranularity")}</Label>
                <Select value={timeGranularity} onValueChange={(v) => setTimeGranularity(v as string)}>
                  <SelectTrigger className="w-full">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="daily">{t("upload.daily")}</SelectItem>
                    <SelectItem value="hourly">{t("upload.hourly")}</SelectItem>
                  </SelectContent>
                </Select>
              </div>
            </div>

            <label className="flex cursor-pointer flex-col items-center justify-center gap-2 rounded-lg border border-dashed py-8 text-center transition-colors hover:bg-muted/40">
              <HugeiconsIcon icon={Upload01Icon} className="text-muted-foreground size-8" />
              <span className="text-sm">{t("upload.dragHint")}</span>
              <input
                type="file"
                multiple
                className="hidden"
                onChange={(e) => handleFiles(e.target.files)}
              />
            </label>

            {files.length > 0 && (
              <ul className="space-y-1">
                {files.map((f, i) => (
                  <li key={i} className="text-muted-foreground truncate text-xs">
                    {f.name} ({f.size} B)
                  </li>
                ))}
              </ul>
            )}

            <Button onClick={handleUpload} disabled={busy || files.length === 0} className="w-full">
              {busy ? t("upload.uploading") : t("upload.upload")}
            </Button>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <HugeiconsIcon icon={FileImportIcon} className="text-muted-foreground size-4" />
              {t("upload.filePath")}
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-1.5">
                <Label>{t("upload.dataType")}</Label>
                <Select value={dataType} onValueChange={(v) => setDataType(v as string)}>
                  <SelectTrigger className="w-full">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {DATA_TYPES.map((dt) => (
                      <SelectItem key={dt.value} value={dt.value}>
                        {t(dt.labelKey)}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <div className="space-y-1.5">
                <Label>{t("upload.sourceName")}</Label>
                <Input value={sourceName} onChange={(e) => setSourceName(e.target.value)} />
              </div>
            </div>
            <div className="space-y-1.5">
              <Label>{t("upload.filePath")}</Label>
              <Input
                value={filePath}
                onChange={(e) => setFilePath(e.target.value)}
                placeholder="/data/raw/example.csv"
              />
            </div>
            <Button onClick={handleImport} disabled={busy || !filePath} className="w-full">
              {busy ? t("upload.uploading") : t("upload.upload")}
            </Button>
          </CardContent>
        </Card>
      </div>

      {message && (
        <p className="text-muted-foreground rounded-lg border px-3 py-2 text-sm">{message}</p>
      )}

      <Card>
        <CardHeader>
          <CardTitle>{t("upload.importHistory")}</CardTitle>
        </CardHeader>
        <CardContent>
          {history.loading ? (
            <LoadingState rows={3} />
          ) : history.error ? (
            <ErrorState message={history.error} onRetry={history.reload} />
          ) : imports.length === 0 ? (
            <p className="text-muted-foreground text-sm">{t("common.noData")}</p>
          ) : (
            <ul className="space-y-2">
              {imports.slice(0, 20).map((row, i) => (
                <li
                  key={i}
                  className="flex items-center justify-between gap-3 rounded-md border px-3 py-2 text-sm"
                >
                  <span className="min-w-0 truncate">
                    {String(row.source_name ?? row.data_type ?? "—")}
                  </span>
                  <span className="flex shrink-0 items-center gap-2">
                    <Badge variant="outline">{String(row.status ?? "")}</Badge>
                    <span className="text-muted-foreground text-xs">
                      {formatDateTime(row.created_at)}
                    </span>
                  </span>
                </li>
              ))}
            </ul>
          )}
        </CardContent>
      </Card>
    </AppShell>
  );
}
