"use client";

import * as React from "react";
import Link from "next/link";
import { useT } from "@/lib/i18n/use-t";
import { useAppStore } from "@/lib/stores/app-store";
import { useCapabilities } from "@/lib/hooks/use-capabilities";
import { endpoints } from "@/lib/api/endpoints";
import { describeApiError, translateModel } from "@/lib/domain";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Checkbox } from "@/components/ui/checkbox";
import { HugeiconsIcon } from "@hugeicons/react";
import { Activity01Icon } from "@hugeicons/core-free-icons";

/**
 * The create half of a prediction run. The job list, queue, logs and result
 * selection live in the task centre, which is the single place a run is
 * monitored; this panel only submits a new one.
 */
export function JobRunnerPanel() {
  const { t } = useT();
  const setActiveJobId = useAppStore((s) => s.setActiveJobId);
  const activeCaseId = useAppStore((s) => s.activeCaseId);
  const stationCode = useAppStore((s) => s.stationCode);
  const capabilities = useCapabilities();

  const models = (capabilities.data?.models ?? []).map((entry) => entry.key);
  const [model, setModel] = React.useState<string>("");
  const effectiveModel = model || models[0] || "";
  const [startDate, setStartDate] = React.useState("");
  const [endDate, setEndDate] = React.useState("");
  const [useExisting, setUseExisting] = React.useState(true);
  const [creating, setCreating] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);
  const [createdJobId, setCreatedJobId] = React.useState<string | null>(null);

  const handleCreate = async () => {
    setCreating(true);
    setError(null);
    setCreatedJobId(null);
    try {
      const job = await endpoints.createJob({
        model_name: effectiveModel,
        station_code: stationCode,
        start_date: startDate || undefined,
        end_date: endDate || undefined,
        use_existing_artifacts: useExisting,
        case_id: activeCaseId ?? undefined,
      });
      setActiveJobId(job.job_id);
      setCreatedJobId(job.job_id);
    } catch (err) {
      setError(describeApiError(t, err));
    } finally {
      setCreating(false);
    }
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <HugeiconsIcon icon={Activity01Icon} className="text-muted-foreground size-4" />
          {t("prediction.jobRunner")}
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        <p className="text-muted-foreground text-xs">
          {activeCaseId ? `${t("case.caseId")}: ${activeCaseId}` : t("case.noCaseBound")}
        </p>
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4">
          <div className="space-y-1.5">
            <Label>{t("prediction.modelName")}</Label>
            <Select value={effectiveModel} onValueChange={(v) => setModel(v as string)}>
              <SelectTrigger className="w-full">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {models.map((m) => (
                  <SelectItem key={m} value={m}>
                    {translateModel(t, m)}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          <div className="space-y-1.5">
            <Label>{t("prediction.startDate")}</Label>
            <Input type="date" value={startDate} onChange={(e) => setStartDate(e.target.value)} />
          </div>

          <div className="space-y-1.5">
            <Label>{t("prediction.endDate")}</Label>
            <Input type="date" value={endDate} onChange={(e) => setEndDate(e.target.value)} />
          </div>
        </div>

        <div className="flex flex-wrap items-center justify-between gap-3">
          <label className="flex items-center gap-2 text-sm">
            <Checkbox
              checked={useExisting}
              onCheckedChange={(v) => setUseExisting(v === true)}
            />
            {t("prediction.useExisting")}
          </label>
          <Button onClick={handleCreate} disabled={creating || !effectiveModel}>
            {creating ? t("prediction.running") : t("prediction.runJob")}
          </Button>
        </div>

        {error && <p className="text-destructive text-xs">{error}</p>}
        {createdJobId && (
          <p className="text-muted-foreground text-xs">
            {t("prediction.jobSubmitted")}{" "}
            <Link href="/tasks" className="font-medium underline underline-offset-2">
              {t("prediction.goToTasks")}
            </Link>
          </p>
        )}
      </CardContent>
    </Card>
  );
}
