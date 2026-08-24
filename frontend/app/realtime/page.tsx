"use client";

import { useT } from "@/lib/i18n/use-t";
import { useApi } from "@/lib/hooks/use-api";
import { endpoints } from "@/lib/api/endpoints";
import { AppShell } from "@/components/waterexpert/app-shell";
import { PageHeading, LoadingState, ErrorState, EmptyState } from "@/components/waterexpert/ui-states";
import { GuardrailBanner } from "@/components/waterexpert/guardrail-banner";
import { StatCard } from "@/components/waterexpert/stat-card";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { RefreshIcon } from "@hugeicons/core-free-icons";

export default function RealtimePage() {
  const { t } = useT();
  const { data, loading, error, reload } = useApi(() => endpoints.realtimeValidation());

  const payload = (data?.payload ?? {}) as Record<string, unknown>;
  const summary = (payload.summary_metrics ?? {}) as Record<string, unknown>;
  const caveats = (payload.caveats ?? []) as string[];

  return (
    <AppShell title={t("nav.realtime")}>
      <PageHeading title={t("realtime.title")} subtitle={t("realtime.subtitle")} />

      {loading ? (
        <LoadingState />
      ) : error ? (
        <ErrorState message={error} onRetry={reload} />
      ) : data ? (
        <>
          {data.status === "missing" ? (
            <EmptyState title={t("realtime.missing")} />
          ) : data.status === "error" ? (
            <ErrorState message={t("realtime.error")} onRetry={reload} />
          ) : (
            <>
              <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
                <StatCard
                  label={String(summary.prediction_success_rate_label ?? t("realtime.predictionSuccessRate"))}
                  value={String(summary.prediction_success_rate_title ?? "—")}
                  icon={RefreshIcon}
                />
                <StatCard
                  label={t("realtime.historicalSimilarDay")}
                  value={String(summary.historical_similar_day ?? "—")}
                />
              </div>

              {(summary.prediction_success_rate_note || summary.historical_similar_day_note) && (
                <Card>
                  <CardHeader>
                    <CardTitle>{t("realtime.summaryMetrics")}</CardTitle>
                  </CardHeader>
                  <CardContent className="space-y-2">
                    {typeof summary.prediction_success_rate_note === "string" &&
                      summary.prediction_success_rate_note && (
                        <p className="text-muted-foreground text-sm leading-snug">
                          {summary.prediction_success_rate_note}
                        </p>
                      )}
                    {typeof summary.historical_similar_day_note === "string" &&
                      summary.historical_similar_day_note && (
                        <p className="text-muted-foreground text-sm leading-snug">
                          {summary.historical_similar_day_note}
                        </p>
                      )}
                  </CardContent>
                </Card>
              )}

              {caveats.length > 0 && <GuardrailBanner items={caveats} />}
            </>
          )}
        </>
      ) : null}
    </AppShell>
  );
}
