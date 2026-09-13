"use client";

import * as React from "react";
import { useT } from "@/lib/i18n/use-t";
import { useApi } from "@/lib/hooks/use-api";
import { endpoints } from "@/lib/api/endpoints";
import { describeApiError, translateBlockingReason, translateStage } from "@/lib/domain";
import { DatasetAssetTable } from "@/components/waterexpert/dataset-asset-table";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
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
          <DatasetAssetTable
            rows={rows}
            loading={datasets.loading}
            error={datasets.error}
            onReload={datasets.reload}
          />
        </CardContent>
      </Card>
    </div>
  );
}
