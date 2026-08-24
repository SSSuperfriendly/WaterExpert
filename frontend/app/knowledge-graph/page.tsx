"use client";

import Link from "next/link";
import { useT } from "@/lib/i18n/use-t";
import { useApi } from "@/lib/hooks/use-api";
import { endpoints } from "@/lib/api/endpoints";
import { AppShell } from "@/components/waterexpert/app-shell";
import { PageHeading, LoadingState, ErrorState } from "@/components/waterexpert/ui-states";
import { StatCard } from "@/components/waterexpert/stat-card";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { HugeiconsIcon } from "@hugeicons/react";
import {
  Book01Icon,
  Upload01Icon,
  Notebook01Icon,
  NodeMoveUpIcon,
  Search01Icon,
  AiNetworkIcon,
  CheckmarkCircle01Icon,
  Cancel01Icon,
} from "@hugeicons/core-free-icons";

const ENTRIES = [
  { href: "/knowledge-graph/upload", labelKey: "nav.kgUpload", icon: Upload01Icon },
  { href: "/knowledge-graph/preprocess", labelKey: "nav.kgPreprocess", icon: Notebook01Icon },
  { href: "/knowledge-graph/build", labelKey: "nav.kgBuild", icon: NodeMoveUpIcon },
  { href: "/knowledge-graph/qa", labelKey: "nav.kgQa", icon: Search01Icon },
  { href: "/knowledge-graph/view", labelKey: "nav.kgView", icon: AiNetworkIcon },
];

export default function KnowledgeGraphOverviewPage() {
  const { t } = useT();
  const { data, loading, error, reload } = useApi(() => endpoints.knowledgeGraph.summary());

  const sourceKey =
    data?.source === "runtime"
      ? "kg.sourceRuntime"
      : data?.source === "baseline"
        ? "kg.sourceBaseline"
        : "kg.sourceNone";

  return (
    <AppShell title={t("nav.kgOverview")}>
      <PageHeading title={t("kg.overviewTitle")} subtitle={t("kg.overviewSubtitle")} />

      {loading ? (
        <LoadingState rows={3} />
      ) : error ? (
        <ErrorState message={error} onRetry={reload} />
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
              {t("kg.source")}: {t(sourceKey)}
            </Badge>
            <Badge variant="outline">
              <HugeiconsIcon
                icon={data.llm_configured ? CheckmarkCircle01Icon : Cancel01Icon}
                className="text-muted-foreground size-3.5"
              />
              {data.llm_configured ? t("kg.llmConfigured") : t("kg.llmNotConfigured")}
            </Badge>
          </div>

          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <HugeiconsIcon icon={Book01Icon} className="text-muted-foreground size-4" />
                {t("nav.knowledgeGraph")}
              </CardTitle>
            </CardHeader>
            <CardContent>
              <p className="text-muted-foreground mb-4 text-sm">{t("kg.pipeline")}</p>
              <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
                {ENTRIES.map((entry) => (
                  <Link
                    key={entry.href}
                    href={entry.href}
                    className="hover:bg-muted/40 flex items-center gap-3 rounded-lg border p-3 transition-colors"
                  >
                    <HugeiconsIcon icon={entry.icon} className="text-muted-foreground size-5" />
                    <span className="text-sm font-medium">{t(entry.labelKey)}</span>
                  </Link>
                ))}
              </div>
            </CardContent>
          </Card>
        </>
      ) : null}
    </AppShell>
  );
}
