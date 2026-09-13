"use client";

import * as React from "react";
import Link from "next/link";
import { useT } from "@/lib/i18n/use-t";
import { useAppStore } from "@/lib/stores/app-store";
import { useCapabilities } from "@/lib/hooks/use-capabilities";
import { endpoints } from "@/lib/api/endpoints";
import { describeApiError, translateModel } from "@/lib/domain";
import { Button, buttonVariants } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { HugeiconsIcon } from "@hugeicons/react";
import { PlayIcon, RefreshIcon } from "@hugeicons/core-free-icons";

const TERMINAL_STATUSES = new Set(["completed", "failed", "orphaned"]);

/**
 * Turns a read-only result page into a compute page.
 *
 * A result is always attributed to a case, so "compute" means running that case
 * and waiting for its artifacts to land. When no case is bound the bar says so
 * and points at the case centre instead of pretending a button would work. The
 * wait polls the job by id — which is also what advances the bound case — and
 * reloads the page's data once the run reaches a terminal state.
 */
export function ResultRunBar({ onComputed }: { onComputed?: () => void }) {
  const { t } = useT();
  const activeCaseId = useAppStore((s) => s.activeCaseId);
  const setActiveJobId = useAppStore((s) => s.setActiveJobId);
  const capabilities = useCapabilities();

  const models = capabilities.data?.models ?? [];
  const [model, setModel] = React.useState("");
  const effectiveModel = model || models[0]?.key || "";
  const [busy, setBusy] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);
  const [pendingJobId, setPendingJobId] = React.useState<string | null>(null);

  React.useEffect(() => {
    if (!pendingJobId) return;
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout>;

    const tick = async () => {
      try {
        const job = await endpoints.job(pendingJobId);
        if (cancelled) return;
        if (TERMINAL_STATUSES.has(job.status)) {
          setPendingJobId(null);
          onComputed?.();
          return;
        }
      } catch {
        // A transient read error must not abort the wait.
      }
      if (!cancelled) timer = setTimeout(tick, 3000);
    };

    timer = setTimeout(tick, 1200);
    return () => {
      cancelled = true;
      clearTimeout(timer);
    };
  }, [pendingJobId, onComputed]);

  const run = async () => {
    if (!activeCaseId || !effectiveModel) return;
    setBusy(true);
    setError(null);
    try {
      const job = await endpoints.runCase(activeCaseId, {
        model_name: effectiveModel,
        use_existing_artifacts: true,
      });
      setActiveJobId(job.job_id);
      setPendingJobId(job.job_id);
    } catch (err) {
      setError(describeApiError(t, err));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="flex flex-wrap items-center gap-3 rounded-md border px-3 py-2">
      {activeCaseId ? (
        <>
          <Badge variant="outline" className="font-mono text-xs">
            {activeCaseId}
          </Badge>
          {models.length > 1 && (
            <Select value={effectiveModel} onValueChange={(v) => v && setModel(v)}>
              <SelectTrigger className="h-8 w-44">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {models.map((entry) => (
                  <SelectItem key={entry.key} value={entry.key}>
                    {translateModel(t, entry.key)}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          )}
          <Button
            size="sm"
            onClick={run}
            disabled={busy || !effectiveModel || pendingJobId !== null}
          >
            <HugeiconsIcon icon={PlayIcon} className="size-4" />
            {pendingJobId ? t("resultRun.computing") : t("resultRun.run")}
          </Button>
          <Button variant="ghost" size="sm" onClick={() => onComputed?.()}>
            <HugeiconsIcon icon={RefreshIcon} className="size-4" />
            {t("resultRun.refresh")}
          </Button>
          {pendingJobId && (
            <span className="text-muted-foreground text-xs">{t("resultRun.waiting")}</span>
          )}
          {error && <span className="text-destructive text-xs">{error}</span>}
        </>
      ) : (
        <>
          <span className="text-muted-foreground flex-1 text-xs">{t("resultRun.noCase")}</span>
          <Link
            href="/cases"
            className={buttonVariants({ variant: "outline", size: "sm" })}
          >
            {t("resultRun.bindCase")}
          </Link>
        </>
      )}
    </div>
  );
}
