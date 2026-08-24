"use client";

import * as React from "react";
import { useT } from "@/lib/i18n/use-t";
import { useApi } from "@/lib/hooks/use-api";
import { endpoints } from "@/lib/api/endpoints";
import { AppShell } from "@/components/waterexpert/app-shell";
import { PageHeading, LoadingState, ErrorState } from "@/components/waterexpert/ui-states";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { HugeiconsIcon } from "@hugeicons/react";
import { Upload01Icon } from "@hugeicons/core-free-icons";

export default function KnowledgeGraphUploadPage() {
  const { t } = useT();
  const uploads = useApi(() => endpoints.knowledgeGraph.uploads());

  const [files, setFiles] = React.useState<File[]>([]);
  const [busy, setBusy] = React.useState(false);
  const [message, setMessage] = React.useState<string | null>(null);

  const handleFiles = (list: FileList | null) => {
    if (!list) return;
    setFiles(Array.from(list).filter((f) => f.name.toLowerCase().endsWith(".pdf")));
  };

  const handleUpload = async () => {
    if (files.length === 0) return;
    setBusy(true);
    setMessage(null);
    try {
      const formData = new FormData();
      files.forEach((f) => formData.append("files", f));
      await endpoints.knowledgeGraph.upload(formData);
      setMessage(t("kg.uploadSuccess"));
      setFiles([]);
      uploads.reload();
    } catch (err) {
      setMessage(err instanceof Error ? err.message : t("common.error"));
    } finally {
      setBusy(false);
    }
  };

  const handleClear = async () => {
    setBusy(true);
    setMessage(null);
    try {
      await endpoints.knowledgeGraph.clearUploads();
      uploads.reload();
    } catch (err) {
      setMessage(err instanceof Error ? err.message : t("common.error"));
    } finally {
      setBusy(false);
    }
  };

  const list = uploads.data ?? [];

  return (
    <AppShell title={t("nav.kgUpload")}>
      <PageHeading title={t("kg.uploadTitle")} subtitle={t("kg.uploadSubtitle")} />

      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <HugeiconsIcon icon={Upload01Icon} className="text-muted-foreground size-4" />
            {t("kg.selectPdf")}
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <label className="flex cursor-pointer flex-col items-center justify-center gap-2 rounded-lg border border-dashed py-8 text-center transition-colors hover:bg-muted/40">
            <HugeiconsIcon icon={Upload01Icon} className="text-muted-foreground size-8" />
            <span className="text-sm">{t("kg.selectPdf")}</span>
            <input
              type="file"
              multiple
              accept="application/pdf"
              className="hidden"
              onChange={(e) => handleFiles(e.target.files)}
            />
          </label>

          {files.length > 0 && (
            <ul className="space-y-1">
              {files.map((f, i) => (
                <li key={i} className="text-muted-foreground truncate text-xs">
                  {f.name} ({f.size} B)
                </li>
              ))}
            </ul>
          )}

          <div className="flex flex-wrap gap-2">
            <Button onClick={handleUpload} disabled={busy || files.length === 0}>
              {t("kg.savePdf")}
            </Button>
            <Button variant="outline" onClick={handleClear} disabled={busy || list.length === 0}>
              {t("kg.clearUploads")}
            </Button>
          </div>

          {message && (
            <p className="text-muted-foreground rounded-lg border px-3 py-2 text-sm">{message}</p>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>{t("kg.uploadedList")}</CardTitle>
        </CardHeader>
        <CardContent>
          {uploads.loading ? (
            <LoadingState rows={3} />
          ) : uploads.error ? (
            <ErrorState message={uploads.error} onRetry={uploads.reload} />
          ) : list.length === 0 ? (
            <p className="text-muted-foreground text-sm">{t("kg.noUploads")}</p>
          ) : (
            <ul className="space-y-2">
              {list.map((f) => (
                <li
                  key={f.name}
                  className="flex items-center justify-between gap-3 rounded-md border px-3 py-2 text-sm"
                >
                  <span className="min-w-0 truncate">📄 {f.name}</span>
                  <span className="text-muted-foreground shrink-0 text-xs">
                    {((f.size_bytes ?? 0) / 1024).toFixed(2)} KB
                  </span>
                </li>
              ))}
            </ul>
          )}
        </CardContent>
      </Card>
    </AppShell>
  );
}
