"use client";

import * as React from "react";
import { useT } from "@/lib/i18n/use-t";
import { useApi } from "@/lib/hooks/use-api";
import { endpoints } from "@/lib/api/endpoints";
import { formatDateTime, formatNumber } from "@/lib/format";
import { AppShell } from "@/components/waterexpert/app-shell";
import { LoadingState, ErrorState } from "@/components/waterexpert/ui-states";
import { StatCard } from "@/components/waterexpert/stat-card";
import { AuthenticatedMedia } from "@/components/waterexpert/authenticated-media";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import type { CrossModalAsset } from "@/lib/api/contracts";

interface EvaluationTarget {
  best_display_name?: string;
  best_rmse?: number;
  baseline_rmse?: number;
  sample_count?: number;
  cv_strategy?: string;
}

const EMPTY_ROWS: Record<string, unknown>[] = [];

//: Columns the fused daily table shows by default. A presentation subset — the
//: full row still lives in the artifact — filtered to the ones this deployment's
//: data actually carries, so the table stays within the page width.
const PREFERRED_DAILY_COLUMNS = [
  "sample_date",
  "sample_site_role",
  "fusion_readiness",
  "turbidity_ntu",
  "secchi_depth_m",
  "uav_asset_count",
  "uav_turbidity_visual_proxy_mean",
  "historical_proxy_weather_precipitation_median",
];

/**
 * The Zhangjiabang cross-modal satellite view.
 *
 * It renders whatever the processed artifacts carry — asset metadata, the
 * representative frames a video was sliced into, the fused daily table and the
 * model comparison — so it is a view over the data layer, not a re-implementation
 * of it. Every image is fetched through the authenticated media endpoint.
 */
export default function CrossModalPage() {
  const { t } = useT();
  const { data, loading, error, reload } = useApi(() => endpoints.crossModal());

  const assets = data?.preview_assets ?? [];
  const dailyRows = data?.daily_rows ?? EMPTY_ROWS;
  const dailyColumns = React.useMemo(() => {
    const all = Object.keys(dailyRows[0] ?? {});
    const preferred = PREFERRED_DAILY_COLUMNS.filter((column) => all.includes(column));
    return preferred.length > 0 ? preferred : all.slice(0, 8);
  }, [dailyRows]);
  const targets = (data?.model_evaluation?.targets ?? {}) as Record<
    string,
    EvaluationTarget
  >;
  const counts = data?.counts ?? {};

  return (
    <AppShell title={t("crossModal.title")}>
      {loading ? (
        <LoadingState />
      ) : error ? (
        <ErrorState error={error} onRetry={reload} />
      ) : !data ? null : (
        <div className="flex flex-col gap-6">
          <p className="text-muted-foreground text-sm">
            {data.site ? `${t("crossModal.site")}: ${data.site} · ` : ""}
            {data.generated_at
              ? `${t("crossModal.generatedAt")}: ${formatDateTime(data.generated_at)}`
              : ""}
          </p>

          <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
            <StatCard
              label={t("crossModal.assets")}
              value={String(counts.uav_assets ?? assets.length)}
            />
            <StatCard label={t("crossModal.images")} value={String(counts.uav_images ?? "—")} />
            <StatCard label={t("crossModal.videos")} value={String(counts.uav_videos ?? "—")} />
            <StatCard
              label={t("crossModal.supervisedRows")}
              value={String(counts.supervised_cross_modal_rows ?? "—")}
            />
          </div>

          {data.modality_status && Object.keys(data.modality_status).length > 0 && (
            <Card>
              <CardHeader>
                <CardTitle>{t("crossModal.modalityStatus")}</CardTitle>
              </CardHeader>
              <CardContent className="flex flex-wrap gap-2">
                {Object.entries(data.modality_status).map(([modality, status]) => (
                  <Badge key={modality} variant="outline" className="gap-1 font-normal">
                    {modality}: {status}
                  </Badge>
                ))}
              </CardContent>
            </Card>
          )}

          <div>
            <h2 className="mb-3 text-sm font-medium">{t("crossModal.assetGallery")}</h2>
            <div className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-3">
              {assets.map((asset) => (
                <AssetCard key={asset.asset_id ?? asset.file_name} asset={asset} />
              ))}
            </div>
          </div>

          {dailyRows.length > 0 && (
            <Card>
              <CardHeader>
                <CardTitle>{t("crossModal.fusedDaily")}</CardTitle>
                <p className="text-muted-foreground text-xs">{t("crossModal.fusedDailyHint")}</p>
              </CardHeader>
              <CardContent>
                <div className="overflow-x-auto">
                  <Table>
                    <TableHeader>
                      <TableRow>
                        {dailyColumns.map((column) => (
                          <TableHead key={column}>{column}</TableHead>
                        ))}
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {dailyRows.map((row, index) => (
                        <TableRow key={index}>
                          {dailyColumns.map((column) => (
                            <TableCell key={column} className="text-xs whitespace-nowrap">
                              {row[column] === null || row[column] === undefined
                                ? "—"
                                : String(row[column])}
                            </TableCell>
                          ))}
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                </div>
              </CardContent>
            </Card>
          )}

          {Object.keys(targets).length > 0 && (
            <Card>
              <CardHeader>
                <CardTitle>{t("crossModal.modelEvaluation")}</CardTitle>
              </CardHeader>
              <CardContent>
                <div className="overflow-x-auto">
                  <Table>
                    <TableHeader>
                      <TableRow>
                        <TableHead>{t("crossModal.target")}</TableHead>
                        <TableHead>{t("crossModal.bestModel")}</TableHead>
                        <TableHead>{t("crossModal.bestRmse")}</TableHead>
                        <TableHead>{t("crossModal.baselineRmse")}</TableHead>
                        <TableHead>{t("crossModal.improvement")}</TableHead>
                        <TableHead>{t("crossModal.sampleCount")}</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {Object.entries(targets).map(([target, evaluation]) => {
                        const best = evaluation.best_rmse;
                        const baseline = evaluation.baseline_rmse;
                        const improvement =
                          best !== undefined && baseline !== undefined && baseline > 0
                            ? (baseline - best) / baseline
                            : null;
                        return (
                          <TableRow key={target}>
                            <TableCell className="text-xs">{target}</TableCell>
                            <TableCell className="text-xs">
                              {evaluation.best_display_name ?? "—"}
                            </TableCell>
                            <TableCell className="font-mono text-xs">
                              {formatNumber(best, 4)}
                            </TableCell>
                            <TableCell className="font-mono text-xs">
                              {formatNumber(baseline, 4)}
                            </TableCell>
                            <TableCell className="text-xs">
                              {improvement === null
                                ? "—"
                                : `${(improvement * 100).toFixed(1)}%`}
                            </TableCell>
                            <TableCell className="text-xs">
                              {evaluation.sample_count ?? "—"}
                            </TableCell>
                          </TableRow>
                        );
                      })}
                    </TableBody>
                  </Table>
                </div>
              </CardContent>
            </Card>
          )}
        </div>
      )}
    </AppShell>
  );
}

function AssetCard({ asset }: { asset: CrossModalAsset }) {
  const { t } = useT();
  const isVideo = asset.media_type === "video";
  const frames = asset.representative_frames ?? [];
  const metrics: Array<[string, unknown]> = [
    [t("crossModal.turbidityProxy"), asset.turbidity_visual_proxy],
    [t("crossModal.sharpness"), asset.sharpness_laplacian],
    [t("crossModal.embeddingNorm"), asset.visual_transformer_embedding_norm],
  ];

  return (
    <Card className="overflow-hidden">
      <div className="bg-muted relative aspect-video w-full overflow-hidden">
        {asset.preview_url ? (
          <AuthenticatedMedia
            path={asset.preview_url}
            alt={asset.file_name ?? asset.asset_id ?? "uav asset"}
            className="h-full w-full object-cover"
            fallbackLabel={t("crossModal.mediaUnavailable")}
          />
        ) : null}
        <Badge className="absolute top-2 left-2" variant={isVideo ? "default" : "secondary"}>
          {isVideo ? t("crossModal.video") : t("crossModal.image")}
        </Badge>
      </div>
      <CardContent className="space-y-2 pt-3">
        <div className="flex items-center justify-between gap-2">
          <span className="truncate text-sm font-medium">{asset.file_name ?? asset.asset_id}</span>
          <span className="text-muted-foreground shrink-0 text-xs">{asset.sample_date}</span>
        </div>

        {isVideo && frames.length > 0 && (
          <div>
            <p className="text-muted-foreground mb-1 text-xs">
              {t("crossModal.slicedFrames", { count: String(frames.length) })}
            </p>
            <div className="flex gap-1 overflow-x-auto pb-1">
              {frames.map((frame, index) => (
                <AuthenticatedMedia
                  key={frame}
                  path={frame}
                  alt={`${asset.file_name ?? "video"} frame ${index + 1}`}
                  className="h-12 w-20 shrink-0 rounded object-cover"
                  fallbackLabel="—"
                />
              ))}
            </div>
          </div>
        )}

        {isVideo && (
          <p className="text-muted-foreground text-xs">
            {asset.frame_count !== undefined && asset.frame_count !== null
              ? `${t("crossModal.frameCount")}: ${asset.frame_count} · `
              : ""}
            {asset.fps ? `${asset.fps} fps · ` : ""}
            {asset.duration_seconds
              ? `${formatNumber(asset.duration_seconds, 1)}s`
              : ""}
          </p>
        )}

        <div className="grid grid-cols-3 gap-2">
          {metrics.map(([label, value]) => (
            <div key={label}>
              <p className="text-muted-foreground truncate text-[10px]">{label}</p>
              <p className="font-mono text-xs">{formatNumber(value, 3)}</p>
            </div>
          ))}
        </div>
      </CardContent>
    </Card>
  );
}
