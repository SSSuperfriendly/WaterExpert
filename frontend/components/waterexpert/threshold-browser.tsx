"use client";

import { useT } from "@/lib/i18n/use-t";
import { formatNumber } from "@/lib/format";
import { DataTable, type ColumnDef } from "@/components/waterexpert/data-table";
import { EmptyState } from "@/components/waterexpert/ui-states";
import type { ThresholdNode } from "@/lib/api/contracts";

function thresholdColumns(t: ReturnType<typeof useT>["t"], contextual: boolean): ColumnDef[] {
  const cols: ColumnDef[] = [
    {
      key: "agent_label",
      header: t("thresholds.feature"),
      render: (row) => (
        <span className="font-medium">
          {String(row.agent_label ?? row.feature ?? "—")}
        </span>
      ),
    },
    {
      key: "threshold",
      header: t("thresholds.threshold"),
      render: (row) => (
        <span className="font-mono tabular-nums">
          {formatNumber(row.threshold, 3)}{" "}
          <span className="text-muted-foreground text-xs">{String(row.unit ?? "")}</span>
        </span>
      ),
    },
    {
      key: "r2_gain",
      header: t("thresholds.r2Gain"),
      render: (row) => formatNumber(row.r2_gain, 3),
    },
    {
      key: "response_jump",
      header: t("thresholds.responseJump"),
      render: (row) => formatNumber(row.response_jump, 3),
    },
    {
      key: "interpretation",
      header: t("thresholds.interpretation"),
      render: (row) => (
        <span className="text-muted-foreground line-clamp-2 max-w-[320px] text-xs">
          {String(row.interpretation ?? "—")}
        </span>
      ),
    },
  ];

  if (contextual) {
    cols.splice(1, 0, {
      key: "context",
      header: t("thresholds.context"),
      render: (row) => (
        <span className="text-xs">
          {String(row.context ?? "")} {row.context_type ? `(${String(row.context_type)})` : ""}
        </span>
      ),
    });
  }

  return cols;
}

export function ThresholdBrowser({
  nodes,
  contextualNodes,
}: {
  nodes: ThresholdNode[];
  contextualNodes: ThresholdNode[];
}) {
  const { t } = useT();
  const hasNodes = nodes && nodes.length > 0;
  const hasContextual = contextualNodes && contextualNodes.length > 0;

  if (!hasNodes && !hasContextual) {
    return <EmptyState />;
  }

  return (
    <div className="space-y-6">
      {hasNodes && (
        <div className="space-y-2">
          <p className="text-sm font-medium">{t("thresholds.thresholdNodes")}</p>
          <DataTable
            columns={thresholdColumns(t, false)}
            rows={nodes as unknown as Record<string, unknown>[]}
            rowKey={(r) => String(r.node_id ?? r.feature ?? "")}
          />
        </div>
      )}
      {hasContextual && (
        <div className="space-y-2">
          <p className="text-sm font-medium">{t("thresholds.contextualThresholds")}</p>
          <DataTable
            columns={thresholdColumns(t, true)}
            rows={contextualNodes as unknown as Record<string, unknown>[]}
            rowKey={(r, i) => String(r.node_id ?? i)}
          />
        </div>
      )}
    </div>
  );
}
