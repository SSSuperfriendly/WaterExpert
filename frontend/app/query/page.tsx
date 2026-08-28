"use client";

import { useT } from "@/lib/i18n/use-t";
import { AppShell } from "@/components/waterexpert/app-shell";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import { DatabaseQueryPanel } from "@/components/waterexpert/panels/database-query-panel";
import { VisualizationPanel } from "@/components/waterexpert/panels/visualization-panel";

export default function QueryPage() {
  const { t } = useT();

  return (
    <AppShell title={t("nav.queryVisualization")}>

      <Tabs defaultValue="query">
        <TabsList>
          <TabsTrigger value="query">{t("hub.query.tabQuery")}</TabsTrigger>
          <TabsTrigger value="visualization">{t("hub.query.tabVisualization")}</TabsTrigger>
        </TabsList>
        <TabsContent value="query">
          <DatabaseQueryPanel />
        </TabsContent>
        <TabsContent value="visualization">
          <VisualizationPanel />
        </TabsContent>
      </Tabs>
    </AppShell>
  );
}
