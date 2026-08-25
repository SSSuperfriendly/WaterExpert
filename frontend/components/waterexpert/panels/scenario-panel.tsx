"use client";

import { useT } from "@/lib/i18n/use-t";
import { useApi } from "@/lib/hooks/use-api";
import { endpoints } from "@/lib/api/endpoints";
import { translateScenario } from "@/lib/domain";
import { formatNumber } from "@/lib/format";
import { LoadingState, ErrorState } from "@/components/waterexpert/ui-states";
import { ScenarioHighPriorityTable, ScenarioCountBadges } from "@/components/waterexpert/scenario-feed";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

export function ScenarioPanel() {
  const { t } = useT();
  const { data, loading, error, reload } = useApi(() => endpoints.scenarioTriage());

  const meanScores = data?.mean_primary_scores_by_scenario ?? {};
  const scenarioDefs = data?.scenario_definitions ?? {};

  return (
    <div className="flex flex-col gap-6">
      {loading ? (
        <LoadingState />
      ) : error ? (
        <ErrorState message={error} onRetry={reload} />
      ) : data ? (
        <>
          <Card>
            <CardHeader>
              <CardTitle>{t("scenario.scenarioCounts")}</CardTitle>
            </CardHeader>
            <CardContent>
              <ScenarioCountBadges counts={data.scenario_counts ?? {}} />
            </CardContent>
          </Card>

          <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
            {Object.keys(meanScores).length > 0 && (
              <Card>
                <CardHeader>
                  <CardTitle>{t("scenario.meanScores")}</CardTitle>
                </CardHeader>
                <CardContent>
                  <ul className="space-y-1.5">
                    {Object.entries(meanScores).map(([key, value]) => (
                      <li
                        key={key}
                        className="flex items-center justify-between rounded-md border px-3 py-2 text-sm"
                      >
                        <span>{translateScenario(t, key)}</span>
                        <span className="font-mono tabular-nums">{formatNumber(value, 3)}</span>
                      </li>
                    ))}
                  </ul>
                </CardContent>
              </Card>
            )}

            {Object.keys(scenarioDefs).length > 0 && (
              <Card>
                <CardHeader>
                  <CardTitle>{t("scenario.scenarioDefinitions")}</CardTitle>
                </CardHeader>
                <CardContent>
                  <ul className="space-y-3">
                    {Object.entries(scenarioDefs).map(([key, def]) => (
                      <li key={key}>
                        <p className="text-sm font-medium">{translateScenario(t, key)}</p>
                        <p className="text-muted-foreground text-xs leading-snug">
                          {typeof def === "string" ? def : JSON.stringify(def)}
                        </p>
                      </li>
                    ))}
                  </ul>
                </CardContent>
              </Card>
            )}
          </div>

          {data.high_priority_days && data.high_priority_days.length > 0 && (
            <Card>
              <CardHeader>
                <CardTitle>{t("scenario.highPriorityDays")}</CardTitle>
              </CardHeader>
              <CardContent>
                <ScenarioHighPriorityTable days={data.high_priority_days} />
              </CardContent>
            </Card>
          )}
        </>
      ) : null}
    </div>
  );
}
