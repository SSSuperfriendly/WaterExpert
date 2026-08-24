"use client";

import { useT } from "@/lib/i18n/use-t";
import { useApi } from "@/lib/hooks/use-api";
import { endpoints } from "@/lib/api/endpoints";
import { translateScenario, translateRisk, riskBadgeVariant } from "@/lib/domain";
import { formatNumber, formatMaybeDate } from "@/lib/format";
import { AppShell } from "@/components/waterexpert/app-shell";
import { PageHeading, LoadingState, ErrorState } from "@/components/waterexpert/ui-states";
import { GuardrailBanner } from "@/components/waterexpert/guardrail-banner";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";

export default function PlaybookPage() {
  const { t } = useT();
  const { data, loading, error, reload } = useApi(() => endpoints.responsePlaybook());

  const playbook = (data?.scenario_response_playbook ?? {}) as Record<string, Record<string, unknown>>;
  const prioritized = (data?.prioritized_cases ?? []) as Record<string, unknown>[];
  const digest = (data?.threshold_digest ?? []) as Record<string, unknown>[];

  const asList = (v: unknown): string[] =>
    Array.isArray(v) ? v.map((x) => String(x)) : v ? [String(v)] : [];

  return (
    <AppShell title={t("nav.playbook")}>
      <PageHeading title={t("playbook.title")} subtitle={t("playbook.subtitle")} />

      {loading ? (
        <LoadingState />
      ) : error ? (
        <ErrorState message={error} onRetry={reload} />
      ) : data ? (
        <>
          {data.guardrails && data.guardrails.length > 0 && (
            <GuardrailBanner items={data.guardrails} />
          )}

          <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
            {Object.entries(playbook).map(([key, def]) => (
              <Card key={key}>
                <CardHeader>
                  <CardTitle>{translateScenario(t, key)}</CardTitle>
                  <p className="text-muted-foreground text-xs">
                    {t("playbook.occurrenceCount")}: {formatNumber(def.occurrence_count, 0)}
                  </p>
                </CardHeader>
                <CardContent className="space-y-3 text-sm">
                  {typeof def.response_focus === "string" && def.response_focus && (
                    <p className="leading-snug">
                      <span className="font-medium">{t("playbook.responseFocus")}: </span>
                      <span className="text-muted-foreground">{def.response_focus}</span>
                    </p>
                  )}
                  <ListSection
                    title={t("playbook.recommendedActions")}
                    items={asList(def.recommended_actions)}
                  />
                  <ListSection
                    title={t("playbook.monitoringTargets")}
                    items={asList(def.monitoring_targets)}
                  />
                  <ListSection
                    title={t("playbook.requiredFollowUpData")}
                    items={asList(def.required_follow_up_data)}
                  />
                  <ListSection
                    title={t("playbook.forbiddenClaims")}
                    items={asList(def.forbidden_claims)}
                    destructive
                  />
                </CardContent>
              </Card>
            ))}
          </div>

          {prioritized.length > 0 && (
            <Card>
              <CardHeader>
                <CardTitle>{t("playbook.prioritizedCases")}</CardTitle>
              </CardHeader>
              <CardContent>
                <ul className="space-y-2">
                  {prioritized.map((row, i) => (
                    <li key={i} className="rounded-md border px-3 py-2 text-sm">
                      <div className="flex flex-wrap items-center gap-2">
                        <span className="font-medium tabular-nums">
                          {formatMaybeDate(row.target_date)}
                        </span>
                        <Badge variant={riskBadgeVariant(String(row.risk_band ?? ""))}>
                          {translateRisk(t, String(row.risk_band ?? ""))}
                        </Badge>
                        <span className="text-muted-foreground">
                          {translateScenario(t, String(row.scenario ?? ""))}
                        </span>
                        <span className="text-muted-foreground ml-auto font-mono text-xs tabular-nums">
                          {formatNumber(row.primary_score, 2)}
                        </span>
                      </div>
                      {typeof row.evidence_summary === "string" && row.evidence_summary && (
                        <p className="text-muted-foreground mt-1 line-clamp-2 text-xs">
                          {row.evidence_summary}
                        </p>
                      )}
                    </li>
                  ))}
                </ul>
              </CardContent>
            </Card>
          )}

          {digest.length > 0 && (
            <Card>
              <CardHeader>
                <CardTitle>{t("playbook.thresholdDigest")}</CardTitle>
              </CardHeader>
              <CardContent>
                <ul className="grid grid-cols-1 gap-2 sm:grid-cols-2 lg:grid-cols-4">
                  {digest.map((row, i) => (
                    <li key={i} className="rounded-md border px-3 py-2 text-sm">
                      <p className="font-medium">{String(row.agent_label ?? row.feature ?? "—")}</p>
                      <p className="text-muted-foreground font-mono text-xs tabular-nums">
                        {formatNumber(row.threshold, 3)} {String(row.unit ?? "")}
                      </p>
                    </li>
                  ))}
                </ul>
              </CardContent>
            </Card>
          )}
        </>
      ) : null}
    </AppShell>
  );
}

function ListSection({
  title,
  items,
  destructive,
}: {
  title: string;
  items: string[];
  destructive?: boolean;
}) {
  if (!items || items.length === 0) return null;
  return (
    <div>
      <p className={`text-xs font-medium ${destructive ? "text-destructive" : ""}`}>{title}</p>
      <ul className={`mt-1 list-disc space-y-0.5 pl-5 text-xs ${destructive ? "text-destructive/80" : "text-muted-foreground"}`}>
        {items.map((item, i) => (
          <li key={i} className="leading-snug">
            {item}
          </li>
        ))}
      </ul>
    </div>
  );
}
