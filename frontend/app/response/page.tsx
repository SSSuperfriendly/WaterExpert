"use client";

import * as React from "react";
import { useT } from "@/lib/i18n/use-t";
import { AppShell } from "@/components/waterexpert/app-shell";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import { ThresholdsPanel } from "@/components/waterexpert/panels/thresholds-panel";
import { ScenarioPanel } from "@/components/waterexpert/panels/scenario-panel";
import { PlaybookPanel } from "@/components/waterexpert/panels/playbook-panel";
import { ResultRunBar } from "@/components/waterexpert/result-run-bar";

export default function ResponsePage() {
  const { t } = useT();
  // Remount the tabs after a compute so every panel refetches its scoped
  // artifacts; the panels own their fetches, so a key is the cleanest signal.
  const [refreshKey, setRefreshKey] = React.useState(0);

  return (
    <AppShell title={t("nav.responsePlaybook")}>

      <ResultRunBar onComputed={() => setRefreshKey((key) => key + 1)} />

      <Tabs key={refreshKey} defaultValue="thresholds">
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
