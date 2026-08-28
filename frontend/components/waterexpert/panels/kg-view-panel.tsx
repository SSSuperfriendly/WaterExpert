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

const VIS_SCRIPT = "/ui/lib/vis-network/vis-network.min.js";
const VIS_CSS = "/ui/lib/vis-network/vis-network.css";

const TYPE_COLORS: Record<string, string> = {
  水体对象: "#0ea5e9",
  清澈度指标: "#10b981",
  水质因子: "#f59e0b",
  环境因子: "#8b5cf6",
  监测方法: "#ec4899",
  水质过程: "#14b8a6",
  水质生物组分: "#ef4444",
};
const DEFAULT_COLOR = "#64748b";

type VisNetworkInstance = {
  destroy: () => void;
  fit: (options?: Record<string, unknown>) => void;
  once: (event: string, handler: () => void) => void;
};
type VisNetworkLib = {
  Network: new (
    container: HTMLElement,
    data: {
      nodes: Array<{ id: string; label: string; color: string; value: number }>;
      edges: Array<{ from: string; to: string; label?: string; title?: string }>;
    },
    options: Record<string, unknown>
  ) => VisNetworkInstance;
};

function getVis(): VisNetworkLib | undefined {
  return (window as unknown as { vis?: VisNetworkLib }).vis;
}

export function KgViewPanel() {
  const { t } = useT();
  const { data, loading, error, reload } = useApi(() => endpoints.knowledgeGraph.graph());

  const containerRef = React.useRef<HTMLDivElement | null>(null);
  const networkRef = React.useRef<VisNetworkInstance | null>(null);
  const [visReady, setVisReady] = React.useState(false);

  // Inject the self-hosted vis-network script + stylesheet once.
  React.useEffect(() => {
    let script: HTMLScriptElement | null = null;

    if (!document.querySelector(`link[href="${VIS_CSS}"]`)) {
      const link = document.createElement("link");
      link.rel = "stylesheet";
      link.href = VIS_CSS;
      document.head.appendChild(link);
    }

    if (getVis()) {
      setVisReady(true);
      return;
    }

    script = document.createElement("script");
    script.src = VIS_SCRIPT;
    script.async = true;
    script.onload = () => setVisReady(true);
    script.onerror = () => setVisReady(false);
    document.head.appendChild(script);
  }, []);

  // Build the network once both the library and the graph payload are ready.
  React.useEffect(() => {
    const vis = getVis();
    const container = containerRef.current;
    if (!visReady || !vis || !container || !data || data.nodes.length === 0) return;

    const degree = new Map<string, number>();
    data.nodes.forEach((n) => degree.set(n.id, 0));
    data.edges.forEach((e) => {
      degree.set(e.source, (degree.get(e.source) ?? 0) + 1);
      degree.set(e.target, (degree.get(e.target) ?? 0) + 1);
    });

    const nodes = data.nodes.map((n) => ({
      id: n.id,
      label: n.label ?? n.id,
      color: TYPE_COLORS[n.type ?? ""] ?? DEFAULT_COLOR,
      value: 1 + (degree.get(n.id) ?? 0) * 2,
    }));
    const edges = data.edges.map((e) => ({
      from: e.source,
      to: e.target,
      label: e.relation,
      title: e.evidence,
    }));

    const network = new vis.Network(
      container,
      { nodes, edges },
      {
        autoResize: true,
        nodes: {
          shape: "dot",
          font: { size: 14, face: "sans-serif", color: "#334155" },
        },
        edges: {
          arrows: { to: { enabled: true, scaleFactor: 0.6 } },
          color: { color: "#cbd5e1", highlight: "#0ea5e9" },
          font: { size: 10, color: "#64748b", align: "middle" },
          smooth: { type: "continuous" },
        },
        physics: {
          stabilization: { iterations: 200 },
          barnesHut: {
            gravitationalConstant: -8000,
            springLength: 140,
            springConstant: 0.04,
            damping: 0.09,
          },
        },
        interaction: { hover: true, tooltipDelay: 120 },
      }
    );

    networkRef.current = network;
    network.once("stabilizationIterationsDone", () => {
      network.fit({ animation: { duration: 300, easingFunction: "easeInOutQuad" } });
    });

    return () => {
      networkRef.current?.destroy();
      networkRef.current = null;
    };
  }, [visReady, data]);

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
              ) : (
                <div
                  ref={containerRef}
                  className="relative h-[520px] w-full overflow-hidden rounded-md border bg-white"
                />
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
