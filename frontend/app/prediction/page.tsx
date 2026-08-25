"use client";

import { useT } from "@/lib/i18n/use-t";
import { AppShell } from "@/components/waterexpert/app-shell";
import { PageHeading } from "@/components/waterexpert/ui-states";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import { PredictionPanel } from "@/components/waterexpert/panels/prediction-panel";
import { RealtimePanel } from "@/components/waterexpert/panels/realtime-panel";

export default function PredictionPage() {
  const { t } = useT();

  return (
    <AppShell title={t("nav.predictionValidation")}>
      <PageHeading title={t("nav.predictionValidation")} subtitle={t("hub.prediction.subtitle")} />

      <Tabs defaultValue="prediction">
        <TabsList>
          <TabsTrigger value="prediction">{t("hub.prediction.tabPrediction")}</TabsTrigger>
          <TabsTrigger value="realtime">{t("hub.prediction.tabRealtime")}</TabsTrigger>
        </TabsList>
        <TabsContent value="prediction">
          <PredictionPanel />
        </TabsContent>
        <TabsContent value="realtime">
          <RealtimePanel />
        </TabsContent>
      </Tabs>
    </AppShell>
  );
}
