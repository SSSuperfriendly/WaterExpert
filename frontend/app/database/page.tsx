"use client";

import { useT } from "@/lib/i18n/use-t";
import { AppShell } from "@/components/waterexpert/app-shell";
import { DatabaseSummaryPanel } from "@/components/waterexpert/panels/database-summary-panel";
import { UploadPanel } from "@/components/waterexpert/panels/upload-panel";

export default function DatabasePage() {
  const { t } = useT();

  return (
    <AppShell title={t("nav.importDatabase")}>

      <DatabaseSummaryPanel />
      <UploadPanel />
    </AppShell>
  );
}
