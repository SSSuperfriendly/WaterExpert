"use client";

import * as React from "react";
import { useT } from "@/lib/i18n/use-t";
import { useApi } from "@/lib/hooks/use-api";
import { endpoints } from "@/lib/api/endpoints";
import { downloadAuthenticated } from "@/lib/api/client";
import { describeApiError, translateKgSource, translateKgSourceInfo } from "@/lib/domain";
import { LoadingState, ErrorState } from "@/components/waterexpert/ui-states";
import { StatCard } from "@/components/waterexpert/stat-card";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { HugeiconsIcon } from "@hugeicons/react";
import { AiNetworkIcon, NodeMoveUpIcon } from "@hugeicons/core-free-icons";
import {
  applyHighlight,
  clearHighlight,
  ensureVisLoaded,
  getVis,
  NETWORK_OPTIONS,
  nodeVisuals,
  type VisDataSet,
  type VisEdge,
  type VisNetworkInstance,
  type VisNode,
} from "@/lib/kg/vis-network";
import { requestKey } from "@/lib/kg/focus";
import { useKgHighlight } from "@/lib/kg/highlight-context";
import type { KgGraphPayload, KgQaSourceInfo, KgSubgraph } from "@/lib/api/contracts";

/** What a click on the canvas selected. */
type Selection = { kind: "node" | "edge"; id: string } | null;

const DEFAULT_EDGE_COLOR = "#e2e8f0";
const DEFAULT_EDGE_WIDTH = 1;

function edgeColor(highlighted: boolean): VisEdge["color"] {
  return {
    color: highlighted ? "#0ea5e9" : DEFAULT_EDGE_COLOR,
    highlight: "#0ea5e9",
  };
}

/** Degrees from an edge list, for sizing where the payload does not send one. */
function degreesFrom(edges: Array<{ from: string; to: string }>): Map<string, number> {
  const degree = new Map<string, number>();
  edges.forEach((edge) => {
    degree.set(edge.from, (degree.get(edge.from) ?? 0) + 1);
    degree.set(edge.to, (degree.get(edge.to) ?? 0) + 1);
  });
  return degree;
}

function nodeTitle(name: string, type: string | undefined): string {
  return type ? `${name}（${type}）` : name;
}

/**
 * The platform overview's own shape, folded onto the canvas's.
 *
 * The overview has no ids: `graph.json` edges are `{source, target, relation,
 * evidence}` with no key of their own. Position within the payload is a
 * sufficient identity here and only here — `save_kg` dedupes on the relation
 * key, so the platform graph has no parallel edges for a positional id to
 * collide with. The subgraph does not get this shortcut; its ids come from the
 * backend.
 */
function overviewCanvas(data: KgGraphPayload): { nodes: VisNode[]; edges: VisEdge[] } {
  const edges: VisEdge[] = data.edges.map((edge, index) => ({
    id: `e${index}`,
    from: edge.source,
    to: edge.target,
    label: edge.relation,
    title: edge.evidence,
    color: edgeColor(false),
    width: DEFAULT_EDGE_WIDTH,
    baseColor: DEFAULT_EDGE_COLOR,
    baseWidth: DEFAULT_EDGE_WIDTH,
  }));
  const degree = degreesFrom(edges);
  return {
    nodes: data.nodes.map((node) => {
      const label = node.label ?? node.id;
      const { color, value } = nodeVisuals(node.type, degree.get(node.id) ?? 0);
      return {
        id: node.id,
        label,
        color,
        value,
        title: nodeTitle(label, node.type),
        baseColor: color,
        baseValue: value,
      };
    }),
    edges,
  };
}

/** A retrieved subgraph, already carrying the identity the canvas needs. */
function subgraphCanvas(payload: KgSubgraph): { nodes: VisNode[]; edges: VisEdge[] } {
  const focused = payload.focus_edge_id ?? null;
  const edges: VisEdge[] = payload.edges.map((edge) => {
    const highlighted = focused !== null && edge.id === focused;
    return {
      id: edge.id,
      from: edge.source,
      to: edge.target,
      label: edge.relation || undefined,
      title: edge.evidence || undefined,
      color: edgeColor(highlighted),
      width: highlighted ? 2 : DEFAULT_EDGE_WIDTH,
      baseColor: DEFAULT_EDGE_COLOR,
      baseWidth: DEFAULT_EDGE_WIDTH,
    };
  });
  const degree = degreesFrom(edges);
  return {
    nodes: payload.nodes.map((node) => {
      // The backend sends a degree over the *whole* graph; fall back to the
      // degree within this subgraph when it does not (community members, for
      // instance, arrive without one).
      const { color, value } = nodeVisuals(node.type, node.degree ?? degree.get(node.id) ?? 0);
      return {
        id: node.id,
        label: node.name,
        color,
        value,
        title: nodeTitle(node.name, node.type),
        baseColor: color,
        baseValue: value,
      };
    }),
    edges,
  };
}

export function KgViewPanel() {
  const { t } = useT();
  const shared = useKgHighlight();

  // The request the QA panel asked for. Absent outside a provider, or after the
  // highlight is cleared — both render the platform overview instead.
  const request = shared?.highlight?.request ?? null;
  const key = request ? requestKey(request) : null;
  const subgraphMode = request !== null;

  // The overview is only fetched when it is what gets drawn. Asking for 66
  // nodes it will not show would be a wasted round trip on the one path the
  // user is actually on.
  const overview = useApi<KgGraphPayload | null>(
    () => (subgraphMode ? Promise.resolve(null) : endpoints.knowledgeGraph.graph()),
    [subgraphMode]
  );

  const sub = useApi<KgSubgraph | null>(
    () =>
      request
        ? endpoints.knowledgeGraph.subgraph({
            nodes: request.nodes,
            community_ids: request.communityIds,
            include_neighbours: request.includeNeighbours,
            focus: request.focus,
          })
        : Promise.resolve(null),
    [key]
  );

  const containerRef = React.useRef<HTMLDivElement | null>(null);
  const networkRef = React.useRef<VisNetworkInstance | null>(null);
  const nodesRef = React.useRef<VisDataSet<VisNode> | null>(null);
  const edgesRef = React.useRef<VisDataSet<VisEdge> | null>(null);
  // Set when the canvas is (re)built so the highlight effect re-runs after a
  // rebuild: a request made while the QA tab was open has to survive arriving
  // at a panel that was unmounted the whole time.
  const [networkReady, setNetworkReady] = React.useState(false);
  const [visError, setVisError] = React.useState(false);
  const [selected, setSelected] = React.useState<Selection>(null);

  const subgraph = sub.data;

  // One payload, two shapes, one drawing. A subgraph that came back empty is
  // not a reason to fall back to the overview: drawing the whole platform graph
  // in answer to "here is what this answer used" would be a confident lie about
  // the answer's grounding.
  const canvas = React.useMemo((): { nodes: VisNode[]; edges: VisEdge[] } => {
    if (subgraphMode) return subgraph ? subgraphCanvas(subgraph) : { nodes: [], edges: [] };
    return overview.data ? overviewCanvas(overview.data) : { nodes: [], edges: [] };
  }, [subgraphMode, subgraph, overview.data]);

  // Build the network once the payload and the lazily injected vis-network
  // library are both available. State is written from the build and from the
  // rejection path only — never synchronously from the effect body.
  React.useEffect(() => {
    const container = containerRef.current;
    if (!container || canvas.nodes.length === 0) return;
    let disposed = false;

    const build = () => {
      const vis = getVis();
      if (disposed || !vis || !containerRef.current) return;

      // Our own DataSets, passed in, so a highlight can update items in place.
      // Letting vis build its own would leave nothing to address afterwards
      // short of rebuilding the graph and losing the layout.
      const nodesDs = new vis.DataSet<VisNode>(canvas.nodes);
      const edgesDs = new vis.DataSet<VisEdge>(canvas.edges);
      const network = new vis.Network(
        container,
        { nodes: nodesDs, edges: edgesDs },
        NETWORK_OPTIONS
      );

      networkRef.current = network;
      nodesRef.current = nodesDs;
      edgesRef.current = edgesDs;
      setNetworkReady(true);
      network.once("stabilizationIterationsDone", () => {
        network.fit({ animation: { duration: 300, easingFunction: "easeInOutQuad" } });
      });
      // A click is how a drawn thing becomes a readable one. Without this the
      // canvas was a picture: the evidence behind an edge was in the payload
      // and there was no way to reach it.
      network.on("click", (params) => {
        const node = params.nodes[0];
        const edge = params.edges[0];
        if (node) setSelected({ kind: "node", id: node });
        else if (edge) setSelected({ kind: "edge", id: edge });
        else setSelected(null);
      });
    };

    ensureVisLoaded()
      .then(build)
      .catch(() => {
        if (!disposed) setVisError(true);
      });

    return () => {
      disposed = true;
      networkRef.current?.destroy();
      networkRef.current = null;
      nodesRef.current = null;
      edgesRef.current = null;
      setNetworkReady(false);
    };
  }, [canvas]);

  // Lit ids come from the payload, not from an intersecting guess. With no
  // request, everything is lit, which is what "no highlight" has always looked
  // like; in subgraph mode the whole drawing *is* the retrieval, so only an
  // explicit focus — an edge, or an entity — narrows it further.
  React.useEffect(() => {
    if (!networkReady) return;
    if (!shared?.highlight) {
      clearHighlight(networkRef.current, nodesRef.current, edgesRef.current);
      return;
    }
    const { focus, focusNode } = shared.highlight.request;
    const focusEdgeId = subgraphMode ? subgraph?.focus_edge_id ?? null : null;
    const focusNodeId = focusNode ? `${focusNode.source_id}::${focusNode.name}` : null;

    let nodeIds = canvas.nodes.map((node) => node.id);
    let edgeIds = canvas.edges.map((edge) => edge.id);
    if (focusEdgeId && focus) {
      nodeIds = [`${focus.source_id}::${focus.source}`, `${focus.source_id}::${focus.target}`];
      edgeIds = [focusEdgeId];
    } else if (focusNodeId) {
      nodeIds = [focusNodeId];
      // The relations that connect it to what it was retrieved with, which is
      // what makes it locatable rather than merely visible.
      edgeIds = canvas.edges
        .filter((edge) => edge.from === focusNodeId || edge.to === focusNodeId)
        .map((edge) => edge.id);
    }

    applyHighlight(networkRef.current, nodesRef.current, edgesRef.current, {
      title: shared.highlight.title,
      nodeIds,
      edgeIds,
    });
  }, [networkReady, shared?.highlight, canvas, subgraph, subgraphMode]);

  // The detail block reads from the payload that was drawn, so it can never
  // describe something the canvas is not showing — e.g. after an expansion
  // replaced the drawing under a stale selection.
  const detail = React.useMemo(() => {
    if (!selected) return null;
    if (selected.kind === "node") {
      const node = canvas.nodes.find((n) => n.id === selected.id);
      if (!node) return null;
      const payloadNode = subgraph?.nodes.find((n) => n.id === selected.id);
      return {
        kind: "node" as const,
        label: node.label,
        type: payloadNode?.type,
        degree: payloadNode?.degree,
      };
    }
    const edge = canvas.edges.find((e) => e.id === selected.id);
    if (!edge) return null;
    const payloadEdge = subgraph?.edges.find((e) => e.id === selected.id);
    return {
      kind: "edge" as const,
      label: `${edge.from} → ${edge.to}`,
      relation: payloadEdge?.relation ?? edge.label,
      evidence: payloadEdge?.evidence ?? edge.title,
      sourceFile: payloadEdge?.source_file,
    };
  }, [selected, canvas, subgraph]);

  const downloads = [
    { name: "entities.csv", labelKey: "kg.downloadEntities" },
    { name: "relations.csv", labelKey: "kg.downloadRelations" },
    { name: "graph.json", labelKey: "kg.downloadGraph" },
  ];

  const sources: KgQaSourceInfo[] = subgraph?.sources ?? [];
  const loading = subgraphMode ? sub.loading : overview.loading;
  const error = subgraphMode ? sub.error : overview.error;
  const highlight = shared?.highlight ?? null;

  return (
    <div className="flex flex-col gap-6">
      {loading ? (
        <LoadingState rows={3} />
      ) : error ? (
        <ErrorState
          message={describeApiError(t, error)}
          onRetry={() => (subgraphMode ? sub.reload() : overview.reload())}
        />
      ) : (
        <>
          <div className="grid grid-cols-2 gap-3 lg:grid-cols-3">
            <StatCard label={t("kg.nodes")} value={canvas.nodes.length} icon={NodeMoveUpIcon} />
            <StatCard label={t("kg.edges")} value={canvas.edges.length} icon={AiNetworkIcon} />
            <StatCard
              label={t("kg.graphSource")}
              value={
                subgraphMode
                  ? sources.map((source) => translateKgSourceInfo(t, source)).join(" · ") || "—"
                  : translateKgSource(t, overview.data?.source ?? "none")
              }
            />
          </div>

          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <HugeiconsIcon icon={AiNetworkIcon} className="text-muted-foreground size-4" />
                {t("kg.graphCanvas")}
              </CardTitle>
            </CardHeader>
            <CardContent>
              {highlight ? (
                <div className="mb-3 flex flex-wrap items-center gap-2 rounded-md border border-sky-200 bg-sky-50 px-3 py-2 text-sm">
                  <span className="text-sky-900">
                    {subgraphMode
                      ? t("kg.subgraphBanner", { title: highlight.title })
                      : highlight.title}
                  </span>
                  <button
                    type="button"
                    onClick={() => shared?.setHighlight(null)}
                    className="text-sky-700 underline underline-offset-2 hover:text-sky-900"
                  >
                    {t("kg.clearHighlight")}
                  </button>
                </div>
              ) : null}

              {canvas.nodes.length === 0 ? (
                <p className="text-muted-foreground text-sm">
                  {subgraphMode ? t("kg.noAnswer") : t("kg.noGraph")}
                </p>
              ) : visError ? (
                <p className="text-muted-foreground text-sm">{t("kg.graphLoadFailed")}</p>
              ) : (
                <>
                  <div className="mb-3 flex flex-wrap items-center gap-2">
                    {(subgraph?.missing ?? []).length > 0 ? (
                      <Badge variant="outline" className="text-xs">
                        {t("kg.subgraphMissing", { count: subgraph?.missing?.length ?? 0 })}
                      </Badge>
                    ) : null}
                    {subgraph?.truncated ? (
                      <Badge variant="outline" className="text-xs">
                        {t("kg.subgraphTruncated")}
                      </Badge>
                    ) : null}
                    {(subgraph?.unresolved_communities ?? []).length > 0 ? (
                      <Badge variant="outline" className="text-xs">
                        {t("kg.subgraphUnknownCommunities", {
                          count: subgraph?.unresolved_communities?.length ?? 0,
                        })}
                      </Badge>
                    ) : null}
                    {subgraphMode && highlight && !request?.includeNeighbours ? (
                      <Button
                        variant="outline"
                        size="sm"
                        onClick={() =>
                          shared?.setHighlight({
                            title: highlight.title,
                            request: { ...highlight.request, includeNeighbours: true },
                          })
                        }
                      >
                        {t("kg.expandNeighbours")}
                      </Button>
                    ) : null}
                  </div>
                  <div
                    ref={containerRef}
                    className="relative h-[520px] w-full overflow-hidden rounded-md border bg-white"
                  />
                </>
              )}
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>{t("kg.detailTitle")}</CardTitle>
            </CardHeader>
            <CardContent>
              {!detail ? (
                <p className="text-muted-foreground text-sm">{t("kg.detailHint")}</p>
              ) : (
                <div className="flex flex-col gap-2 text-sm">
                  <div className="flex flex-wrap items-center gap-2">
                    <Badge variant="outline" className="text-xs">
                      {detail.kind === "node" ? t("kg.detailNode") : t("kg.detailEdge")}
                    </Badge>
                    <span className="font-medium">{detail.label}</span>
                    <button
                      type="button"
                      onClick={() => setSelected(null)}
                      className="text-muted-foreground underline underline-offset-2"
                    >
                      {t("kg.detailClear")}
                    </button>
                  </div>
                  {detail.kind === "node" ? (
                    <div className="text-muted-foreground flex flex-wrap gap-x-4 gap-y-1 text-xs">
                      {detail.type ? (
                        <span>
                          {t("kg.detailType")}：{detail.type}
                        </span>
                      ) : null}
                      {detail.degree != null ? (
                        <span>
                          {t("kg.detailDegree")}：{detail.degree}
                        </span>
                      ) : null}
                    </div>
                  ) : (
                    <>
                      {detail.relation ? (
                        <div>
                          <span className="text-muted-foreground">{t("kg.detailEdge")}：</span>
                          {detail.relation}
                        </div>
                      ) : null}
                      {detail.evidence ? (
                        <div>
                          <span className="text-muted-foreground">{t("kg.detailEvidence")}：</span>
                          {detail.evidence}
                        </div>
                      ) : null}
                      {detail.sourceFile ? (
                        <div className="text-muted-foreground text-xs">
                          {t("kg.sourceFile")}：{detail.sourceFile}
                        </div>
                      ) : null}
                    </>
                  )}
                </div>
              )}
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>{t("kg.downloadFiles")}</CardTitle>
            </CardHeader>
            <CardContent className="flex flex-wrap gap-2">
              {downloads.map((d) => (
                <button
                  key={d.name}
                  type="button"
                  onClick={() =>
                    downloadAuthenticated(endpoints.knowledgeGraph.downloadUrl(d.name), d.name).catch(
                      (err) => console.error("KG download failed:", err)
                    )
                  }
                  className="text-muted-foreground hover:bg-muted/40 inline-flex items-center gap-2 rounded-md border px-3 py-2 text-sm transition-colors"
                >
                  <Badge variant="outline" className="font-mono text-xs">
                    {d.name}
                  </Badge>
                  {t(d.labelKey)}
                </button>
              ))}
            </CardContent>
          </Card>
        </>
      )}
    </div>
  );
}
