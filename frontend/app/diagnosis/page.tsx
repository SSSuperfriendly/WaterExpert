"use client";

import { useT } from "@/lib/i18n/use-t";
import { useApi } from "@/lib/hooks/use-api";
import { endpoints } from "@/lib/api/endpoints";
import { AppShell } from "@/components/waterexpert/app-shell";
import { LoadingState, ErrorState } from "@/components/waterexpert/ui-states";
import { DriverDiagnosis } from "@/components/waterexpert/driver-diagnosis";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { formatNumber } from "@/lib/format";
import { translateDomain } from "@/lib/domain";

export default function DiagnosisPage() {
  const { t } = useT();
  const { data, loading, error, reload } = useApi(() => endpoints.diagnostics());

  const decomposition = (data?.process_decomposition ?? []) as Record<string, unknown>[];

  return (
    <AppShell title={t("nav.diagnosis")}>

      {loading ? (
        <LoadingState />
      ) : error ? (
        <ErrorState message={error} onRetry={reload} />
      ) : data ? (
        <>
          <DriverDiagnosis data={data} />

          {decomposition.length > 0 && (
            <Card>
              <CardHeader>
                <CardTitle>{t("diagnosis.processDecomposition")}</CardTitle>
              </CardHeader>
              <CardContent>
                <ul className="grid grid-cols-1 gap-2 sm:grid-cols-2">
                  {decomposition.map((row, i) => (
                    <li
                      key={i}
                      className="flex items-center justify-between rounded-md border px-3 py-2 text-sm"
                    >
                      <span className="truncate">
                        {String(row.label ?? row.process ?? row.name ?? "—")}
                      </span>
                      <span className="font-mono tabular-nums">
                        {formatNumber(row.contribution ?? row.value, 3)}
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
