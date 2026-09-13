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
import { ConfirmDialog } from "@/components/waterexpert/confirm-dialog";
import { Modal } from "@/components/waterexpert/modal";
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
import type { Dataset, DatasetLineage, FieldDictionary } from "@/lib/api/contracts";

/** A→D. Only A and B may feed a prediction run. */
function gradeBadge(t: ReturnType<typeof useT>["t"], grade?: string) {
  if (!grade) return null;
  const variant =
    grade === "a" ? "secondary" : grade === "b" ? "outline" : "destructive";
  return <Badge variant={variant}>{translateQualityGrade(t, grade)}</Badge>;
}

/**
 * The governance half of the data asset centre: the dataset list with its
 * versions, each version's quality report, row preview, lineage and field
 * dictionary, plus archive/delete. UploadPanel owns the ingest half; this owns
 * everything a user does *after* a file was accepted.
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
  const [pendingConfirm, setPendingConfirm] = React.useState<{
    dataset: Dataset;
    kind: "archive" | "delete";
  } | null>(null);
  const [fieldDictionaryType, setFieldDictionaryType] = React.useState<string | null>(null);

  const confirmPending = async () => {
    if (!pendingConfirm) return;
    const { dataset, kind } = pendingConfirm;
    setBusyId(dataset.dataset_id);
    setActionError(null);
    try {
      if (kind === "archive") {
        await endpoints.archiveDataset(dataset.dataset_id);
      } else {
        await endpoints.deleteDataset(dataset.dataset_id);
      }
      setPendingConfirm(null);
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
                        onClick={() => setFieldDictionaryType(dataset.data_type)}
                      >
                        {t("datasetDetail.fieldDictionary")}
                      </Button>
                      <Button
                        variant="ghost"
                        size="sm"
                        disabled={busyId === dataset.dataset_id}
                        onClick={() => setPendingConfirm({ dataset, kind: "archive" })}
                      >
                        {t("upload.archive")}
                      </Button>
                      <Button
                        variant="ghost"
                        size="sm"
                        disabled={busyId === dataset.dataset_id}
                        onClick={() => setPendingConfirm({ dataset, kind: "delete" })}
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

      <ConfirmDialog
        open={pendingConfirm !== null}
        title={
          pendingConfirm?.kind === "delete"
            ? t("upload.delete")
            : t("upload.archive")
        }
        message={
          pendingConfirm?.kind === "delete"
            ? t("upload.confirmDelete")
            : t("upload.confirmArchive")
        }
        confirmLabel={
          pendingConfirm?.kind === "delete"
            ? t("upload.delete")
            : t("upload.archive")
        }
        destructive={pendingConfirm?.kind === "delete"}
        busy={busyId !== null}
        onConfirm={confirmPending}
        onCancel={() => setPendingConfirm(null)}
      />

      <FieldDictionaryModal
        dataType={fieldDictionaryType}
        onClose={() => setFieldDictionaryType(null)}
      />
    </div>
  );
}

function DatasetVersions({ datasetId }: { datasetId: string }) {
  const { t } = useT();
  const versions = useApi(() => endpoints.datasetVersions(datasetId), [datasetId]);
  const [selectedVersion, setSelectedVersion] = React.useState<string | null>(null);
  const [lineageVersionId, setLineageVersionId] = React.useState<string | null>(null);

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
                    <div className="flex flex-wrap gap-2">
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
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={() => setLineageVersionId(version.version_id)}
                      >
                        {t("datasetDetail.lineage")}
                      </Button>
                    </div>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      )}
      {selectedVersion && <VersionDetail versionId={selectedVersion} />}

      <LineageModal
        versionId={lineageVersionId}
        onClose={() => setLineageVersionId(null)}
      />
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

function FieldDictionaryModal({
  dataType,
  onClose,
}: {
  dataType: string | null;
  onClose: () => void;
}) {
  const { t } = useT();
  const dictionary = useApi<FieldDictionary | null>(
    () => (dataType ? endpoints.datasetFieldDictionary(dataType) : Promise.resolve(null)),
    [dataType]
  );
  const fields = dictionary.data?.fields ?? [];

  return (
    <Modal
      open={dataType !== null}
      title={t("datasetDetail.fieldDictionary")}
      onClose={onClose}
      size="lg"
    >
      {dictionary.loading ? (
        <LoadingState rows={3} />
      ) : dictionary.error ? (
        <ErrorState error={dictionary.error} onRetry={dictionary.reload} />
      ) : dictionary.data ? (
        <div className="space-y-2">
          <p className="text-muted-foreground text-xs">
            {dictionary.data.label ?? dictionary.data.data_type}
            {dictionary.data.granularity ? ` · ${dictionary.data.granularity}` : ""}
          </p>
          <div className="overflow-x-auto">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>{t("datasetDetail.field")}</TableHead>
                  <TableHead>{t("datasetDetail.kind")}</TableHead>
                  <TableHead>{t("datasetDetail.unit")}</TableHead>
                  <TableHead>{t("datasetDetail.required")}</TableHead>
                  <TableHead>{t("datasetDetail.aliases")}</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {fields.map((field) => (
                  <TableRow key={field.canonical}>
                    <TableCell className="text-xs font-medium">
                      {field.label ?? field.canonical}
                    </TableCell>
                    <TableCell className="text-xs">{field.kind ?? "—"}</TableCell>
                    <TableCell className="text-xs">{field.unit ?? "—"}</TableCell>
                    <TableCell className="text-xs">
                      {field.required ? t("datasetDetail.yes") : "—"}
                    </TableCell>
                    <TableCell className="max-w-[18rem] truncate text-xs">
                      {(field.aliases ?? []).slice(0, 4).join("、") || "—"}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        </div>
      ) : null}
    </Modal>
  );
}

function LineageModal({
  versionId,
  onClose,
}: {
  versionId: string | null;
  onClose: () => void;
}) {
  const { t } = useT();
  const lineage = useApi<DatasetLineage | null>(
    () => (versionId ? endpoints.datasetLineage(versionId) : Promise.resolve(null)),
    [versionId]
  );
  const data = lineage.data;

  return (
    <Modal
      open={versionId !== null}
      title={t("datasetDetail.lineage")}
      onClose={onClose}
      size="md"
    >
      {lineage.loading ? (
        <LoadingState rows={3} />
      ) : lineage.error ? (
        <ErrorState error={lineage.error} onRetry={lineage.reload} />
      ) : data ? (
        <dl className="space-y-2 text-xs">
          <LineageRow label={t("datasetDetail.source")} value={data.source_name ?? "—"} />
          <LineageRow label={t("datasetDetail.sourceKind")} value={data.source_kind ?? "—"} />
          <LineageRow label={t("datasetDetail.sha256")} value={data.source_sha256 ?? "—"} mono />
          <LineageRow
            label={t("datasetDetail.createdAt")}
            value={data.created_at ? formatDateTime(data.created_at) : "—"}
          />
          <LineageRow label={t("datasetDetail.createdBy")} value={data.created_by ?? "—"} />
          <LineageRow
            label={t("datasetDetail.usedByCases")}
            value={(data.used_by_cases ?? []).join("、") || "—"}
            mono
          />
        </dl>
      ) : null}
    </Modal>
  );
}

function LineageRow({
  label,
  value,
  mono = false,
}: {
  label: string;
  value: string;
  mono?: boolean;
}) {
  return (
    <div className="flex items-start justify-between gap-4">
      <dt className="text-muted-foreground shrink-0">{label}</dt>
      <dd className={`min-w-0 text-right ${mono ? "font-mono" : ""}`}>{value}</dd>
    </div>
  );
}
