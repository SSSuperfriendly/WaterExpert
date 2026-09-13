"use client";

import * as React from "react";
import { useT } from "@/lib/i18n/use-t";
import { AppShell } from "@/components/waterexpert/app-shell";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import { KgOverviewPanel } from "@/components/waterexpert/panels/kg-overview-panel";
import { KgUploadPanel } from "@/components/waterexpert/panels/kg-upload-panel";
import { KgPreprocessPanel } from "@/components/waterexpert/panels/kg-preprocess-panel";
import { KgBuildPanel } from "@/components/waterexpert/panels/kg-build-panel";
import { KgViewPanel } from "@/components/waterexpert/panels/kg-view-panel";
import { KgQaPanel } from "@/components/waterexpert/panels/kg-qa-panel";
import { KgHighlightProvider } from "@/lib/kg/highlight-context";

const TAB_QA = "qa";
const TAB_VIEW = "overviewView";

export default function KnowledgeGraphPage() {
  const { t } = useT();
  // Controlled rather than defaulted: the QA panel jumps to the graph tab to
  // show the subgraph it just retrieved, which needs a setter here.
  const [tab, setTab] = React.useState("uploadBuild");

  return (
    <AppShell title={t("nav.knowledgeGraph")}>
      {/* The provider sits above the tabs because the panels do not coexist:
          Base UI unmounts an inactive panel, so the QA panel that sets a
          highlight and the view panel that draws it are never both mounted. */}
      <KgHighlightProvider>
        <Tabs value={tab} onValueChange={(value) => setTab(String(value))}>
          <TabsList>
            <TabsTrigger value="uploadBuild">{t("hub.knowledgeGraph.tabUploadBuild")}</TabsTrigger>
            <TabsTrigger value={TAB_VIEW}>{t("hub.knowledgeGraph.tabOverviewView")}</TabsTrigger>
            <TabsTrigger value={TAB_QA}>{t("hub.knowledgeGraph.tabQa")}</TabsTrigger>
          </TabsList>
          <TabsContent value="uploadBuild">
            <div className="flex flex-col gap-6">
              <KgUploadPanel />
              <KgPreprocessPanel />
              <KgBuildPanel />
            </div>
          </TabsContent>
          <TabsContent value={TAB_VIEW}>
            <div className="flex flex-col gap-6">
              <KgOverviewPanel />
              <KgViewPanel />
            </div>
          </TabsContent>
          <TabsContent value={TAB_QA}>
            <KgQaPanel onJumpToGraph={() => setTab(TAB_VIEW)} />
          </TabsContent>
        </Tabs>
      </KgHighlightProvider>
    </AppShell>
  );
}
