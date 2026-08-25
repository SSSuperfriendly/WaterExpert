"use client";

import { useT } from "@/lib/i18n/use-t";
import { AppShell } from "@/components/waterexpert/app-shell";
import { PageHeading } from "@/components/waterexpert/ui-states";
import { DatabaseSummaryPanel } from "@/components/waterexpert/panels/database-summary-panel";
import { UploadPanel } from "@/components/waterexpert/panels/upload-panel";

export default function DatabasePage() {
  const { t } = useT();

  return (
    <AppShell title={t("nav.importDatabase")}>
      <PageHeading title={t("nav.importDatabase")} subtitle={t("hub.database.subtitle")} />

      <DatabaseSummaryPanel />
      <UploadPanel />
    </AppShell>
  );
}
