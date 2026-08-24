"use client";

import * as React from "react";
import { useT } from "@/lib/i18n/use-t";
import { endpoints } from "@/lib/api/endpoints";
import { AppShell } from "@/components/waterexpert/app-shell";
import { PageHeading } from "@/components/waterexpert/ui-states";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { Badge } from "@/components/ui/badge";
import { HugeiconsIcon } from "@hugeicons/react";
import { Search01Icon } from "@hugeicons/core-free-icons";
import type { KgQaResult } from "@/lib/api/contracts";

export default function KnowledgeGraphQaPage() {
  const { t } = useT();

  const [question, setQuestion] = React.useState("");
  const [busy, setBusy] = React.useState(false);
  const [result, setResult] = React.useState<KgQaResult | null>(null);
  const [error, setError] = React.useState<string | null>(null);

  const handleAsk = async () => {
    const q = question.trim();
    if (!q) return;
    setBusy(true);
    setError(null);
    setResult(null);
    try {
      setResult(await endpoints.knowledgeGraph.qa(q));
    } catch (err) {
      setError(err instanceof Error ? err.message : t("common.error"));
    } finally {
      setBusy(false);
    }
  };

  const relations = result?.matched_relations ?? [];

  return (
    <AppShell title={t("nav.kgQa")}>
      <PageHeading title={t("kg.qaTitle")} subtitle={t("kg.qaSubtitle")} />

      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <HugeiconsIcon icon={Search01Icon} className="text-muted-foreground size-4" />
            {t("kg.questionInput")}
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <Textarea
            value={question}
            onChange={(e) => setQuestion(e.target.value)}
            placeholder={t("kg.questionPlaceholder")}
            rows={3}
            onKeyDown={(e) => {
              if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) handleAsk();
            }}
          />
          <div className="flex items-center gap-3">
            <Button onClick={handleAsk} disabled={busy || !question.trim()}>
              {busy ? t("common.loading") : t("kg.ask")}
            </Button>
            <p className="text-muted-foreground text-xs">{t("kg.sampleQuestions")}</p>
          </div>
          {error && <p className="text-destructive text-xs">{error}</p>}
        </CardContent>
      </Card>

      {result && (
        <>
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                {t("kg.answerResult")}
                <Badge variant="outline" className="text-xs">
                  {result.source}
                </Badge>
              </CardTitle>
            </CardHeader>
            <CardContent>
              <p className="text-sm leading-relaxed whitespace-pre-wrap">{result.answer}</p>
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>{t("kg.matchedRelations")}</CardTitle>
            </CardHeader>
            <CardContent>
              {relations.length === 0 ? (
                <p className="text-muted-foreground text-sm">{t("common.noData")}</p>
              ) : (
                <ul className="space-y-2">
                  {relations.map((rel, i) => (
                    <li key={i} className="rounded-md border px-3 py-2 text-sm">
                      <p className="font-medium">
                        {rel.source} <span className="text-muted-foreground">—{rel.relation}→</span>{" "}
                        {rel.target}
                      </p>
                      {rel.evidence && (
                        <p className="text-muted-foreground mt-1 text-xs">{rel.evidence}</p>
                      )}
                      {(rel.source_file || rel.source_type || rel.target_type) && (
                        <p className="text-muted-foreground mt-0.5 text-[11px]">
                          {t("kg.sourceFile")}: {rel.source_file ?? "—"}
                          {rel.source_type ? ` · ${rel.source_type}` : ""}
                          {rel.target_type ? ` · ${rel.target_type}` : ""}
                        </p>
                      )}
                    </li>
                  ))}
                </ul>
              )}
            </CardContent>
          </Card>
        </>
      )}
    </AppShell>
  );
}
