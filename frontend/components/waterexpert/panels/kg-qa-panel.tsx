"use client";

import * as React from "react";
import { useT } from "@/lib/i18n/use-t";
import { endpoints } from "@/lib/api/endpoints";
import { describeApiError, translateKgSource, translateKgSourceInfo } from "@/lib/domain";
import type { KgQaCitation, KgQaResult } from "@/lib/api/contracts";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { EmptyState, ErrorState } from "@/components/waterexpert/ui-states";
import { HugeiconsIcon } from "@hugeicons/react";
import { AiNetworkIcon, Search01Icon } from "@hugeicons/core-free-icons";
import {
  useKgHighlight,
  type KgEdgeFocus,
  type KgNodeRef,
  type KgSubgraphRequest,
} from "@/lib/kg/highlight-context";

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
 * What one click asks the canvas for, on top of the answer's own entities.
 *
 * A patch rather than a whole request because every affordance here starts from
 * the same drawing — the answer's subgraph — and changes exactly one thing
 * about it: which part to light up, or one more community to merge in. Building
 * complete requests per affordance would let the node list drift between them,
 * and a citation whose entity was not in the list would land in ``missing``.
 */
type Patch = {
  focus?: KgEdgeFocus;
  focusNode?: KgNodeRef;
  communityIds?: string[];
};

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

/** How many citations of the same ordered pair came before this one. */
function occurrenceIndexes(citations: KgQaCitation[]): Map<string, number> {
  const seen = new Map<string, number>();
  const out = new Map<string, number>();
  for (const citation of citations) {
    if (citation.kind !== "relation" || !citation.source || !citation.target) continue;
    const triple = `${citation.source_id ?? ""}::${citation.source}>${citation.target}`;
    const index = seen.get(triple) ?? 0;
    seen.set(triple, index + 1);
    out.set(citation.marker, index);
  }
  return out;
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

  const sources = React.useMemo(() => result?.sources ?? [], [result]);
  const relations = React.useMemo(() => result?.matched_relations ?? [], [result]);
  const paths = React.useMemo(() => result?.paths ?? [], [result]);
  const seeds = React.useMemo(() => result?.seed_entities ?? [], [result]);
  const citations = React.useMemo(() => result?.citations ?? [], [result]);
  const communities = React.useMemo(() => result?.communities ?? [], [result]);
  const chunks = React.useMemo(() => result?.chunks ?? [], [result]);

  /**
   * Every entity the answer stands on, in the canvas's vocabulary.
   *
   * Collected from all five places the answer names one — paths, relations,
   * citations, seeds and community members — because a citation can point at an
   * edge the relation list does not carry, and asking the canvas to focus that
   * edge without its endpoints would return a focus of ``null``.
   */
  const answerNodes = React.useMemo<KgNodeRef[]>(() => {
    if (!result) return [];
    const refs = new Map<string, KgNodeRef>();
    const add = (sourceId?: string, name?: string) => {
      if (!sourceId || !name) return;
      refs.set(`${sourceId}::${name}`, { source_id: sourceId, name });
    };
    for (const path of result.paths ?? []) {
      path.nodes.forEach((name) => add(path.source_id, name));
      (path.edges ?? []).forEach((edge) => {
        add(edge.source_id, edge.source);
        add(edge.source_id, edge.target);
      });
    }
    for (const relation of result.matched_relations ?? []) {
      add(relation.source_id, relation.source);
      add(relation.source_id, relation.target);
    }
    for (const citation of result.citations ?? []) {
      add(citation.source_id, citation.source);
      add(citation.source_id, citation.target);
    }
    for (const seed of result.seed_entities ?? []) add(seed.source_id, seed.name);
    return [...refs.values()];
  }, [result]);

  const markerIndex = React.useMemo(() => occurrenceIndexes(citations), [citations]);

  const labelFor = (sourceId?: string) => {
    const known = sources.find((s) => s.source_id === sourceId);
    // The backend sends ``label_key``; using it means a source this UI was never
    // taught about shows its own name instead of a literal i18n key.
    return known ? translateKgSourceInfo(t, known) : translateKgSource(t, sourceId);
  };

  /** Ask the canvas for this answer's subgraph, plus one change to it. */
  const show = React.useCallback(
    (patch: Patch, options: { jump?: boolean; marker?: string | null } = {}) => {
      const { jump = false, marker = null } = options;
      setActiveMarker(marker);
      if (!shared) return;
      const request: KgSubgraphRequest = {
        nodes: answerNodes,
        communityIds: patch.communityIds,
        focus: patch.focus,
        focusNode: patch.focusNode,
      };
      shared.setHighlight({ title: result?.question ?? question, request });
      if (jump) onJumpToGraph?.();
    },
    [shared, answerNodes, onJumpToGraph, question, result]
  );

  const showEdge = React.useCallback(
    (focus: KgEdgeFocus, options?: { jump?: boolean; marker?: string | null }) =>
      show({ focus }, options),
    [show]
  );

  const showNode = React.useCallback(
    (node: KgNodeRef, options?: { jump?: boolean; marker?: string | null }) =>
      show({ focusNode: node }, options),
    [show]
  );

  /** Merge a community in, or drop it again if it is already merged. */
  const toggleCommunity = React.useCallback(
    (communityId: string, options: { jump?: boolean; marker?: string | null } = {}) => {
      const current = shared?.highlight?.request.communityIds ?? [];
      const next = current.includes(communityId)
        ? current.filter((id) => id !== communityId)
        : [...current, communityId];
      show({ communityIds: next }, options);
    },
    [shared, show]
  );

  // A citation marker in the answer text resolves through ``citations`` rather
  // than by position: the backend numbers each kind separately and tells us the
  // id behind every marker, so guessing an offset would be strictly worse.
  const onCitation = React.useCallback(
    (marker: string) => {
      const citation = citations.find((item) => item.marker === marker);
      if (!citation) {
        setActiveMarker(marker);
        return;
      }
      if (citation.kind === "relation") {
        showEdge(
          {
            source_id: citation.source_id ?? "",
            source: citation.source ?? "",
            target: citation.target ?? "",
            index: markerIndex.get(marker) ?? 0,
          },
          { marker }
        );
        return;
      }
      if (citation.kind === "community" && citation.community_id) {
        toggleCommunity(citation.community_id, { marker });
        return;
      }
      // A chunk citation has no edge to point at, so it only marks itself.
      setActiveMarker(marker);
    },
    [citations, markerIndex, showEdge, toggleCommunity]
  );

  // The answer's own subgraph is pushed to the canvas as soon as it arrives, so
  // switching to the graph tab is enough to see the grounding — the button at
  // the bottom is a shortcut, not the only way through.
  const pushed = React.useRef<KgQaResult | null>(null);
  React.useEffect(() => {
    if (!result || !shared || pushed.current === result) return;
    pushed.current = result;
    setActiveMarker(null);
    shared.setHighlight({
      title: result.question,
      request: { nodes: answerNodes },
    });
  }, [result, shared, answerNodes]);

  const issues = result?.stats?.hallucinated_markers ?? [];

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
                {renderAnswer(result.answer, onCitation, activeMarker)}
              </div>
              <div className="flex flex-wrap items-center gap-2">
                <Badge variant="outline">
                  {t("kg.mode")}
                  {"："}
                  {t(`kg.mode${(result.mode ?? "none").replace(/^./, (c) => c.toUpperCase())}`)}
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
            </CardContent>
          </Card>

          {paths.length > 0 ? (
            <Card>
              <CardHeader>
                <CardTitle className="flex items-center gap-2">
                  <HugeiconsIcon icon={AiNetworkIcon} className="text-muted-foreground size-4" />
                  {t("kg.paths")}
                </CardTitle>
              </CardHeader>
              <CardContent className="flex flex-col gap-2">
                {paths.map((path, index) => (
                  <div
                    key={path.path_id ?? index}
                    className="flex flex-wrap items-center gap-1 text-sm"
                  >
                    {path.nodes.map((node, nodeIndex) => (
                      <React.Fragment key={`${node}-${nodeIndex}`}>
                        {nodeIndex > 0 ? <span className="text-muted-foreground">→</span> : null}
                        <button
                          type="button"
                          title={t("kg.focusInGraph")}
                          onClick={() =>
                            path.source_id &&
                            showNode(
                              { source_id: path.source_id, name: node },
                              { jump: true }
                            )
                          }
                          className="rounded bg-slate-100 px-1.5 py-0.5 hover:bg-sky-100"
                        >
                          {node}
                        </button>
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

          {seeds.length > 0 ? (
            <Card>
              <CardHeader>
                <CardTitle>{t("kg.seedEntities")}</CardTitle>
              </CardHeader>
              <CardContent className="flex flex-wrap gap-2">
                {seeds.map((seed, index) => (
                  <button
                    key={`${seed.name}-${index}`}
                    type="button"
                    title={seed.source_id ? t("kg.focusInGraph") : undefined}
                    disabled={!seed.source_id}
                    onClick={() =>
                      seed.source_id &&
                      showNode({ source_id: seed.source_id, name: seed.name }, { jump: true })
                    }
                    className="hover:bg-muted/40 rounded-full border px-2.5 py-1 text-xs disabled:opacity-60"
                  >
                    {seed.name}
                    <span className="text-muted-foreground ml-1">
                      {t("kg.matchedVia")}
                      {"："}
                      {seed.matched_via}
                      {seed.score != null ? ` · ${seed.score.toFixed(2)}` : ""}
                    </span>
                  </button>
                ))}
              </CardContent>
            </Card>
          ) : null}

          <Card>
            <CardHeader>
              <CardTitle>{t("kg.matchedRelations")}</CardTitle>
            </CardHeader>
            <CardContent className="flex flex-col gap-2">
              {relations.length === 0 ? (
                <p className="text-muted-foreground text-sm">{t("kg.noAnswer")}</p>
              ) : (
                relations.map((relation, index) => {
                  const marker = `[关系${index + 1}]`;
                  const focus: KgEdgeFocus = {
                    source_id: relation.source_id ?? "",
                    source: relation.source ?? "",
                    target: relation.target ?? "",
                    // Parallel edges share endpoints; the count of earlier
                    // relations over the same pair is what tells them apart.
                    index: relations
                      .slice(0, index)
                      .filter(
                        (other) =>
                          other.source_id === relation.source_id &&
                          other.source === relation.source &&
                          other.target === relation.target
                      ).length,
                  };
                  return (
                    <div
                      key={`${relation.source}-${relation.target}-${index}`}
                      className={
                        "rounded-md border px-3 py-2 text-sm transition-colors " +
                        (activeMarker === marker ? "border-sky-300 bg-sky-50" : "")
                      }
                    >
                      <div>
                        <button
                          type="button"
                          onClick={() => showEdge(focus, { marker })}
                          className={
                            "mr-1 rounded px-1 text-xs underline underline-offset-2 " +
                            (activeMarker === marker
                              ? "bg-sky-100 text-sky-900"
                              : "text-sky-700 hover:bg-sky-50")
                          }
                        >
                          {marker}
                        </button>
                        {relation.source}
                        <span className="text-muted-foreground">
                          {" --"}
                          {relation.relation || relation.evidence}
                          {"--> "}
                        </span>
                        {relation.target}
                      </div>
                      <div className="mt-1 flex flex-wrap items-center gap-2 text-xs">
                        {relation.source_file ? (
                          <button
                            type="button"
                            title={t("kg.focusInGraph")}
                            onClick={() => showEdge(focus, { jump: true, marker })}
                            className="text-muted-foreground underline underline-offset-2 hover:text-sky-700"
                          >
                            {t("kg.sourceFile")}
                            {"："}
                            {relation.source_file}
                          </button>
                        ) : null}
                        <span className="text-muted-foreground">{labelFor(relation.source_id)}</span>
                      </div>
                    </div>
                  );
                })
              )}
            </CardContent>
          </Card>

          {chunks.length > 0 ? (
            <Card>
              <CardHeader>
                <CardTitle>{t("kg.chunks")}</CardTitle>
              </CardHeader>
              <CardContent className="flex flex-col gap-3">
                {chunks.map((chunk) => (
                  <div key={chunk.chunk_id} className="rounded-md border px-3 py-2 text-sm">
                    <div className="text-muted-foreground flex flex-wrap items-center gap-2 text-xs">
                      <span className="font-mono">{chunk.chunk_id}</span>
                      {chunk.source_file ? <span>{chunk.source_file}</span> : null}
                      {chunk.truncated ? (
                        <Badge variant="outline" className="text-xs">
                          {t("kg.subgraphTruncated")}
                        </Badge>
                      ) : null}
                    </div>
                    <p className="mt-1 leading-relaxed">{chunk.excerpt}</p>
                    {(chunk.used_by_relations ?? []).length > 0 ? (
                      <div className="mt-1 flex flex-wrap gap-x-3 gap-y-1 text-xs">
                        {(chunk.used_by_relations ?? []).map((triple, tripleIndex) => {
                          // A chunk names the relations that used it by their
                          // display endpoints, which do not say which graph they
                          // came from. Where the answer also carries the
                          // relation, it can be located; where it does not, the
                          // text is shown as the fact it is rather than dressed
                          // up as a link that would resolve to nothing.
                          const sourceId = relations.find(
                            (relation) =>
                              relation.source === triple[0] && relation.target === triple[2]
                          )?.source_id;
                          const label = `${triple[0]} --${triple[1]}--> ${triple[2]}`;
                          return sourceId ? (
                            <button
                              key={`${chunk.chunk_id}-${tripleIndex}`}
                              type="button"
                              title={t("kg.focusInGraph")}
                              onClick={() =>
                                showEdge(
                                  {
                                    source_id: sourceId,
                                    source: triple[0] ?? "",
                                    target: triple[2] ?? "",
                                  },
                                  { jump: true }
                                )
                              }
                              className="text-muted-foreground underline underline-offset-2 hover:text-sky-700"
                            >
                              {label}
                            </button>
                          ) : (
                            <span key={`${chunk.chunk_id}-${tripleIndex}`}>{label}</span>
                          );
                        })}
                      </div>
                    ) : null}
                  </div>
                ))}
              </CardContent>
            </Card>
          ) : null}

          {citations.length > 0 ? (
            <Card>
              <CardHeader>
                <CardTitle>{t("kg.citations")}</CardTitle>
              </CardHeader>
              <CardContent className="flex flex-col gap-2">
                {citations.map((citation) => (
                  <div
                    key={citation.marker}
                    className={
                      "flex flex-col gap-1 rounded-md border px-3 py-2 text-sm transition-colors " +
                      (activeMarker === citation.marker ? "border-sky-300 bg-sky-50" : "")
                    }
                  >
                    <div className="flex flex-wrap items-center gap-2">
                      <button
                        type="button"
                        onClick={() => onCitation(citation.marker)}
                        className={
                          "rounded px-1 font-mono text-xs underline underline-offset-2 " +
                          (activeMarker === citation.marker
                            ? "bg-sky-100 text-sky-900"
                            : "text-sky-700 hover:bg-sky-50")
                        }
                      >
                        {citation.marker}
                      </button>
                      {citation.kind === "community" ? (
                        <span className="font-mono text-xs">{citation.community_id}</span>
                      ) : (
                        <span>
                          {citation.source}
                          {" → "}
                          {citation.target}
                        </span>
                      )}
                      <span className="text-muted-foreground text-xs">
                        {labelFor(citation.source_id)}
                      </span>
                      {citation.source_file ? (
                        <span className="text-muted-foreground text-xs">
                          {citation.source_file}
                        </span>
                      ) : null}
                    </div>
                    {citation.evidence ? (
                      <p className="text-muted-foreground text-xs">{citation.evidence}</p>
                    ) : null}
                  </div>
                ))}
              </CardContent>
            </Card>
          ) : null}

          {communities.length > 0 ? (
            <Card>
              <CardHeader>
                <CardTitle>{t("kg.communities")}</CardTitle>
              </CardHeader>
              <CardContent className="flex flex-col gap-3">
                {communities.map((community) => (
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
                      <button
                        type="button"
                        onClick={() => toggleCommunity(community.community_id, { jump: true })}
                        className="text-sky-700 text-xs underline underline-offset-2 hover:text-sky-900"
                      >
                        {t("kg.expandCommunity")}
                      </button>
                    </div>
                    {community.summary ? (
                      <p className="text-muted-foreground mt-2 text-sm">{community.summary}</p>
                    ) : null}
                  </div>
                ))}
              </CardContent>
            </Card>
          ) : null}

          {shared ? (
            <div>
              <Button variant="outline" size="sm" onClick={() => show({}, { jump: true })}>
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
