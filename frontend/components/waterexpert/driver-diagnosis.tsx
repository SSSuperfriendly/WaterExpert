"use client";

import * as React from "react";
import { useT } from "@/lib/i18n/use-t";
import { translateFactor, translateDomain } from "@/lib/domain";
import { formatNumber } from "@/lib/format";
import type { DiagnosticsPayload } from "@/lib/api/contracts";

function BarList({
  items,
  valueKey,
  color,
}: {
  items: Record<string, unknown>[];
  valueKey: string;
  color: string;
}) {
  if (!items || items.length === 0) return null;
  const max = Math.max(...items.map((it) => Number(it[valueKey] ?? 0)), 0);

  return (
    <ul className="space-y-2.5">
      {items.map((it, i) => {
        const label = it.feature_label ? String(it.feature_label) : String(it.feature ?? "");
        const value = Number(it[valueKey] ?? 0);
        const width = max > 0 ? Math.max(4, (value / max) * 100) : 0;
        return (
          <li key={i} className="space-y-1">
            <div className="flex items-center justify-between gap-3 text-sm">
              <span className="min-w-0 truncate">{label}</span>
              <span className="font-mono text-xs tabular-nums">{formatNumber(value, 3)}</span>
            </div>
            <div className="bg-muted h-1.5 w-full overflow-hidden rounded-full">
              <div
                className={`h-full rounded-full ${color}`}
                style={{ width: `${width}%` }}
              />
            </div>
          </li>
        );
      })}
    </ul>
  );
}

export function DriverDiagnosis({ data }: { data: DiagnosticsPayload }) {
  const { t } = useT();

  const drivers = (data.top_driver_features ?? []).map((f) => ({ ...f })) as Record<string, unknown>[];
  const inhibitors = (data.top_inhibitor_features ?? []).map((f) => ({ ...f })) as Record<string, unknown>[];
  const driverDomains = data.top_driver_domains ?? [];
  const inhibitorDomains = data.top_inhibitor_domains ?? [];

  return (
    <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
      <div className="rounded-lg border p-4">
        <p className="mb-3 text-sm font-medium">{t("diagnosis.topDrivers")}</p>
        <BarList items={drivers} valueKey="driver_score" color="bg-rose-500" />
        {driverDomains.length > 0 && (
          <div className="mt-5 border-t pt-4">
            <p className="text-muted-foreground mb-2 text-xs font-medium">
              {t("diagnosis.topDriverDomains")}
            </p>
            <ul className="flex flex-wrap gap-2">
              {driverDomains.map((d, i) => (
                <li
                  key={i}
                  className="bg-muted text-muted-foreground rounded-md px-2 py-1 text-xs"
                >
                  {translateDomain(t, d.domain, d.domain_label)} · {formatNumber(d.score, 3)}
                </li>
              ))}
            </ul>
          </div>
        )}
      </div>

      <div className="rounded-lg border p-4">
        <p className="mb-3 text-sm font-medium">{t("diagnosis.topInhibitors")}</p>
        <BarList items={inhibitors} valueKey="inhibitor_score" color="bg-emerald-500" />
        {inhibitorDomains.length > 0 && (
          <div className="mt-5 border-t pt-4">
            <p className="text-muted-foreground mb-2 text-xs font-medium">
              {t("diagnosis.topInhibitorDomains")}
            </p>
            <ul className="flex flex-wrap gap-2">
              {inhibitorDomains.map((d, i) => (
                <li
                  key={i}
                  className="bg-muted text-muted-foreground rounded-md px-2 py-1 text-xs"
                >
                  {translateDomain(t, d.domain, d.domain_label)} · {formatNumber(d.score, 3)}
                </li>
              ))}
            </ul>
          </div>
        )}
      </div>
    </div>
  );
}
