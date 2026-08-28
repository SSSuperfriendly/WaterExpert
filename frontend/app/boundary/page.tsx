"use client";

import { useT } from "@/lib/i18n/use-t";
import { useApi } from "@/lib/hooks/use-api";
import { endpoints } from "@/lib/api/endpoints";
import { useArtifactScope } from "@/lib/hooks/use-artifact-scope";
import { AppShell } from "@/components/waterexpert/app-shell";
import { LoadingState, ErrorState } from "@/components/waterexpert/ui-states";
import { BoundarySummaryView } from "@/components/waterexpert/boundary-summary";
import { Card, CardContent } from "@/components/ui/card";

export default function BoundaryPage() {
  const { t } = useT();
  const scope = useArtifactScope();
  const { data, loading, error, reload } = useApi(() => endpoints.boundary(scope), [scope]);

  return (
    <AppShell title={t("nav.boundary")}>

      {loading ? (
        <LoadingState />
      ) : error ? (
        <ErrorState error={error} onRetry={reload} />
      ) : data ? (
        <Card>
          <CardContent className="pt-6">
            <BoundarySummaryView data={data} />
          </CardContent>
        </Card>
      ) : null}
    </AppShell>
  );
}
