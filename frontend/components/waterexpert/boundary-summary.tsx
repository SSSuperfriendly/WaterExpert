"use client";

import { useT } from "@/lib/i18n/use-t";
import { translateModel } from "@/lib/domain";
import { formatNumber, formatPercent } from "@/lib/format";
import { StatCard } from "@/components/waterexpert/stat-card";
import { DataTable, type ColumnDef } from "@/components/waterexpert/data-table";
import { EmptyState } from "@/components/waterexpert/ui-states";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import type { BoundarySummary } from "@/lib/api/contracts";

export function BoundarySummaryView({ data }: { data: BoundarySummary }) {
  const { t } = useT();

  const labels = (data.label_generation_summary ?? {}) as Record<string, unknown>;
  const models = data.models ?? {};
  const splits = ["test", "val", "train"];

  const modelEntries = Object.entries(models);
  const stat = (v: unknown) =>
    v && typeof v === "object" ? formatNumber((v as Record<string, unknown>).mean ?? v, 3) : formatNumber(v, 3);

  return (
    <div className="space-y-6">
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <StatCard label={t("boundary.sampledDays")} value={formatNumber(labels.sampled_days, 0)} />
        <StatCard
          label={t("boundary.positiveLabeledDays")}
          value={formatNumber(labels.positive_labeled_days, 0)}
        />
        <StatCard
          label={t("boundary.boundaryExtentRatio")}
          value={stat(labels.boundary_extent_ratio_stats)}
        />
        <StatCard label={t("boundary.waterFraction")} value={stat(labels.water_fraction_stats)} />
      </div>

      {typeof labels.label_semantics === "string" && labels.label_semantics && (
        <p className="text-muted-foreground text-sm leading-snug">
          <span className="font-medium text-foreground">{t("boundary.labelSemantics")}: </span>
          {labels.label_semantics}
        </p>
      )}

      {modelEntries.length === 0 ? (
        <EmptyState />
      ) : (
        <div className="overflow-x-auto">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>{t("boundary.model")}</TableHead>
                {splits.map((split) => (
                  <TableHead key={split} className="text-right capitalize">
                    {split}
                  </TableHead>
                ))}
              </TableRow>
            </TableHeader>
            <TableBody>
              {["accuracy", "precision", "recall", "f1"].map((metric) => (
                <TableRow key={metric}>
                  <TableCell className="font-medium">
                    {t(`boundary.${metric}`)}
                  </TableCell>
                  {splits.map((split) => {
                    const row: Record<string, unknown> = {};
                    for (const [model, splitMap] of Object.entries(models)) {
                      const m = (splitMap as Record<string, Record<string, number>>)[split];
                      if (m) row[model] = m[metric];
                    }
                    return (
                      <TableCell key={split} className="text-right">
                        {modelEntries.map(([model]) => {
                          const v = row[model];
                          return v === undefined ? null : (
                            <div key={model} className="text-xs">
                              <span className="text-muted-foreground">
                                {translateModel(t, model)}
                              </span>{" "}
                              <span className="font-mono tabular-nums">
                                {metric === "f1" ? formatNumber(v, 3) : formatPercent(v, 1)}
                              </span>
                            </div>
                          );
                        })}
                      </TableCell>
                    );
                  })}
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      )}

      {data.prediction_preview && data.prediction_preview.length > 0 && (
        <div className="space-y-2">
          <p className="text-sm font-medium">{t("boundary.predictionPreview")}</p>
          <BoundaryPreviewTable rows={data.prediction_preview as unknown as Record<string, unknown>[]} />
        </div>
      )}
    </div>
  );
}

function BoundaryPreviewTable({ rows }: { rows: Record<string, unknown>[] }) {
  const { t } = useT();
  const sample = rows[0] ?? {};
  const keys = Object.keys(sample).slice(0, 8);

  const columns: ColumnDef[] = keys.map((k) => ({
    key: k,
    header: k,
    render: (row) => {
      const v = row[k];
      return typeof v === "number" ? formatNumber(v, 3) : String(v ?? "—");
    },
  }));

  return <DataTable columns={columns} rows={rows} rowKey={(r, i) => String(i)} />;
}
