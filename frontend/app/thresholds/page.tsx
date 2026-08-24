"use client";

import { useT } from "@/lib/i18n/use-t";
import { useApi } from "@/lib/hooks/use-api";
import { endpoints } from "@/lib/api/endpoints";
import { formatNumber } from "@/lib/format";
import { AppShell } from "@/components/waterexpert/app-shell";
import { PageHeading, LoadingState, ErrorState } from "@/components/waterexpert/ui-states";
import { ThresholdBrowser } from "@/components/waterexpert/threshold-browser";
import { GuardrailBanner } from "@/components/waterexpert/guardrail-banner";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

export default function ThresholdsPage() {
  const { t } = useT();
  const { data, loading, error, reload } = useApi(() => endpoints.thresholds({}));

  const risk = data?.risk_snapshot ?? {};

  return (
    <AppShell title={t("nav.thresholds")}>
      <PageHeading title={t("thresholds.title")} subtitle={t("thresholds.subtitle")} />

      {loading ? (
        <LoadingState />
      ) : error ? (
        <ErrorState message={error} onRetry={reload} />
      ) : data ? (
        <>
          {data.threshold_semantics && (
            <GuardrailBanner items={[data.threshold_semantics]} />
          )}

          {Object.keys(risk).length > 0 && (
            <Card>
              <CardHeader>
                <CardTitle>{t("thresholds.riskSnapshot")}</CardTitle>
              </CardHeader>
              <CardContent className="grid grid-cols-2 gap-2 sm:grid-cols-4">
                {Object.entries(risk).map(([key, value]) => (
                  <div key={key} className="rounded-md border px-3 py-2">
                    <p className="text-muted-foreground truncate text-xs">{key}</p>
                    <p className="font-mono text-sm font-medium tabular-nums">
                      {formatNumber(value, 3)}
                    </p>
                  </div>
                ))}
              </CardContent>
            </Card>
          )}

          <ThresholdBrowser
            nodes={(data.threshold_nodes ?? []) as never}
            contextualNodes={(data.contextual_threshold_nodes ?? []) as never}
          />
        </>
      ) : null}
    </AppShell>
  );
}
