"use client";

import * as React from "react";
import { useT } from "@/lib/i18n/use-t";
import { useApi } from "@/lib/hooks/use-api";
import { endpoints } from "@/lib/api/endpoints";
import { LoadingState, ErrorState } from "@/components/waterexpert/ui-states";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Badge } from "@/components/ui/badge";
import { HugeiconsIcon } from "@hugeicons/react";
import { Notebook01Icon } from "@hugeicons/core-free-icons";

export function KgPreprocessPanel() {
  const { t } = useT();
  const uploads = useApi(() => endpoints.knowledgeGraph.uploads());
  const texts = useApi(() => endpoints.knowledgeGraph.texts());

  const [selected, setSelected] = React.useState<string[]>([]);
  const [writeJson, setWriteJson] = React.useState(false);
  const [keepCaptions, setKeepCaptions] = React.useState(false);
  const [busy, setBusy] = React.useState(false);
  const [message, setMessage] = React.useState<string | null>(null);

  const uploadList = uploads.data ?? [];
  const txtList = texts.data?.txt ?? [];
  const jsonList = texts.data?.json ?? [];

  const toggle = (name: string) => {
    setSelected((prev) =>
      prev.includes(name) ? prev.filter((n) => n !== name) : [...prev, name]
    );
  };

  const handlePreprocess = async () => {
    if (selected.length === 0) return;
    setBusy(true);
    setMessage(null);
    try {
      await endpoints.knowledgeGraph.preprocess({
        files: selected,
        write_json: writeJson,
        keep_captions: keepCaptions,
      });
      setMessage(t("kg.preprocessSuccess"));
      setSelected([]);
      texts.reload();
    } catch (err) {
      setMessage(err instanceof Error ? err.message : t("common.error"));
    } finally {
      setBusy(false);
    }
  };

  const handleClearTexts = async () => {
    setBusy(true);
    setMessage(null);
    try {
      await endpoints.knowledgeGraph.clearTexts();
      texts.reload();
    } catch (err) {
      setMessage(err instanceof Error ? err.message : t("common.error"));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="flex flex-col gap-6">
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <HugeiconsIcon icon={Notebook01Icon} className="text-muted-foreground size-4" />
            {t("kg.selectPdfToProcess")}
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          {uploads.loading ? (
            <LoadingState rows={3} />
          ) : uploads.error ? (
            <ErrorState error={uploads.error} onRetry={uploads.reload} />
          ) : uploadList.length === 0 ? (
            <p className="text-muted-foreground text-sm">{t("kg.noPdfToProcess")}</p>
          ) : (
            <div className="space-y-2">
              {uploadList.map((f) => (
                <label
                  key={f.name}
                  className="flex items-center gap-2 rounded-md border px-3 py-2 text-sm"
                >
                  <Checkbox
                    checked={selected.includes(f.name)}
                    onCheckedChange={() => toggle(f.name)}
                  />
                  <span className="min-w-0 flex-1 truncate">📄 {f.name}</span>
                </label>
              ))}
            </div>
          )}

          <div className="flex flex-wrap items-center gap-4">
            <label className="flex items-center gap-2 text-sm">
              <Checkbox checked={writeJson} onCheckedChange={(v) => setWriteJson(v === true)} />
              {t("kg.writeJson")}
            </label>
            <label className="flex items-center gap-2 text-sm">
              <Checkbox
                checked={keepCaptions}
                onCheckedChange={(v) => setKeepCaptions(v === true)}
              />
              {t("kg.keepCaptions")}
            </label>
          </div>

          <div className="flex flex-wrap gap-2">
            <Button onClick={handlePreprocess} disabled={busy || selected.length === 0}>
              {t("kg.startPreprocess")}
            </Button>
            <Button
              variant="outline"
              onClick={handleClearTexts}
              disabled={busy || (txtList.length === 0 && jsonList.length === 0)}
            >
              {t("kg.clearTexts")}
            </Button>
          </div>

          {message && (
            <p className="text-muted-foreground rounded-lg border px-3 py-2 text-sm">{message}</p>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            {t("kg.processedCount")}
            <Badge variant="outline">
              {t("kg.generatedTxt")} {txtList.length}
            </Badge>
            <Badge variant="outline">
              {t("kg.generatedJson")} {jsonList.length}
            </Badge>
          </CardTitle>
        </CardHeader>
        <CardContent>
          {texts.loading ? (
            <LoadingState rows={3} />
          ) : texts.error ? (
            <ErrorState error={texts.error} onRetry={texts.reload} />
          ) : txtList.length === 0 && jsonList.length === 0 ? (
            <p className="text-muted-foreground text-sm">{t("kg.noTxt")}</p>
          ) : (
            <ul className="space-y-2">
              {txtList.map((f) => (
                <li
                  key={`txt-${f.name}`}
                  className="flex items-center justify-between gap-3 rounded-md border px-3 py-2 text-sm"
                >
                  <span className="min-w-0 truncate">📝 {f.name}</span>
                  <span className="text-muted-foreground shrink-0 text-xs">
                    {((f.size_bytes ?? 0) / 1024).toFixed(2)} KB
                  </span>
                </li>
              ))}
              {jsonList.map((f) => (
                <li
                  key={`json-${f.name}`}
                  className="flex items-center justify-between gap-3 rounded-md border px-3 py-2 text-sm"
                >
                  <span className="min-w-0 truncate">🧾 {f.name}</span>
                  <span className="text-muted-foreground shrink-0 text-xs">
                    {((f.size_bytes ?? 0) / 1024).toFixed(2)} KB
                  </span>
                </li>
              ))}
            </ul>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
