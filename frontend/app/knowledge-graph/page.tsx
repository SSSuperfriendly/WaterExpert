"use client";

import { useT } from "@/lib/i18n/use-t";
import { AppShell } from "@/components/waterexpert/app-shell";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import { KgOverviewPanel } from "@/components/waterexpert/panels/kg-overview-panel";
import { KgUploadPanel } from "@/components/waterexpert/panels/kg-upload-panel";
import { KgPreprocessPanel } from "@/components/waterexpert/panels/kg-preprocess-panel";
import { KgBuildPanel } from "@/components/waterexpert/panels/kg-build-panel";
import { KgViewPanel } from "@/components/waterexpert/panels/kg-view-panel";

export default function KnowledgeGraphPage() {
  const { t } = useT();

  return (
    <AppShell title={t("nav.knowledgeGraph")}>

      <Tabs defaultValue="uploadBuild">
        <TabsList>
          <TabsTrigger value="uploadBuild">{t("hub.knowledgeGraph.tabUploadBuild")}</TabsTrigger>
          <TabsTrigger value="overviewView">{t("hub.knowledgeGraph.tabOverviewView")}</TabsTrigger>
        </TabsList>
        <TabsContent value="uploadBuild">
          <div className="flex flex-col gap-6">
            <KgUploadPanel />
            <KgPreprocessPanel />
            <KgBuildPanel />
          </div>
        </TabsContent>
        <TabsContent value="overviewView">
          <div className="flex flex-col gap-6">
            <KgOverviewPanel />
            <KgViewPanel />
          </div>
        </TabsContent>
      </Tabs>
    </AppShell>
  );
}
