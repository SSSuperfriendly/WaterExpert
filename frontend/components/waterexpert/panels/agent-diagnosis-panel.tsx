"use client";

/**
 * What the six agents concluded, and what each conclusion rests on.
 *
 * The strategy card above this one shows three numbers and six metrics. Read
 * alone, they are indistinguishable whether the trained models produced them or
 * a rule of thumb did — and both paths run, because every agent here falls back
 * rather than failing a request. The fallback is what makes the page robust and
 * what makes it dangerous to read: `release_rate: 4.5` looks the same either
 * way, and the run that produced it can be one where MSCIM never loaded.
 *
 * So the first thing every block renders is `inference_source`. A checkpoint
 * run says so. A rule-based run says so in as many words, in the warning tone,
 * with the load error beside it. Nothing here is inferred from whether the
 * numbers look plausible.
 *
 * Everything below that heading is the model's own vocabulary, resolved through
 * `translateColumn` and left as the raw identifier when no label exists — the
 * alternative is a translation this file invents, which would read exactly like
 * a name the model actually uses.
 */

import * as React from "react";
import { useT } from "@/lib/i18n/use-t";
import { translateColumn } from "@/lib/domain";
import { formatNumber, formatPercent } from "@/lib/format";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import type {
  AgentCaseEvidence,
  AgentCmfbeTrace,
  AgentKbRecommendation,
  AgentMscimTrace,
} from "@/lib/api/contracts";

/** `checkpoint` reads as a fact; `fallback_rules` reads as a caveat. */
function InferenceBadge({ source }: { source: string | undefined }) {
  const { t } = useT();
  if (source === "checkpoint") {
    return (
      <Badge variant="secondary" className="text-xs">
        {t("agent.inferenceCheckpoint")}
      </Badge>
    );
  }
  if (source === "fallback_rules") {
    return (
      <Badge variant="destructive" className="text-xs">
        {t("agent.inferenceFallback")}
      </Badge>
    );
  }
  // An agent the platform predates, or one that returned a source this page
  // does not know: show what it said rather than guessing which badge fits.
  return (
    <Badge variant="outline" className="text-xs">
      {source || "—"}
    </Badge>
  );
}

/** The heading every agent block shares: name, provenance, and any load error. */
function AgentHeading({
  agent,
  source,
  error,
}: {
  agent: string;
  source: string | undefined;
  error: string | undefined;
}) {
  const { t } = useT();
  return (
    <div className="space-y-1.5">
      <div className="flex flex-wrap items-center gap-2">
        <span className="text-sm font-medium">{agent}</span>
        <span className="text-muted-foreground text-xs">{t("agent.inferenceSource")}:</span>
        <InferenceBadge source={source} />
      </div>
      {source === "fallback_rules" && (
        <p className="text-destructive text-xs">{t("agent.inferenceFallbackNote")}</p>
      )}
      {error && (
        <p className="text-muted-foreground font-mono text-[11px] break-all">
          {t("agent.checkpointError")}: {error}
        </p>
      )}
    </div>
  );
}

/** A labelled number, the shape every scalar in these traces is shown in. */
function Stat({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="rounded-md border px-3 py-2">
      <p className="text-muted-foreground text-xs">{label}</p>
      <p className="font-mono text-sm tabular-nums">{value}</p>
    </div>
  );
}

export function MscimDiagnosis({ trace }: { trace: AgentMscimTrace }) {
  const { t } = useT();
  // The trace is either a prediction or an error; on the error path there is no
  // `diagnosis` at all, and the heading is the whole of what can be said.
  if (trace.error) {
    return (
      <div className="space-y-3">
        <AgentHeading agent="MSCIM" source={trace.inference_source} error={trace.error} />
      </div>
    );
  }

  const prediction = trace.prediction ?? {};
  const diagnosis = trace.diagnosis ?? {};
  const drivers = diagnosis.primary_drivers ?? [];
  const uncertainty = diagnosis.uncertainty ?? {};

  return (
    <div className="space-y-3">
      <AgentHeading
        agent="MSCIM"
        source={trace.inference_source}
        error={trace.checkpoint_error}
      />

      <div className="grid grid-cols-2 gap-2">
        <Stat
          label={t("agent.predictedTurbidity")}
          value={formatNumber(prediction.turbidity, 2)}
        />
        <Stat
          label={t("agent.predictionConfidence")}
          value={formatPercent(prediction.turbidity_confidence, 0)}
        />
      </div>

      {drivers.length === 0 ? (
        <p className="text-muted-foreground text-xs">{t("agent.noDrivers")}</p>
      ) : (
        <div className="space-y-1.5">
          <p className="text-muted-foreground text-xs">{t("agent.dominantDriver")}</p>
          <table className="w-full text-xs">
            <thead>
              <tr className="text-muted-foreground border-b text-left">
                <th className="py-1 font-normal">{t("agent.driverFactor")}</th>
                <th className="py-1 text-right font-normal">{t("agent.driverImportance")}</th>
                <th className="py-1 text-right font-normal">{t("agent.driverValue")}</th>
              </tr>
            </thead>
            <tbody>
              {drivers.map((driver, index) => (
                <tr key={driver.factor ?? index} className="border-b last:border-0">
                  <td className="py-1">{translateColumn(t, driver.factor)}</td>
                  <td className="py-1 text-right font-mono tabular-nums">
                    {formatNumber(driver.importance, 3)}
                  </td>
                  <td className="py-1 text-right font-mono tabular-nums">
                    {formatNumber(driver.value, 2)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {(uncertainty.epistemic !== undefined || uncertainty.aleatoric !== undefined) && (
        <div className="flex flex-wrap gap-2">
          <Badge variant="outline" className="text-xs font-normal">
            {t("agent.uncertaintyEpistemic")} {formatNumber(uncertainty.epistemic, 3)}
          </Badge>
          <Badge variant="outline" className="text-xs font-normal">
            {t("agent.uncertaintyAleatoric")} {formatNumber(uncertainty.aleatoric, 3)}
          </Badge>
        </div>
      )}
    </div>
  );
}

export function CmfbeDiagnosis({ trace }: { trace: AgentCmfbeTrace }) {
  const { t } = useT();
  if (trace.error) {
    return (
      <div className="space-y-3">
        <AgentHeading agent="CMFBE-ST-GCN" source={trace.inference_source} error={trace.error} />
      </div>
    );
  }

  const processes = Object.entries(trace.process_decomposition ?? {});
  const predictions = trace.predictions ?? {};
  const physics = trace.physics ?? {};
  // A process value is a signed contribution: above zero it adds turbidity,
  // below zero it removes it. The bar length is the magnitude, the side is the
  // sign, so the two are not confused for one another.
  const largest = Math.max(...processes.map(([, value]) => Math.abs(value)), 0.0001);

  return (
    <div className="space-y-3">
      <AgentHeading
        agent="CMFBE-ST-GCN"
        source={trace.inference_source}
        error={trace.checkpoint_error}
      />

      <div className="grid grid-cols-2 gap-2">
        <Stat
          label={t("agent.nextDayTurbidity")}
          value={formatNumber(predictions.next_day_turbidity, 2)}
        />
        <Stat label={t("agent.processNetChange")} value={formatNumber(trace.net_change, 4)} />
      </div>

      {processes.length > 0 && (
        <div className="space-y-1.5">
          {processes.map(([name, value]) => (
            <div key={name} className="flex items-center gap-2 text-xs">
              <span className="w-28 shrink-0 truncate">{translateColumn(t, name)}</span>
              <span className="bg-muted relative h-2 flex-1 rounded-sm">
                <span
                  className={`absolute top-0 h-2 rounded-sm ${
                    value >= 0 ? "bg-amber-500" : "bg-sky-500"
                  }`}
                  style={{ width: `${Math.min(100, (Math.abs(value) / largest) * 100)}%` }}
                />
              </span>
              <span className="w-16 shrink-0 text-right font-mono tabular-nums">
                {formatNumber(value, 4)}
              </span>
            </div>
          ))}
        </div>
      )}

      <div className="flex flex-wrap gap-2">
        <Badge variant="outline" className="text-xs font-normal">
          {t("agent.processSourceTotal")} {formatNumber(physics.source_total, 4)}
        </Badge>
        <Badge variant="outline" className="text-xs font-normal">
          {t("agent.processSinkTotal")} {formatNumber(physics.sink_total, 4)}
        </Badge>
        {predictions.next_day_turbidity_trend && (
          <Badge variant="outline" className="text-xs font-normal">
            {predictions.next_day_turbidity_trend === "increasing"
              ? t("agent.trendIncreasing")
              : t("agent.trendDecreasing")}
          </Badge>
        )}
      </div>

      <div className="space-y-1.5">
        <p className="text-muted-foreground text-xs">{t("agent.thresholdTitle")}</p>
        {(trace.threshold_breaches ?? []).length === 0 ? (
          <p className="text-muted-foreground text-xs">{t("agent.thresholdClear")}</p>
        ) : (
          <div className="flex flex-wrap gap-2">
            {(trace.threshold_breaches ?? []).map((breach, index) => (
              <Badge key={breach.factor ?? index} variant="destructive" className="text-xs font-normal">
                {translateColumn(t, breach.factor)} {formatNumber(breach.value, 2)} /{" "}
                {formatNumber(breach.threshold, 2)}
              </Badge>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

/**
 * One candidate measure, with the thing that makes its number checkable.
 *
 * The three origins are genuinely different claims and are labelled as such. A
 * graph candidate is an influence someone published, and its parameters are
 * blank because a relation carries no dose — rendering `—` is the point, not a
 * gap to be filled. A case-backed candidate is a dose that was actually applied
 * to a water body, so it names the case and the paper. A seed entry is the
 * curated technology table, which has no parameters either.
 */
export function KnowledgeCandidate({ item }: { item: AgentKbRecommendation }) {
  const { t } = useT();
  const origin = item.origin ?? "";
  const originLabel =
    origin === "graph"
      ? t("agent.originGraph")
      : origin === "scenario"
        ? t("agent.originScenario")
        : origin === "seed"
          ? t("agent.originSeed")
          : origin;

  return (
    <div className="space-y-1.5 rounded-md border p-3">
      <div className="flex flex-wrap items-center gap-2">
        <span className="text-sm font-medium">{item.technique}</span>
        {originLabel && (
          <Badge variant={origin === "graph" ? "outline" : "secondary"} className="text-xs">
            {originLabel}
          </Badge>
        )}
        {item.intensity !== null && item.intensity !== undefined ? (
          <span className="font-mono text-xs tabular-nums">
            {formatNumber(item.intensity, 2)} {item.intensity_unit ?? ""}
          </span>
        ) : (
          <span className="text-muted-foreground text-xs">{t("agent.noIntensity")}</span>
        )}
      </div>

      {item.source_label && (
        <p className="text-muted-foreground text-xs">
          {t("agent.graphFrom")}: {item.source_label}
          {item.citation ? ` · ${item.citation}` : ""}
        </p>
      )}

      {item.relation && (
        <p className="text-muted-foreground text-xs">
          {item.relation}
          {item.evidence ? ` · ${item.evidence}` : ""}
        </p>
      )}
      {!item.relation && item.evidence && (
        <p className="text-muted-foreground text-xs">{item.evidence}</p>
      )}

      {item.case_id && (
        <p className="text-muted-foreground text-xs">
          {t("agent.caseBackedBy")}: <span className="font-mono">{item.case_id}</span>
          {item.case_similarity !== null && item.case_similarity !== undefined
            ? ` · ${t("agent.caseSimilarity")} ${formatPercent(item.case_similarity, 0)}`
            : ""}
        </p>
      )}

      {item.reference && (
        <p className="text-muted-foreground border-t pt-1.5 text-[11px] italic">
          {t("agent.caseReference")}: {item.reference}
        </p>
      )}
      {!item.reference && (item.environment || item.effect) && (
        <p className="text-muted-foreground border-t pt-1.5 text-[11px]">
          {[item.environment, item.effect].filter(Boolean).join(" · ")}
        </p>
      )}
    </div>
  );
}

/** The whole knowledge block: what the retrieval returned and what it rests on. */
export function KnowledgeEvidence({
  grounded,
  recommendations,
  caseEvidence,
}: {
  grounded: boolean;
  recommendations: AgentKbRecommendation[];
  caseEvidence: AgentCaseEvidence[];
}) {
  const { t } = useT();
  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">{t("agent.knowledgeTitle")}</CardTitle>
        <CardTitle className="text-muted-foreground text-xs font-normal">
          {t("agent.knowledgeSubtitle")}
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        <Badge variant={grounded ? "secondary" : "outline"} className="text-xs font-normal">
          {grounded ? t("agent.knowledgeGrounded") : t("agent.knowledgeUngrounded")}
        </Badge>

        {recommendations.length === 0 ? (
          <p className="text-muted-foreground text-xs">{t("common.noData")}</p>
        ) : (
          <div className="grid grid-cols-1 gap-3 lg:grid-cols-2">
            {recommendations.map((item, index) => (
              <KnowledgeCandidate key={`${item.technique}-${index}`} item={item} />
            ))}
          </div>
        )}

        {caseEvidence.length > 0 && (
          <div className="space-y-2">
            <p className="text-sm font-medium">{t("agent.caseEvidenceTitle")}</p>
            <div className="grid grid-cols-1 gap-3 lg:grid-cols-2">
              {caseEvidence.map((record, index) => (
                <div key={record.id ?? index} className="space-y-2 rounded-md border p-3">
                  <p className="text-sm font-medium">{record.title ?? record.id}</p>
                  <p className="text-muted-foreground text-xs">
                    {[record.location, record.year].filter(Boolean).join(" · ")}
                    {record.similarity !== undefined
                      ? ` · ${t("agent.caseSimilarity")} ${formatPercent(record.similarity, 0)}`
                      : ""}
                  </p>
                  {record.summary && (
                    <p className="text-muted-foreground text-xs leading-snug">{record.summary}</p>
                  )}
                  {record.intervention && Object.keys(record.intervention).length > 0 && (
                    <p className="text-xs">
                      <span className="text-muted-foreground">{t("agent.caseIntervention")}: </span>
                      <span className="font-mono tabular-nums">
                        {Object.entries(record.intervention)
                          .map(([key, value]) => `${translateColumn(t, key)} ${formatNumber(value, 2)}`)
                          .join(" · ")}
                      </span>
                    </p>
                  )}
                  {record.outcome && (
                    <div className="flex flex-wrap gap-1.5">
                      {record.outcome.turbidity_reduction_ratio !== undefined && (
                        <Badge variant="secondary" className="text-xs">
                          {t("agent.turbidityCutRatio")}{" "}
                          {formatPercent(record.outcome.turbidity_reduction_ratio, 0)}
                        </Badge>
                      )}
                      {record.outcome.cost_saving_ratio !== undefined && (
                        <Badge variant="secondary" className="text-xs">
                          {t("agent.costSavingRatio")}{" "}
                          {formatPercent(record.outcome.cost_saving_ratio, 0)}
                        </Badge>
                      )}
                      {record.outcome.recovery_days !== undefined && (
                        <Badge variant="secondary" className="text-xs">
                          {t("agent.recoveryDays")} {formatNumber(record.outcome.recovery_days, 0)} d
                        </Badge>
                      )}
                    </div>
                  )}
                  {record.reference && (
                    <p className="text-muted-foreground border-t pt-1.5 text-[11px] italic">
                      {t("agent.caseReference")}: {record.reference}
                    </p>
                  )}
                </div>
              ))}
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
