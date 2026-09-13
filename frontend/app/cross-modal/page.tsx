"use client";

import { useT } from "@/lib/i18n/use-t";
import { useApi } from "@/lib/hooks/use-api";
import { endpoints } from "@/lib/api/endpoints";
import { formatDateTime, formatNumber } from "@/lib/format";
import { AppShell } from "@/components/waterexpert/app-shell";
import { LoadingState, ErrorState } from "@/components/waterexpert/ui-states";
import { StatCard } from "@/components/waterexpert/stat-card";
import { AuthenticatedMedia } from "@/components/waterexpert/authenticated-media";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import type { CrossModalAsset } from "@/lib/api/contracts";

function assetLabel(t: ReturnType<typeof useT>["t"], asset: CrossModalAsset): string {
  const kind = asset.media_type === "video" ? t("crossModal.video") : t("crossModal.image");
  const sequence = String(asset.sequence ?? 1).padStart(2, "0");
  return `${kind} #${sequence}`;
}

/**
 * The Zhangjiabang cross-modal satellite view.
 *
 * Images and videos are shown as separate collections. A video plays when its
 * source file is on disk (served through the authenticated media endpoint) and
 * otherwise falls back to the representative frames it was sliced into — the
 * raw UAV drop is gitignored, so frames are what this deployment usually has.
 * Assets are labelled by a stable date ordinal, never by the raw filename.
 */
export default function CrossModalPage() {
  const { t } = useT();
  const { data, loading, error, reload } = useApi(() => endpoints.crossModal());

  const assets = data?.preview_assets ?? [];
  const images = assets.filter((asset) => asset.media_type !== "video");
  const videos = assets.filter((asset) => asset.media_type === "video");
  const counts = data?.counts ?? {};

  return (
    <AppShell title={t("crossModal.title")}>
      {loading ? (
        <LoadingState />
      ) : error ? (
        <ErrorState error={error} onRetry={reload} />
      ) : !data ? null : (
        <div className="flex min-w-0 flex-col gap-6">
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
              <CardContent className="flex flex-wrap gap-2 pt-6">
                {Object.entries(data.modality_status).map(([modality, status]) => (
                  <Badge key={modality} variant="outline" className="gap-1 font-normal">
                    {modality}: {status}
                  </Badge>
                ))}
              </CardContent>
            </Card>
          )}

          <Tabs defaultValue="images">
            <TabsList>
              <TabsTrigger value="images">
                {t("crossModal.tabImages")} ({images.length})
              </TabsTrigger>
              <TabsTrigger value="videos">
                {t("crossModal.tabVideos")} ({videos.length})
              </TabsTrigger>
            </TabsList>
            <TabsContent value="images">
              <AssetGrid assets={images} />
            </TabsContent>
            <TabsContent value="videos">
              <AssetGrid assets={videos} />
            </TabsContent>
          </Tabs>
        </div>
      )}
    </AppShell>
  );
}

function AssetGrid({ assets }: { assets: CrossModalAsset[] }) {
  const { t } = useT();

  if (assets.length === 0) {
    return <p className="text-muted-foreground text-sm">{t("common.noData")}</p>;
  }

  return (
    <div className="grid min-w-0 grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-3">
      {assets.map((asset) => (
        <AssetCard key={asset.asset_id ?? asset.file_name} asset={asset} />
      ))}
    </div>
  );
}

function AssetCard({ asset }: { asset: CrossModalAsset }) {
  const { t } = useT();
  const isVideo = asset.media_type === "video";
  const frames = asset.representative_frames ?? [];
  const label = assetLabel(t, asset);
  const metrics: Array<[string, unknown]> = [
    [t("crossModal.turbidityProxy"), asset.turbidity_visual_proxy],
    [t("crossModal.sharpness"), asset.sharpness_laplacian],
  ];

  return (
    <Card className="min-w-0 overflow-hidden">
      <div className="bg-muted relative aspect-video w-full overflow-hidden">
        {isVideo && asset.video_url ? (
          <AuthenticatedMedia
            kind="video"
            path={asset.video_url}
            alt={label}
            className="h-full w-full object-contain"
            fallbackLabel={t("crossModal.mediaUnavailable")}
          />
        ) : asset.preview_url ? (
          <AuthenticatedMedia
            path={asset.preview_url}
            alt={label}
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
          <span className="truncate text-sm font-medium" title={asset.file_name ?? ""}>
            {label}
          </span>
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
                  alt={`${label} ${index + 1}`}
                  className="h-12 w-20 shrink-0 rounded object-cover"
                  fallbackLabel="—"
                />
              ))}
            </div>
            {!asset.video_url && (
              <p className="text-muted-foreground mt-1 text-[10px]">
                {t("crossModal.videoSourceUnavailable")}
              </p>
            )}
          </div>
        )}

        {isVideo && (
          <p className="text-muted-foreground text-xs">
            {asset.frame_count !== undefined && asset.frame_count !== null
              ? `${t("crossModal.frameCount")}: ${asset.frame_count} · `
              : ""}
            {asset.fps ? `${asset.fps} fps · ` : ""}
            {asset.duration_seconds ? `${formatNumber(asset.duration_seconds, 1)}s` : ""}
          </p>
        )}

        <div className="grid grid-cols-2 gap-2">
          {metrics.map(([metricLabel, value]) => (
            <div key={metricLabel}>
              <p className="text-muted-foreground truncate text-[10px]">{metricLabel}</p>
              <p className="font-mono text-xs">{formatNumber(value, 3)}</p>
            </div>
          ))}
        </div>
      </CardContent>
    </Card>
  );
}
