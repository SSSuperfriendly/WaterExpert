"use client";

import * as React from "react";
import { useT } from "@/lib/i18n/use-t";
import { useApi } from "@/lib/hooks/use-api";
import { endpoints } from "@/lib/api/endpoints";
import {
  describeApiError,
  translateDataType,
  translateDatasetStatus,
  translateQualityGrade,
  translateStage,
} from "@/lib/domain";
import { formatDateTime } from "@/lib/format";
import { LoadingState, ErrorState } from "@/components/waterexpert/ui-states";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import type { Dataset } from "@/lib/api/contracts";

/** A→D. Only A and B may feed a prediction run. */
function gradeBadge(t: ReturnType<typeof useT>["t"], grade?: string) {
  if (!grade) return null;
  const variant =
    grade === "a" ? "secondary" : grade === "b" ? "outline" : "destructive";
  return <Badge variant={variant}>{translateQualityGrade(t, grade)}</Badge>;
}

/**
 * The governance half of the data asset centre: the dataset list with its
 * versions, each version's quality report and row preview, and the archive /
 * delete actions. UploadPanel owns the ingest half; this owns everything a
 * user does *after* a file was accepted.
 */
export function DatasetAssetTable({
  rows,
  loading,
  error,
  onReload,
}: {
  rows: Dataset[];
  loading: boolean;
  error: unknown;
  onReload: () => void;
}) {
  const { t } = useT();
  const [expandedId, setExpandedId] = React.useState<string | null>(null);
  const [busyId, setBusyId] = React.useState<string | null>(null);
  const [actionError, setActionError] = React.useState<string | null>(null);

  const archive = async (dataset: Dataset) => {
    if (!window.confirm(t("upload.confirmArchive"))) return;
    setBusyId(dataset.dataset_id);
    setActionError(null);
    try {
      await endpoints.archiveDataset(dataset.dataset_id);
      onReload();
    } catch (err) {
      setActionError(describeApiError(t, err));
    } finally {
      setBusyId(null);
    }
  };

  const remove = async (dataset: Dataset) => {
    if (!window.confirm(t("upload.confirmDelete"))) return;
    setBusyId(dataset.dataset_id);
    setActionError(null);
    try {
      await endpoints.deleteDataset(dataset.dataset_id);
      onReload();
    } catch (err) {
      setActionError(describeApiError(t, err));
    } finally {
      setBusyId(null);
    }
  };

  if (loading) return <LoadingState rows={3} />;
  if (error) return <ErrorState error={error} onRetry={onReload} />;
  if (rows.length === 0) {
    return <p className="text-muted-foreground text-sm">{t("common.noData")}</p>;
  }

  return (
    <div className="space-y-3">
      {actionError && <p className="text-destructive text-xs">{actionError}</p>}
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
              <TableHead>{t("common.actions")}</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {rows.map((dataset) => (
              <React.Fragment key={dataset.dataset_id}>
                <TableRow>
                  <TableCell className="max-w-[16rem] truncate">
                    {dataset.title ?? dataset.dataset_id}
                  </TableCell>
                  <TableCell>{translateDataType(t, dataset.data_type)}</TableCell>
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
                  <TableCell>
                    <div className="flex flex-wrap gap-2">
                      <Button
                        variant="outline"
                        size="sm"
                        onClick={() =>
                          setExpandedId(
                            expandedId === dataset.dataset_id ? null : dataset.dataset_id
                          )
                        }
                      >
                        {expandedId === dataset.dataset_id
                          ? t("upload.close")
                          : t("upload.manage")}
                      </Button>
                      <Button
                        variant="ghost"
                        size="sm"
                        disabled={busyId === dataset.dataset_id}
                        onClick={() => archive(dataset)}
                      >
                        {t("upload.archive")}
                      </Button>
                      <Button
                        variant="ghost"
                        size="sm"
                        disabled={busyId === dataset.dataset_id}
                        onClick={() => remove(dataset)}
                      >
                        {t("upload.delete")}
                      </Button>
                    </div>
                  </TableCell>
                </TableRow>
                {expandedId === dataset.dataset_id && (
                  <TableRow>
                    <TableCell colSpan={7} className="bg-muted/30">
                      <DatasetVersions datasetId={dataset.dataset_id} />
                    </TableCell>
                  </TableRow>
                )}
              </React.Fragment>
            ))}
          </TableBody>
        </Table>
      </div>
    </div>
  );
}

function DatasetVersions({ datasetId }: { datasetId: string }) {
  const { t } = useT();
  const versions = useApi(() => endpoints.datasetVersions(datasetId), [datasetId]);
  const [selectedVersion, setSelectedVersion] = React.useState<string | null>(null);

  return (
    <div className="space-y-3 py-2">
      <p className="text-xs font-medium">{t("upload.versions")}</p>
      {versions.loading ? (
        <LoadingState rows={2} />
      ) : versions.error ? (
        <ErrorState error={versions.error} onRetry={versions.reload} />
      ) : (versions.data ?? []).length === 0 ? (
        <p className="text-muted-foreground text-xs">{t("upload.noVersions")}</p>
      ) : (
        <div className="overflow-x-auto">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>{t("upload.version")}</TableHead>
                <TableHead>{t("upload.stage")}</TableHead>
                <TableHead>{t("upload.quality")}</TableHead>
                <TableHead>{t("upload.modelableRows")}</TableHead>
                <TableHead>{t("upload.rowCount")}</TableHead>
                <TableHead>{t("prediction.createdAt")}</TableHead>
                <TableHead>{t("common.actions")}</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {(versions.data ?? []).map((version) => (
                <TableRow key={version.version_id}>
                  <TableCell className="font-mono text-xs">{version.version}</TableCell>
                  <TableCell className="text-xs">
                    {translateStage(t, version.blocked_at ?? version.stage)}
                  </TableCell>
                  <TableCell>{gradeBadge(t, version.quality_grade)}</TableCell>
                  <TableCell className="text-xs">{version.modelable_rows ?? "—"}</TableCell>
                  <TableCell className="text-xs">{version.row_count ?? "—"}</TableCell>
                  <TableCell className="text-xs">
                    {formatDateTime(version.created_at)}
                  </TableCell>
                  <TableCell>
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={() =>
                        setSelectedVersion(
                          selectedVersion === version.version_id ? null : version.version_id
                        )
                      }
                    >
                      {selectedVersion === version.version_id
                        ? t("upload.close")
                        : t("upload.preview")}
                    </Button>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      )}
      {selectedVersion && <VersionDetail versionId={selectedVersion} />}
    </div>
  );
}

function VersionDetail({ versionId }: { versionId: string }) {
  const { t } = useT();
  const preview = useApi(() => endpoints.datasetPreview(versionId, 20), [versionId]);
  const quality = useApi(() => endpoints.datasetQuality(versionId), [versionId]);
  const columns = preview.data?.columns ?? [];

  return (
    <div className="space-y-3 rounded-md border p-3">
      <div>
        <p className="text-xs font-medium">{t("upload.qualityReport")}</p>
        {quality.loading ? (
          <LoadingState rows={1} />
        ) : quality.error ? (
          <ErrorState error={quality.error} onRetry={quality.reload} />
        ) : quality.data ? (
          <div className="mt-1 flex flex-wrap gap-3 text-xs">
            <span>
              {t("upload.stage")}: {translateStage(t, quality.data.final_stage)}
            </span>
            <span>
              {t("upload.missingRate")}: {quality.data.missing_rate ?? "—"}
            </span>
            <span>
              {t("upload.modelableRows")}: {quality.data.modelable_rows ?? "—"}
            </span>
          </div>
        ) : null}
      </div>
      <div>
        <p className="text-xs font-medium">{t("upload.preview")}</p>
        {preview.loading ? (
          <LoadingState rows={2} />
        ) : preview.error ? (
          <ErrorState error={preview.error} onRetry={preview.reload} />
        ) : preview.data && !preview.data.available ? (
          <p className="text-muted-foreground text-xs">{t("upload.previewUnavailable")}</p>
        ) : preview.data?.rows?.length ? (
          <div className="overflow-x-auto">
            <Table>
              <TableHeader>
                <TableRow>
                  {columns.map((column) => (
                    <TableHead key={column}>{column}</TableHead>
                  ))}
                </TableRow>
              </TableHeader>
              <TableBody>
                {preview.data.rows.map((row, index) => (
                  <TableRow key={index}>
                    {columns.map((column) => (
                      <TableCell key={column} className="text-xs">
                        {String(row[column] ?? "")}
                      </TableCell>
                    ))}
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        ) : (
          <p className="text-muted-foreground text-xs">{t("common.noData")}</p>
        )}
      </div>
    </div>
  );
}
