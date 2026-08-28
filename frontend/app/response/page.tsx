"use client";

import { useT } from "@/lib/i18n/use-t";
import { AppShell } from "@/components/waterexpert/app-shell";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import { ThresholdsPanel } from "@/components/waterexpert/panels/thresholds-panel";
import { ScenarioPanel } from "@/components/waterexpert/panels/scenario-panel";
import { PlaybookPanel } from "@/components/waterexpert/panels/playbook-panel";

export default function ResponsePage() {
  const { t } = useT();

  return (
    <AppShell title={t("nav.responsePlaybook")}>

      <Tabs defaultValue="thresholds">
        <TabsList>
          <TabsTrigger value="thresholds">{t("hub.response.tabThresholds")}</TabsTrigger>
          <TabsTrigger value="scenario">{t("hub.response.tabScenario")}</TabsTrigger>
          <TabsTrigger value="playbook">{t("hub.response.tabPlaybook")}</TabsTrigger>
        </TabsList>
        <TabsContent value="thresholds">
          <ThresholdsPanel />
        </TabsContent>
        <TabsContent value="scenario">
          <ScenarioPanel />
        </TabsContent>
        <TabsContent value="playbook">
          <PlaybookPanel />
        </TabsContent>
      </Tabs>
    </AppShell>
  );
}
