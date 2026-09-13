"use client";

import * as React from "react";
import { useT } from "@/lib/i18n/use-t";
import { endpoints } from "@/lib/api/endpoints";
import { describeApiError } from "@/lib/domain";
import type { KgQaResult } from "@/lib/api/contracts";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { EmptyState, ErrorState } from "@/components/waterexpert/ui-states";
import { HugeiconsIcon } from "@hugeicons/react";
import { AiNetworkIcon, Search01Icon } from "@hugeicons/core-free-icons";
import { edgeKey, type KgHighlight } from "@/lib/kg/vis-network";
import { useKgHighlight } from "@/lib/kg/highlight-context";

/**
 * Citation markers as the answer writes them: ``[关系3]``, ``[分块1]``, ``[社区2]``.
 *
 * The same shape the backend validates against. Kept in sync by being the same
 * grammar rather than by sharing code across a language boundary — the backend
 * strips markers it cannot resolve, so a drift here shows up as a marker that
 * renders as plain text rather than as a silent mis-link.
 */
const CITATION_RE = /\[(关系|分块|社区)(\d+)\]/g;

/** Example questions drawn from real edges in the two graphs. */
const SAMPLES = [
  "风如何影响水体浊度？",
  "监测透明度有哪些方法？",
  "悬浮物如何影响清澈度？",
  "农业活动如何影响沉积物？",
];

/**
 * Split an answer into text and citation markers.
 *
 * Rendering the answer as plain text would make its citations unclickable —
 * and a citation nobody can follow is decoration. `String.prototype.split`
 * with a capturing group keeps the markers, so nothing is dropped.
 */
function renderAnswer(
  answer: string,
  onCitation: (marker: string) => void,
  activeMarker: string | null
) {
  const parts = answer.split(CITATION_RE);
  const nodes: React.ReactNode[] = [];
  // split() with one capture group yields [text, g1, g2, text, g1, g2, ...].
  for (let i = 0; i < parts.length; i += 3) {
    if (parts[i]) nodes.push(<React.Fragment key={`t${i}`}>{parts[i]}</React.Fragment>);
    if (i + 2 < parts.length) {
      const marker = `[${parts[i + 1]}${parts[i + 2]}]`;
      const active = marker === activeMarker;
      nodes.push(
        <button
          key={`c${i}`}
          type="button"
          onClick={() => onCitation(marker)}
          className={
            "mx-0.5 rounded px-1 text-xs underline underline-offset-2 transition-colors " +
            (active ? "bg-sky-100 text-sky-900" : "text-sky-700 hover:bg-sky-50")
          }
        >
          {marker}
        </button>
      );
    }
  }
  return nodes;
}

export function KgQaPanel({ onJumpToGraph }: { onJumpToGraph?: () => void } = {}) {
  const { t } = useT();
  const shared = useKgHighlight();

  const [question, setQuestion] = React.useState("");
  const [result, setResult] = React.useState<KgQaResult | null>(null);
  const [loading, setLoading] = React.useState(false);
  const [error, setError] = React.useState<unknown>(null);
  const [activeMarker, setActiveMarker] = React.useState<string | null>(null);

  const ask = React.useCallback(
    async (value: string) => {
      const trimmed = value.trim();
      if (!trimmed) return;
      setLoading(true);
      setError(null);
      setActiveMarker(null);
      try {
        // A manual handler rather than useApi: that hook is GET/effect driven,
        // and a question is submitted, not fetched.
        const payload = await endpoints.knowledgeGraph.qa(trimmed);
        setResult(payload);
      } catch (err) {
        setError(err);
        setResult(null);
      } finally {
        setLoading(false);
      }
    },
    []
  );

  const sources = result?.sources ?? [];
  const labelFor = (sourceId: string | undefined) =>
    sources.find((s) => s.source_id === sourceId)?.label ||
    (sourceId ? t(`kg.source.${sourceId}`) : "");

  // The subgraph the retrieval actually touched, in the canvas's own vocabulary.
  const highlight: KgHighlight | null = React.useMemo(() => {
    if (!result) return null;
    const nodeIds = new Set<string>();
    const edgeKeys = new Set<string>();
    for (const path of result.paths ?? []) {
      path.nodes.forEach((node) => nodeIds.add(node));
      (path.edges ?? []).forEach((edge) => edgeKeys.add(edgeKey(edge.source, edge.target)));
    }
    for (const relation of result.matched_relations ?? []) {
      if (relation.source) nodeIds.add(relation.source);
      if (relation.target) nodeIds.add(relation.target);
      if (relation.source && relation.target) edgeKeys.add(edgeKey(relation.source, relation.target));
    }
    if (nodeIds.size === 0) return null;
    return {
      title: t("kg.highlightBanner", { title: result.question }),
      nodeIds: [...nodeIds],
      edgeKeys: [...edgeKeys],
    };
  }, [result, t]);

  const jumped = React.useRef<KgQaResult | null>(null);
  React.useEffect(() => {
    if (!highlight || !shared) return;
    if (jumped.current === result) return;
    jumped.current = result;
    shared.setHighlight(highlight);
  }, [highlight, shared, result]);

  const issues = result?.stats?.hallucinated_markers ?? [];
  const chunkLevel = result?.capabilities?.chunk_level;

  return (
    <div className="flex flex-col gap-6">
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <HugeiconsIcon icon={Search01Icon} className="text-muted-foreground size-4" />
            {t("kg.questionInput")}
          </CardTitle>
        </CardHeader>
        <CardContent className="flex flex-col gap-3">
          <div className="flex flex-col gap-2 sm:flex-row">
            <input
              value={question}
              onChange={(e) => setQuestion(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter") void ask(question);
              }}
              placeholder={t("kg.questionPlaceholder")}
              aria-label={t("kg.questionInput")}
              aria-busy={loading}
              className="focus-visible:ring-ring h-9 w-full rounded-md border px-3 text-sm focus-visible:ring-[3px] focus-visible:outline-none"
            />
            <Button onClick={() => void ask(question)} disabled={loading || !question.trim()}>
              {loading ? t("common.loading") : t("kg.ask")}
            </Button>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-muted-foreground text-xs">{t("kg.sampleQuestions")}</span>
            {SAMPLES.map((sample) => (
              <button
                key={sample}
                type="button"
                onClick={() => {
                  setQuestion(sample);
                  void ask(sample);
                }}
                className="text-muted-foreground hover:bg-muted/40 rounded-full border px-2.5 py-1 text-xs transition-colors"
              >
                {sample}
              </button>
            ))}
          </div>
        </CardContent>
      </Card>

      {loading ? (
        <p className="text-muted-foreground text-sm">{t("common.loading")}</p>
      ) : error ? (
        <ErrorState message={describeApiError(t, error)} onRetry={() => void ask(question)} />
      ) : !result ? (
        <EmptyState description={t("kg.questionPlaceholder")} />
      ) : (
        <>
          <Card>
            <CardHeader>
              <CardTitle>{t("kg.answerResult")}</CardTitle>
            </CardHeader>
            <CardContent className="flex flex-col gap-3">
              <div className="text-sm leading-relaxed whitespace-pre-wrap">
                {renderAnswer(result.answer, setActiveMarker, activeMarker)}
              </div>
              <div className="flex flex-wrap items-center gap-2">
                <Badge variant="outline">
                  {t("kg.mode")}
                  {"："}
                  {t(
                    `kg.mode${(result.mode ?? "none").replace(/^./, (c) => c.toUpperCase())}`
                  )}
                </Badge>
                {result.stats?.elapsed_ms != null ? (
                  <Badge variant="outline">
                    {t("kg.ingestTime")}
                    {"："}
                    {result.stats.elapsed_ms} ms
                  </Badge>
                ) : null}
                {result.stats?.citation_validity != null ? (
                  <Badge variant="outline">
                    {t("kg.citationValidity")}
                    {"："}
                    {Math.round(result.stats.citation_validity * 100)}%
                  </Badge>
                ) : null}
                {result.stats?.llm_called ? (
                  <Badge variant="outline">{t("kg.llmCalled")}</Badge>
                ) : null}
                {result.stats?.degraded ? (
                  <Badge variant="outline">{t("kg.degradedNote")}</Badge>
                ) : null}
              </div>
              {issues.length > 0 ? (
                <p className="rounded-md border border-amber-300 bg-amber-50 px-3 py-2 text-xs text-amber-900">
                  {t("kg.citationIssues")} {issues.join("、")}
                </p>
              ) : null}
              {chunkLevel === false ? (
                <p className="text-muted-foreground text-xs">{t("kg.chunkUnavailable")}</p>
              ) : null}
            </CardContent>
          </Card>

          {(result.paths ?? []).length > 0 ? (
            <Card>
              <CardHeader>
                <CardTitle className="flex items-center gap-2">
                  <HugeiconsIcon icon={AiNetworkIcon} className="text-muted-foreground size-4" />
                  {t("kg.paths")}
                </CardTitle>
              </CardHeader>
              <CardContent className="flex flex-col gap-2">
                {(result.paths ?? []).map((path, index) => (
                  <div
                    key={path.path_id ?? index}
                    className="flex flex-wrap items-center gap-1 text-sm"
                  >
                    {path.nodes.map((node, nodeIndex) => (
                      <React.Fragment key={`${node}-${nodeIndex}`}>
                        {nodeIndex > 0 ? <span className="text-muted-foreground">→</span> : null}
                        <span className="rounded bg-slate-100 px-1.5 py-0.5">{node}</span>
                      </React.Fragment>
                    ))}
                    <Badge variant="outline" className="ml-2 text-xs">
                      {t("kg.pathHops", { count: path.hops ?? 0 })}
                    </Badge>
                    <span className="text-muted-foreground text-xs">
                      {labelFor(path.source_id)}
                    </span>
                  </div>
                ))}
              </CardContent>
            </Card>
          ) : null}

          {(result.seed_entities ?? []).length > 0 ? (
            <Card>
              <CardHeader>
                <CardTitle>{t("kg.seedEntities")}</CardTitle>
              </CardHeader>
              <CardContent className="flex flex-wrap gap-2">
                {(result.seed_entities ?? []).map((seed) => (
                  <Badge key={seed.name} variant="outline" className="gap-1 font-normal">
                    {seed.name}
                    <span className="text-muted-foreground text-xs">
                      {seed.matched_via} · {seed.score?.toFixed(2)}
                    </span>
                  </Badge>
                ))}
              </CardContent>
            </Card>
          ) : null}

          <Card>
            <CardHeader>
              <CardTitle>{t("kg.matchedRelations")}</CardTitle>
            </CardHeader>
            <CardContent className="flex flex-col gap-2">
              {(result.matched_relations ?? []).length === 0 ? (
                <p className="text-muted-foreground text-sm">{t("kg.noAnswer")}</p>
              ) : (
                (result.matched_relations ?? []).map((relation, index) => {
                  const marker = `[关系${index + 1}]`;
                  return (
                    <div
                      key={`${relation.source}-${relation.target}-${index}`}
                      className={
                        "rounded-md border px-3 py-2 text-sm transition-colors " +
                        (activeMarker === marker ? "border-sky-300 bg-sky-50" : "")
                      }
                    >
                      <div>
                        {relation.source}
                        <span className="text-muted-foreground">
                          {" --"}
                          {relation.relation || relation.evidence}
                          {"--> "}
                        </span>
                        {relation.target}
                      </div>
                      {relation.source_file ? (
                        <div className="text-muted-foreground mt-1 text-xs">
                          {t("kg.sourceFile")}
                          {"："}
                          {relation.source_file}
                        </div>
                      ) : null}
                    </div>
                  );
                })
              )}
            </CardContent>
          </Card>

          {(result.citations ?? []).length > 0 ? (
            <Card>
              <CardHeader>
                <CardTitle>{t("kg.citations")}</CardTitle>
              </CardHeader>
              <CardContent className="flex flex-col gap-2">
                {(result.citations ?? []).map((citation) => (
                  <div
                    key={citation.marker}
                    className={
                      "flex flex-wrap items-center gap-2 rounded-md border px-3 py-2 text-sm transition-colors " +
                      (activeMarker === citation.marker ? "border-sky-300 bg-sky-50" : "")
                    }
                  >
                    <Badge variant="outline" className="font-mono text-xs">
                      {citation.marker}
                    </Badge>
                    <span>
                      {citation.source}
                      {" → "}
                      {citation.target}
                    </span>
                    <span className="text-muted-foreground text-xs">
                      {labelFor(citation.source_id)}
                    </span>
                    {citation.source_file ? (
                      <span className="text-muted-foreground text-xs">
                        {citation.source_file}
                      </span>
                    ) : null}
                  </div>
                ))}
              </CardContent>
            </Card>
          ) : null}

          {(result.communities ?? []).length > 0 ? (
            <Card>
              <CardHeader>
                <CardTitle>{t("kg.communities")}</CardTitle>
              </CardHeader>
              <CardContent className="flex flex-col gap-3">
                {(result.communities ?? []).map((community) => (
                  <div key={community.community_id} className="rounded-md border px-3 py-2">
                    <div className="flex flex-wrap items-center gap-2 text-sm">
                      <span className="font-mono text-xs">{community.community_id}</span>
                      <Badge variant="outline" className="text-xs">
                        {t("kg.communitySize", { count: community.size ?? 0 })}
                      </Badge>
                      {community.summary_mode && community.summary_mode !== "llm" ? (
                        <Badge variant="outline" className="text-xs">
                          {t("kg.communityExtractive")}
                        </Badge>
                      ) : null}
                    </div>
                    {community.summary ? (
                      <p className="text-muted-foreground mt-2 text-sm">{community.summary}</p>
                    ) : null}
                  </div>
                ))}
              </CardContent>
            </Card>
          ) : null}

          {shared && highlight ? (
            <div>
              <Button
                variant="outline"
                size="sm"
                onClick={() => {
                  shared.setHighlight(highlight);
                  onJumpToGraph?.();
                }}
              >
                <HugeiconsIcon icon={AiNetworkIcon} className="size-4" />
                {t("kg.viewInGraph")}
              </Button>
            </div>
          ) : null}
        </>
      )}
    </div>
  );
}
