"use client";

import * as React from "react";
import { useT } from "@/lib/i18n/use-t";
import { useApi } from "@/lib/hooks/use-api";
import { endpoints } from "@/lib/api/endpoints";
import { downloadAuthenticated } from "@/lib/api/client";
import { translateKgSource } from "@/lib/domain";
import { LoadingState, ErrorState } from "@/components/waterexpert/ui-states";
import { StatCard } from "@/components/waterexpert/stat-card";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { HugeiconsIcon } from "@hugeicons/react";
import { AiNetworkIcon, NodeMoveUpIcon } from "@hugeicons/core-free-icons";
import {
  applyHighlight,
  clearHighlight,
  edgeId,
  ensureVisLoaded,
  getVis,
  NETWORK_OPTIONS,
  nodeVisuals,
  type VisDataSet,
  type VisEdge,
  type VisNetworkInstance,
  type VisNode,
} from "@/lib/kg/vis-network";
import { useKgHighlight } from "@/lib/kg/highlight-context";

export function KgViewPanel() {
  const { t } = useT();
  const { data, loading, error, reload } = useApi(() => endpoints.knowledgeGraph.graph());
  const shared = useKgHighlight();

  const containerRef = React.useRef<HTMLDivElement | null>(null);
  const networkRef = React.useRef<VisNetworkInstance | null>(null);
  const nodesRef = React.useRef<VisDataSet<VisNode> | null>(null);
  const edgesRef = React.useRef<VisDataSet<VisEdge> | null>(null);
  // Bumped when the canvas is (re)built, so the highlight effect re-runs after
  // a rebuild: a highlight set while the QA tab was open must survive being
  // carried back to a panel that was unmounted the whole time.
  const [networkReady, setNetworkReady] = React.useState(false);
  const [visError, setVisError] = React.useState(false);

  // Build the network once the payload and the lazily injected vis-network
  // library are both available. The build runs after the inject promise
  // resolves; state is only written from the rejection path.
  React.useEffect(() => {
    const container = containerRef.current;
    if (!container || !data || data.nodes.length === 0) return;
    let disposed = false;

    const build = () => {
      const vis = getVis();
      if (disposed || !vis || !containerRef.current) return;

      const degree = new Map<string, number>();
      data.nodes.forEach((n) => degree.set(n.id, 0));
      data.edges.forEach((e) => {
        degree.set(e.source, (degree.get(e.source) ?? 0) + 1);
        degree.set(e.target, (degree.get(e.target) ?? 0) + 1);
      });

      const nodes: VisNode[] = data.nodes.map((n) => {
        const { color, value } = nodeVisuals(n.type, degree.get(n.id) ?? 0);
        return { id: n.id, label: n.label ?? n.id, color, value, baseColor: color, baseValue: value };
      });
      const edges: VisEdge[] = data.edges.map((e) => ({
        id: edgeId(e.source, e.target),
        from: e.source,
        to: e.target,
        label: e.relation,
        title: e.evidence,
        color: { color: "#e2e8f0", highlight: "#0ea5e9" },
        width: 1,
        baseColor: "#e2e8f0",
        baseWidth: 1,
      }));

      // Our own DataSets, passed in, so a highlight can update items in place.
      // Letting vis build its own would leave nothing to address afterwards
      // short of rebuilding the graph and losing the layout.
      const nodesDs = new vis.DataSet<VisNode>(nodes);
      const edgesDs = new vis.DataSet<VisEdge>(edges);
      const network = new vis.Network(container, { nodes: nodesDs, edges: edgesDs }, NETWORK_OPTIONS);

      networkRef.current = network;
      nodesRef.current = nodesDs;
      edgesRef.current = edgesDs;
      setNetworkReady(true);
      network.once("stabilizationIterationsDone", () => {
        network.fit({ animation: { duration: 300, easingFunction: "easeInOutQuad" } });
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
  }, [data]);

  React.useEffect(() => {
    if (!networkReady) return;
    if (shared?.highlight) {
      applyHighlight(networkRef.current, nodesRef.current, edgesRef.current, shared.highlight);
    } else {
      clearHighlight(networkRef.current, nodesRef.current, edgesRef.current);
    }
  }, [networkReady, shared?.highlight]);

  const downloads = [
    { name: "entities.csv", labelKey: "kg.downloadEntities" },
    { name: "relations.csv", labelKey: "kg.downloadRelations" },
    { name: "graph.json", labelKey: "kg.downloadGraph" },
  ];

  return (
    <div className="flex flex-col gap-6">
      {loading ? (
        <LoadingState rows={3} />
      ) : error ? (
        <ErrorState error={error} onRetry={reload} />
      ) : data ? (
        <>
          <div className="grid grid-cols-2 gap-3 lg:grid-cols-3">
            <StatCard label={t("kg.nodes")} value={data.node_count ?? 0} icon={NodeMoveUpIcon} />
            <StatCard label={t("kg.edges")} value={data.edge_count ?? 0} icon={AiNetworkIcon} />
            <StatCard label={t("kg.sourceLabel")} value={translateKgSource(t, data.source)} />
          </div>

          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <HugeiconsIcon icon={AiNetworkIcon} className="text-muted-foreground size-4" />
                {t("kg.graphCanvas")}
              </CardTitle>
            </CardHeader>
            <CardContent>
              {data.nodes.length === 0 ? (
                <p className="text-muted-foreground text-sm">{t("kg.noGraph")}</p>
              ) : visError ? (
                <p className="text-muted-foreground text-sm">{t("kg.graphLoadFailed")}</p>
              ) : (
                <>
                  {shared?.highlight ? (
                    <div className="mb-3 flex flex-wrap items-center gap-2 rounded-md border border-sky-200 bg-sky-50 px-3 py-2 text-sm">
                      <span className="text-sky-900">{shared.highlight.title}</span>
                      <button
                        type="button"
                        onClick={() => shared.setHighlight(null)}
                        className="text-sky-700 underline underline-offset-2 hover:text-sky-900"
                      >
                        {t("kg.clearHighlight")}
                      </button>
                    </div>
                  ) : null}
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
              <CardTitle>{t("kg.downloadFiles")}</CardTitle>
            </CardHeader>
            <CardContent className="flex flex-wrap gap-2">
              {downloads.map((d) => (
                <button
                  key={d.name}
                  type="button"
                  onClick={() =>
                    downloadAuthenticated(
                      endpoints.knowledgeGraph.downloadUrl(d.name),
                      d.name
                    ).catch((err) => console.error("KG download failed:", err))
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
      ) : null}
    </div>
  );
}
