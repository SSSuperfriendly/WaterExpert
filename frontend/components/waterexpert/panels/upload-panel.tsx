"use client";

import * as React from "react";
import { useT } from "@/lib/i18n/use-t";
import { useApi } from "@/lib/hooks/use-api";
import { endpoints } from "@/lib/api/endpoints";
import { formatDateTime } from "@/lib/format";
import {
  describeApiError,
  translateBlockingReason,
  translateDataType,
  translateDatasetStatus,
  translateQualityGrade,
  translateStage,
} from "@/lib/domain";
import { LoadingState, ErrorState } from "@/components/waterexpert/ui-states";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { HugeiconsIcon } from "@hugeicons/react";
import { Upload01Icon, FileImportIcon } from "@hugeicons/core-free-icons";
import type { DatasetVersion } from "@/lib/api/contracts";

const DATA_TYPES = [
  { value: "water_quality", labelKey: "upload.waterQuality" },
  { value: "weather", labelKey: "upload.weather" },
  { value: "hydrodynamics", labelKey: "upload.hydrodynamics" },
  { value: "water_control", labelKey: "upload.waterControl" },
  { value: "boundary_labels", labelKey: "upload.boundaryLabels" },
  { value: "spatial", labelKey: "upload.spatial" },
];

/** A→D. Only A and B may feed a prediction run. */
function gradeBadge(t: ReturnType<typeof useT>["t"], grade?: string) {
  if (!grade) return null;
  const variant =
    grade === "a" ? "secondary" : grade === "b" ? "outline" : "destructive";
  return <Badge variant={variant}>{translateQualityGrade(t, grade)}</Badge>;
}

export function UploadPanel() {
  const { t } = useT();
  const datasets = useApi(() => endpoints.datasets());

  const [dataType, setDataType] = React.useState("water_quality");
  const [stationCode, setStationCode] = React.useState("2586");
  const [relativePath, setRelativePath] = React.useState("");
  const [file, setFile] = React.useState<File | null>(null);
  const [busy, setBusy] = React.useState(false);
  const [message, setMessage] = React.useState<string | null>(null);
  const [result, setResult] = React.useState<DatasetVersion | null>(null);

  /**
   * Both entry points run the same acceptance chain, so they report the same
   * way: the resulting version, its grade, and — when it was refused — the
   * stage that stopped it. "Uploaded" is no longer the same as "usable".
   */
  const submit = async (run: () => Promise<DatasetVersion>) => {
    setBusy(true);
    setMessage(null);
    setResult(null);
    try {
      const version = await run();
      setResult(version);
      setMessage(
        version.status === "accepted"
          ? t("upload.acceptedWithRows", {
              rows: String(version.modelable_rows ?? version.row_count ?? 0),
            })
          : t("upload.rejectedAtStage", {
              stage: translateStage(t, version.blocked_at ?? version.stage),
            })
      );
      setFile(null);
      datasets.reload();
    } catch (err) {
      setMessage(describeApiError(t, err));
    } finally {
      setBusy(false);
    }
  };

  const handleUpload = () => {
    if (!file) return;
    const formData = new FormData();
    formData.set("data_type", dataType);
    formData.set("station_code", stationCode);
    formData.set("file", file);
    return submit(() => endpoints.uploadDataset(formData));
  };

  const handleImport = () =>
    submit(() =>
      endpoints.importDataset({
        data_type: dataType,
        relative_path: relativePath,
        station_code: stationCode,
      })
    );

  const rows = datasets.data ?? [];

  return (
    <div className="flex flex-col gap-6">
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
                <Label>{t("upload.stationCode")}</Label>
                <Input
                  value={stationCode}
                  onChange={(e) => setStationCode(e.target.value)}
                />
              </div>
            </div>

            <label className="flex cursor-pointer flex-col items-center justify-center gap-2 rounded-lg border border-dashed py-8 text-center transition-colors hover:bg-muted/40">
              <HugeiconsIcon icon={Upload01Icon} className="text-muted-foreground size-8" />
              <span className="text-sm">{t("upload.dragHint")}</span>
              <input
                type="file"
                className="hidden"
                accept=".csv,.xls,.xlsx,.json"
                onChange={(e) => setFile(e.target.files?.[0] ?? null)}
              />
            </label>

            {file && (
              <p className="text-muted-foreground truncate text-xs">
                {file.name} ({file.size} B)
              </p>
            )}

            <Button onClick={handleUpload} disabled={busy || !file} className="w-full">
              {busy ? t("upload.uploading") : t("upload.upload")}
            </Button>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <HugeiconsIcon icon={FileImportIcon} className="text-muted-foreground size-4" />
              {t("upload.managedImport")}
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="space-y-1.5">
              <Label>{t("upload.relativePath")}</Label>
              <Input
                value={relativePath}
                onChange={(e) => setRelativePath(e.target.value)}
                placeholder="wusongkou_water_quality_2586.csv"
              />
              <p className="text-muted-foreground text-xs">{t("upload.managedImportHint")}</p>
            </div>
            <Button
              onClick={handleImport}
              disabled={busy || !relativePath}
              className="w-full"
            >
              {busy ? t("upload.uploading") : t("upload.import")}
            </Button>
          </CardContent>
        </Card>
      </div>

      {message && (
        <div className="rounded-lg border px-3 py-2 text-sm">
          <p>{message}</p>
          {result?.blocking_reasons?.length ? (
            <ul className="text-muted-foreground mt-1 list-disc pl-5 text-xs">
              {result.blocking_reasons.map((reason) => (
                <li key={reason}>{translateBlockingReason(t, reason)}</li>
              ))}
            </ul>
          ) : null}
        </div>
      )}

      <Card>
        <CardHeader>
          <CardTitle>{t("upload.datasetList")}</CardTitle>
        </CardHeader>
        <CardContent>
          {datasets.loading ? (
            <LoadingState rows={3} />
          ) : datasets.error ? (
            <ErrorState error={datasets.error} onRetry={datasets.reload} />
          ) : rows.length === 0 ? (
            <p className="text-muted-foreground text-sm">{t("common.noData")}</p>
          ) : (
            <div className="overflow-x-auto">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>{t("upload.dataset")}</TableHead>
                    <TableHead>{t("upload.dataType")}</TableHead>
                    <TableHead>{t("upload.coverage")}</TableHead>
                    <TableHead>{t("upload.quality")}</TableHead>
                    <TableHead>{t("common.status")}</TableHead>
                    <TableHead>{t("prediction.createdAt")}</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {rows.map((dataset) => (
                    <TableRow key={dataset.dataset_id}>
                      <TableCell className="max-w-[16rem] truncate">
                        {dataset.title ?? dataset.dataset_id}
                      </TableCell>
                      <TableCell>
                        {translateDataType(t, dataset.data_type)}
                      </TableCell>
                      <TableCell className="text-xs">
                        {dataset.coverage_start && dataset.coverage_end
                          ? `${dataset.coverage_start} → ${dataset.coverage_end}`
                          : "—"}
                      </TableCell>
                      <TableCell>{gradeBadge(t, dataset.quality_grade)}</TableCell>
                      <TableCell>
                        <Badge variant="outline">
                          {translateDatasetStatus(t, dataset.status)}
                        </Badge>
                      </TableCell>
                      <TableCell className="text-xs">
                        {formatDateTime(dataset.created_at)}
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
