"use client";

import { useT } from "@/lib/i18n/use-t";
import { useApi } from "@/lib/hooks/use-api";
import { endpoints } from "@/lib/api/endpoints";
import { translateKgSource } from "@/lib/domain";
import { LoadingState, ErrorState } from "@/components/waterexpert/ui-states";
import { StatCard } from "@/components/waterexpert/stat-card";
import { Badge } from "@/components/ui/badge";
import { HugeiconsIcon } from "@hugeicons/react";
import {
  Upload01Icon,
  Notebook01Icon,
  NodeMoveUpIcon,
  AiNetworkIcon,
  CheckmarkCircle01Icon,
  Cancel01Icon,
} from "@hugeicons/core-free-icons";

export function KgOverviewPanel() {
  const { t } = useT();
  const { data, loading, error, reload } = useApi(() => endpoints.knowledgeGraph.summary());

  return (
    <div className="flex flex-col gap-6">
      {loading ? (
        <LoadingState rows={3} />
      ) : error ? (
        <ErrorState error={error} onRetry={reload} />
      ) : data ? (
        <>
          <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
            <StatCard label={t("kg.uploads")} value={data.uploads ?? 0} icon={Upload01Icon} />
            <StatCard label={t("kg.texts")} value={data.texts ?? 0} icon={Notebook01Icon} />
            <StatCard label={t("kg.nodes")} value={data.node_count ?? 0} icon={NodeMoveUpIcon} />
            <StatCard label={t("kg.edges")} value={data.edge_count ?? 0} icon={AiNetworkIcon} />
          </div>

          <div className="flex flex-wrap items-center gap-2">
            <Badge variant="outline">
              {t("kg.sourceLabel")}: {translateKgSource(t, data.source)}
            </Badge>
            <Badge variant="outline">
              <HugeiconsIcon
                icon={data.llm_configured ? CheckmarkCircle01Icon : Cancel01Icon}
                className="text-muted-foreground size-3.5"
              />
              {data.llm_configured ? t("kg.llmConfigured") : t("kg.llmNotConfigured")}
            </Badge>
          </div>
        </>
      ) : null}
    </div>
  );
}
