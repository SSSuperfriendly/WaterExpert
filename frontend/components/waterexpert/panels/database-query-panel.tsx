"use client";

import * as React from "react";
import { useT } from "@/lib/i18n/use-t";
import { useApi } from "@/lib/hooks/use-api";
import { endpoints } from "@/lib/api/endpoints";
import { formatNumber } from "@/lib/format";
import { DataTable, type ColumnDef } from "@/components/waterexpert/data-table";
import { LoadingState, ErrorState } from "@/components/waterexpert/ui-states";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import { HugeiconsIcon } from "@hugeicons/react";
import { Search01Icon } from "@hugeicons/core-free-icons";

const PAGE_SIZE = 50;

export function DatabaseQueryPanel() {
  const { t } = useT();

  const [filters, setFilters] = React.useState({
    station_code: "",
    keyword: "",
    start_date: "",
    end_date: "",
  });
  const [page, setPage] = React.useState(1);
  const [submitted, setSubmitted] = React.useState(false);

  const query = useApi(
    () =>
      endpoints.query({
        station_code: filters.station_code || undefined,
        keyword: filters.keyword || undefined,
        start_date: filters.start_date || undefined,
        end_date: filters.end_date || undefined,
        limit: PAGE_SIZE,
        offset: (page - 1) * PAGE_SIZE,
      }),
    [submitted, page]
  );

  const runSearch = (e: React.FormEvent) => {
    e.preventDefault();
    setPage(1);
    setSubmitted((s) => !s);
  };

  const result = query.data;
  const columns: ColumnDef[] = React.useMemo(() => {
    const sample = result?.rows?.[0] ?? {};
    const keys = result?.columns ?? Object.keys(sample);
    return keys.slice(0, 12).map((key) => ({
      key,
      header: key,
      render: (row: Record<string, unknown>) => {
        const v = row[key];
        if (v === null || v === undefined || v === "") return "—";
        if (typeof v === "number") return formatNumber(v, 2);
        return String(v);
      },
    }));
  }, [result]);

  return (
    <div className="flex flex-col gap-6">
      <Card>
        <CardHeader>
          <CardTitle>{t("database.filters")}</CardTitle>
        </CardHeader>
        <CardContent>
          <form onSubmit={runSearch} className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4">
            <div className="space-y-1.5">
              <Label>{t("database.stationCode")}</Label>
              <Input
                value={filters.station_code}
                onChange={(e) => setFilters((f) => ({ ...f, station_code: e.target.value }))}
                placeholder="2586"
              />
            </div>
            <div className="space-y-1.5">
              <Label>{t("database.keyword")}</Label>
              <Input
                value={filters.keyword}
                onChange={(e) => setFilters((f) => ({ ...f, keyword: e.target.value }))}
              />
            </div>
            <div className="space-y-1.5">
              <Label>{t("database.startDate")}</Label>
              <Input
                type="date"
                value={filters.start_date}
                onChange={(e) => setFilters((f) => ({ ...f, start_date: e.target.value }))}
              />
            </div>
            <div className="space-y-1.5">
              <Label>{t("database.endDate")}</Label>
              <Input
                type="date"
                value={filters.end_date}
                onChange={(e) => setFilters((f) => ({ ...f, end_date: e.target.value }))}
              />
            </div>
            <div className="sm:col-span-2 lg:col-span-4">
              <Button type="submit">
                <HugeiconsIcon icon={Search01Icon} className="size-4" />
                {t("common.search")}
              </Button>
            </div>
          </form>
        </CardContent>
      </Card>

      <Card>
        <CardHeader className="flex-row items-center justify-between">
          <CardTitle>{t("database.columns")}</CardTitle>
          {result && (
            <div className="flex gap-2">
              <Badge variant="outline">
                {t("database.matchedRows")}: {formatNumber(result.matched_rows, 0)}
              </Badge>
              <Badge variant="outline">
                {t("database.returnedRows")}: {formatNumber(result.returned_rows, 0)}
              </Badge>
            </div>
          )}
        </CardHeader>
        <CardContent className="space-y-4">
          {query.loading ? (
            <LoadingState />
          ) : query.error ? (
            <ErrorState message={query.error} onRetry={query.reload} />
          ) : result && result.rows && result.rows.length > 0 ? (
            <>
              <DataTable
                columns={columns}
                rows={result.rows}
                rowKey={(r, i) => String(i)}
                emptyHint={t("database.emptyResult")}
              />
              {result.pagination && result.pagination.total_pages > 1 && (
                <div className="flex items-center justify-between gap-3">
                  <Button
                    variant="outline"
                    size="sm"
                    disabled={!result.pagination.has_previous}
                    onClick={() => setPage((p) => Math.max(1, p - 1))}
                  >
                    {t("database.previous")}
                  </Button>
                  <span className="text-muted-foreground text-xs">
                    {t("database.page")} {result.pagination.page} / {result.pagination.total_pages}
                  </span>
                  <Button
                    variant="outline"
                    size="sm"
                    disabled={!result.pagination.has_next}
                    onClick={() => setPage((p) => p + 1)}
                  >
                    {t("database.next")}
                  </Button>
                </div>
              )}
            </>
          ) : (
            <p className="text-muted-foreground text-sm">{t("database.emptyResult")}</p>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
