"use client";

import { useT } from "@/lib/i18n/use-t";
import { translateScenario, translateRisk, riskBadgeVariant } from "@/lib/domain";
import { formatNumber, formatMaybeDate, formatPercent } from "@/lib/format";
import { Badge } from "@/components/ui/badge";
import { DataTable, type ColumnDef } from "@/components/waterexpert/data-table";
import type { ScenarioDay } from "@/lib/api/contracts";

export function ScenarioHighPriorityTable({ days }: { days: ScenarioDay[] }) {
  const { t } = useT();

  const columns: ColumnDef[] = [
    {
      key: "target_date",
      header: t("common.date"),
      render: (row) => (
        <span className="font-medium tabular-nums">{formatMaybeDate(row.target_date)}</span>
      ),
    },
    {
      key: "primary_scenario",
      header: t("scenario.primaryScenario"),
      render: (row) =>
        translateScenario(t, String(row.primary_scenario), String(row.primary_scenario_label ?? "")),
    },
    {
      key: "risk_band",
      header: t("scenario.riskBand"),
      render: (row) => {
        const risk = String(row.risk_band ?? "");
        return <Badge variant={riskBadgeVariant(risk)}>{translateRisk(t, risk)}</Badge>;
      },
    },
    {
      key: "primary_score",
      header: t("scenario.primaryScore"),
      render: (row) => formatNumber(row.primary_score),
    },
    {
      key: "predicted_critical_transition_prob",
      header: t("prediction.criticalTransition"),
      render: (row) => formatPercent(row.predicted_critical_transition_prob),
    },
    {
      key: "evidence_summary",
      header: t("scenario.evidence"),
      render: (row) => (
        <span className="text-muted-foreground line-clamp-2 max-w-[320px] text-xs">
          {String(row.evidence_summary ?? "—")}
        </span>
      ),
    },
  ];

  return <DataTable columns={columns} rows={days as unknown as Record<string, unknown>[]} rowKey={(r) => String(r.target_date ?? "")} />;
}

export function ScenarioCountBadges({ counts }: { counts: Record<string, number> }) {
  const { t } = useT();
  const entries = Object.entries(counts || {});
  if (entries.length === 0) return null;

  return (
    <div className="flex flex-wrap gap-2">
      {entries.map(([key, value]) => (
        <Badge key={key} variant="outline" className="gap-1.5">
          <span>{translateScenario(t, key)}</span>
          <span className="text-muted-foreground font-mono tabular-nums">{value}</span>
        </Badge>
      ))}
    </div>
  );
}
