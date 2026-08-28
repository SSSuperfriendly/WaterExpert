"use client";

import * as React from "react";
import { useT } from "@/lib/i18n/use-t";
import { useApi } from "@/lib/hooks/use-api";
import { endpoints } from "@/lib/api/endpoints";
import { translateFactor } from "@/lib/domain";
import { formatNumber } from "@/lib/format";
import { AppShell } from "@/components/waterexpert/app-shell";
import { LoadingState, ErrorState, EmptyState } from "@/components/waterexpert/ui-states";
import { DataTable, type ColumnDef } from "@/components/waterexpert/data-table";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

export default function SensitivityPage() {
  const { t } = useT();
  const { data, loading, error, reload } = useApi(() => endpoints.sensitivity());

  const sobol = data?.sobol ?? {};
  const topFactors = (sobol.top_factors ?? []) as Record<string, unknown>[];
  const counterfactual = (data?.counterfactual ?? []) as Record<string, unknown>[];
  const joint = (data?.joint_counterfactual ?? []) as Record<string, unknown>[];

  const factorColumns: ColumnDef[] = [
    {
      key: "factor",
      header: t("sensitivity.factor"),
      render: (row) => (
        <span className="font-medium">{translateFactor(t, String(row.factor), String(row.factor_label ?? ""))}</span>
      ),
    },
    {
      key: "first_order_index",
      header: t("sensitivity.firstOrder"),
      render: (row) => formatNumber(row.first_order_index, 4),
    },
    {
      key: "total_order_index",
      header: t("sensitivity.totalOrder"),
      render: (row) => formatNumber(row.total_order_index, 4),
    },
    {
      key: "interaction_strength",
      header: t("sensitivity.interactionStrength"),
      render: (row) => formatNumber(row.interaction_strength, 4),
    },
  ];

  const counterfactualColumns: ColumnDef[] = React.useMemo(() => {
    const sample = counterfactual[0] ?? {};
    const keys = Object.keys(sample).slice(0, 8);
    return keys.map((k) => ({
      key: k,
      header: k,
      render: (row: Record<string, unknown>) => {
        const v = row[k];
        return typeof v === "number" ? formatNumber(v, 3) : String(v ?? "—");
      },
    }));
  }, [counterfactual]);

  return (
    <AppShell title={t("nav.sensitivity")}>

      {loading ? (
        <LoadingState />
      ) : error ? (
        <ErrorState message={error} onRetry={reload} />
      ) : data ? (
        <>
          <Card>
            <CardHeader>
              <CardTitle>{t("sensitivity.sobolIndices")}</CardTitle>
              <p className="text-muted-foreground text-xs">
                {t("sensitivity.sampleCount")}: {formatNumber(sobol.sample_count, 0)} ·{" "}
                {t("sensitivity.response")}: {String(sobol.response ?? "—")}
              </p>
            </CardHeader>
            <CardContent>
              {topFactors.length > 0 ? (
                <DataTable
                  columns={factorColumns}
                  rows={topFactors}
                  rowKey={(r, i) => String(r.factor ?? i)}
                />
              ) : (
                <EmptyState />
              )}
            </CardContent>
          </Card>

          {counterfactual.length > 0 && (
            <Card>
              <CardHeader>
                <CardTitle>{t("sensitivity.counterfactual")}</CardTitle>
              </CardHeader>
              <CardContent>
                <DataTable columns={counterfactualColumns} rows={counterfactual} rowKey={(r, i) => String(i)} />
              </CardContent>
            </Card>
          )}

          {joint.length > 0 && (
            <Card>
              <CardHeader>
                <CardTitle>{t("sensitivity.jointCounterfactual")}</CardTitle>
              </CardHeader>
              <CardContent>
                <ul className="space-y-2">
                  {joint.slice(0, 10).map((row, i) => (
                    <li key={i} className="rounded-md border px-3 py-2 text-sm">
                      <span className="text-muted-foreground font-mono text-xs">
                        {JSON.stringify(row)}
                      </span>
                    </li>
                  ))}
                </ul>
              </CardContent>
            </Card>
          )}
        </>
      ) : null}
    </AppShell>
  );
}
