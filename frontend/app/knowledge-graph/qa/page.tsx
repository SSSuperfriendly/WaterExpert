"use client";

import * as React from "react";
import { useT } from "@/lib/i18n/use-t";
import { endpoints } from "@/lib/api/endpoints";
import { describeApiError } from "@/lib/domain";
import { formatNumber } from "@/lib/format";
import { AppShell } from "@/components/waterexpert/app-shell";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { LoadingState } from "@/components/waterexpert/ui-states";
import { HugeiconsIcon } from "@hugeicons/react";
import { AiNetworkIcon } from "@hugeicons/core-free-icons";
import type {
  AgentHealth,
  AgentScenario,
  AgentStrategyResult,
  AgentStrategyState,
} from "@/lib/api/contracts";

//: The self-developed WaterExpert model stack is now deployed by the
//: collaborator at `docs/internal/INTEGRATION_GUIDE.md`. This page answers the
//: way the deployed system does: pick a governance scenario, hand it the
//: current water state, and read back the RL-TGRR-style strategy job.

//: The scenario list returns `{code: "S1", name: "External Input Type"}` while
//: the strategy request wants a slug like `s1_external_input`. Derive the slug
//: from the API's own label so a rename upstream does not break the mapping.
function strategyScenarioOf(scenario: AgentScenario): string {
  const codeSlug = (scenario.code ?? "").toLowerCase();
  const nameSlug = (scenario.name ?? "")
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "_")
    .replace(/^_+|_+$/g, "");
  return nameSlug ? `${codeSlug}_${nameSlug}` : codeSlug;
}

//: Prefilled from the integration guide's worked example (Wusongkou).
const DEFAULT_STATE: Record<string, string> = {
  date: "2025-10-31",
  turbidity: "25.5",
  flow_rate: "28.5",
  temperature: "18.2",
  ph: "7.5",
  dissolved_oxygen: "8.3",
  chlorophyll_a: "5.2",
  rainfall_3d: "45.3",
  rainfall_7d: "120.5",
};

const REQUIRED_FIELDS = ["date", "turbidity", "flow_rate"];

function agentStatusVariant(status: string): "default" | "secondary" | "destructive" | "outline" {
  if (status === "ready") return "default";
  if (status === "unavailable" || status === "down" || status === "error") return "destructive";
  return "secondary";
}

export default function WaterExpertAgentPage() {
  const { t } = useT();

  const [healthData, setHealthData] = React.useState<AgentHealth | null>(null);
  const [healthError, setHealthError] = React.useState(false);
  const [scenarios, setScenarios] = React.useState<AgentScenario[] | null>(null);
  const [scenarioKey, setScenarioKey] = React.useState<string>("");
  const [form, setForm] = React.useState<Record<string, string>>(DEFAULT_STATE);
  const [busy, setBusy] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);
  const [job, setJob] = React.useState<AgentStrategyResult | null>(null);
  const [polling, setPolling] = React.useState(false);

  React.useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const data = await endpoints.agent.health();
        if (!cancelled) {
          setHealthData(data);
          setHealthError(false);
        }
      } catch {
        if (!cancelled) setHealthError(true);
      }
    })();
    (async () => {
      try {
        const data = await endpoints.agent.scenarios();
        if (!cancelled) setScenarios(data);
      } catch {
        if (!cancelled) setScenarios([]);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  const setField = (key: string) => (e: React.ChangeEvent<HTMLInputElement>) =>
    setForm((f) => ({ ...f, [key]: e.target.value }));

  const pollJob = React.useCallback(
    async (jobId: string) => {
      setPolling(true);
      try {
        const result = await endpoints.agent.strategyJob(jobId);
        setJob(result);
        if (result.status === "completed" || result.status === "failed") {
          setPolling(false);
          return;
        }
        window.setTimeout(() => pollJob(jobId), 1500);
      } catch (err) {
        setError(describeApiError(t, err));
        setPolling(false);
      }
    },
    [t]
  );

  const handleGenerate = async () => {
    if (!scenarioKey || busy) return;
    const missing = REQUIRED_FIELDS.filter((k) => !form[k]?.trim());
    if (missing.length > 0) {
      setError(t("agent.requiredState"));
      return;
    }
    const state: AgentStrategyState = {
      date: form.date.trim(),
      turbidity: Number(form.turbidity),
      flow_rate: Number(form.flow_rate),
    };
    for (const key of [
      "temperature",
      "ph",
      "dissolved_oxygen",
      "chlorophyll_a",
      "rainfall_3d",
      "rainfall_7d",
    ]) {
      if (form[key]?.trim() !== "") {
        const value = Number(form[key]);
        if (Number.isFinite(value)) state[key] = value;
      }
    }
    if (!Number.isFinite(state.turbidity) || !Number.isFinite(state.flow_rate)) {
      setError(t("agent.requiredState"));
      return;
    }

    setBusy(true);
    setError(null);
    setJob(null);
    try {
      const created = await endpoints.agent.strategy({
        scenario: scenarioKey,
        state,
        episodes: 1,
        backend: "api",
      });
      setJob({ ...created, status: created.status });
      if (created.status === "completed") {
        setPolling(false);
      } else {
        pollJob(created.job_id);
      }
    } catch (err) {
      setError(describeApiError(t, err));
    } finally {
      setBusy(false);
    }
  };

  const selectedScenario = scenarios?.find((s) => strategyScenarioOf(s) === scenarioKey) ?? null;
  const agents = healthData?.agents ?? {};

  //: The deployed API may report statuses beyond the guide's four; fall back to
  //: the raw value instead of rendering an untranslated key.
  const statusLabel = (status: string | undefined): string => {
    if (status && ["queued", "running", "completed", "failed"].includes(status)) {
      return t(`agent.${status}`);
    }
    return status ?? t("agent.queued");
  };

  return (
    <AppShell title={t("nav.waterExpert")}>
      <div className="flex flex-col gap-6">
        {/* Health — proves the deployed model stack is online. */}
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <HugeiconsIcon icon={AiNetworkIcon} className="text-muted-foreground size-4" />
              {t("agent.title")}
              <Badge variant="secondary" className="text-xs">
                {t("agent.deployedBadge")}
              </Badge>
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            <p className="text-muted-foreground text-xs">{t("agent.subtitle")}</p>
            <div className="flex flex-wrap items-center gap-2">
              <span className="text-muted-foreground text-xs">{t("agent.baseUrlLabel")}:</span>
              <code className="text-xs">http://219.228.144.101:8000/api</code>
            </div>

            <p className="text-sm font-medium">{t("agent.healthTitle")}</p>
            {healthError ? (
              <p className="text-destructive text-xs">{t("agent.healthFetchError")}</p>
            ) : Object.keys(agents).length === 0 ? (
              <p className="text-muted-foreground text-xs">{t("agent.healthUnknown")}</p>
            ) : (
              <div className="flex flex-wrap gap-2">
                {Object.entries(agents).map(([name, status]) => (
                  <Badge key={name} variant={agentStatusVariant(String(status))} className="gap-1.5">
                    <span>{name}</span>
                    <span className="text-muted-foreground">·</span>
                    <span>{t(`agent.${status === "ready" ? "agentReady" : "agentNotReady"}`)}</span>
                  </Badge>
                ))}
              </div>
            )}
          </CardContent>
        </Card>

        {/* Scenario picker — the four governance scenarios the model supports. */}
        <Card>
          <CardHeader>
            <CardTitle>{t("agent.scenariosTitle")}</CardTitle>
            <CardTitle className="text-muted-foreground text-xs font-normal">
              {t("agent.scenariosSubtitle")}
            </CardTitle>
          </CardHeader>
          <CardContent>
            {scenarios === null ? (
              <LoadingState rows={4} />
            ) : scenarios.length === 0 ? (
              <p className="text-muted-foreground text-sm">{t("common.noData")}</p>
            ) : (
              <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
                {scenarios.map((s) => {
                  const key = strategyScenarioOf(s);
                  const active = key === scenarioKey;
                  return (
                    <button
                      key={s.code}
                      type="button"
                      onClick={() => setScenarioKey(key)}
                      className={`rounded-md border p-3 text-left transition-colors ${
                        active ? "border-primary bg-primary/5" : "hover:bg-accent/40"
                      }`}
                    >
                      <p className="flex items-center justify-between text-sm font-medium">
                        <span>{s.code}</span>
                        <span className="font-mono text-muted-foreground text-[10px]">{key}</span>
                      </p>
                      <p className="mt-0.5 text-sm">{s.name}</p>
                      {s.description && (
                        <p className="text-muted-foreground mt-1 text-xs leading-snug">
                          {s.description}
                        </p>
                      )}
                    </button>
                  );
                })}
              </div>
            )}
          </CardContent>
        </Card>

        {/* Strategy generation — the deployed model's core "answer". */}
        <Card>
          <CardHeader>
            <CardTitle>{t("agent.strategyTitle")}</CardTitle>
            <CardTitle className="text-muted-foreground text-xs font-normal">
              {t("agent.strategySubtitle")}
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="flex flex-wrap items-center gap-3">
              <Label className="w-20">{t("agent.scenario")}</Label>
              <Select
                value={scenarioKey}
                onValueChange={(v) => setScenarioKey(String(v))}
                disabled={!scenarios || scenarios.length === 0}
              >
                <SelectTrigger className="w-72">
                  <SelectValue placeholder={selectedScenario?.name ?? t("agent.scenario")} />
                </SelectTrigger>
                <SelectContent>
                  {(scenarios ?? []).map((s) => (
                    <SelectItem key={s.code} value={strategyScenarioOf(s)}>
                      {s.code} · {s.name}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>

            <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
              <div className="space-y-1.5">
                <Label>{t("agent.fieldDate")}</Label>
                <Input type="date" value={form.date} onChange={setField("date")} />
              </div>
              <div className="space-y-1.5">
                <Label>{t("agent.fieldTurbidity")}</Label>
                <Input type="number" step="any" value={form.turbidity} onChange={setField("turbidity")} />
              </div>
              <div className="space-y-1.5">
                <Label>{t("agent.fieldFlowRate")}</Label>
                <Input type="number" step="any" value={form.flow_rate} onChange={setField("flow_rate")} />
              </div>
              <div className="space-y-1.5">
                <Label>
                  {t("agent.fieldTemperature")}{" "}
                  <span className="text-muted-foreground text-[10px]">{t("agent.optional")}</span>
                </Label>
                <Input type="number" step="any" value={form.temperature} onChange={setField("temperature")} />
              </div>
              <div className="space-y-1.5">
                <Label>
                  {t("agent.fieldPh")}{" "}
                  <span className="text-muted-foreground text-[10px]">{t("agent.optional")}</span>
                </Label>
                <Input type="number" step="any" min="0" max="14" value={form.ph} onChange={setField("ph")} />
              </div>
              <div className="space-y-1.5">
                <Label>
                  {t("agent.fieldDissolvedOxygen")}{" "}
                  <span className="text-muted-foreground text-[10px]">{t("agent.optional")}</span>
                </Label>
                <Input type="number" step="any" value={form.dissolved_oxygen} onChange={setField("dissolved_oxygen")} />
              </div>
              <div className="space-y-1.5">
                <Label>
                  {t("agent.fieldChlorophyllA")}{" "}
                  <span className="text-muted-foreground text-[10px]">{t("agent.optional")}</span>
                </Label>
                <Input type="number" step="any" value={form.chlorophyll_a} onChange={setField("chlorophyll_a")} />
              </div>
              <div className="space-y-1.5">
                <Label>
                  {t("agent.fieldRainfall3d")}{" "}
                  <span className="text-muted-foreground text-[10px]">{t("agent.optional")}</span>
                </Label>
                <Input type="number" step="any" value={form.rainfall_3d} onChange={setField("rainfall_3d")} />
              </div>
              <div className="space-y-1.5">
                <Label>
                  {t("agent.fieldRainfall7d")}{" "}
                  <span className="text-muted-foreground text-[10px]">{t("agent.optional")}</span>
                </Label>
                <Input type="number" step="any" value={form.rainfall_7d} onChange={setField("rainfall_7d")} />
              </div>
            </div>

            <p className="text-muted-foreground text-xs">{t("agent.exampleHint")}</p>
            {error && <p className="text-destructive text-xs">{error}</p>}

            <div className="flex items-center gap-3">
              <Button onClick={handleGenerate} disabled={busy || polling || !scenarioKey}>
                {busy || polling ? t("agent.generating") : t("agent.generate")}
              </Button>
              {job && (job.status === "completed" || job.status === "failed") && (
                <Button variant="outline" onClick={handleGenerate} disabled={busy}>
                  {t("agent.generateAnother")}
                </Button>
              )}
              {polling && (
                <span className="text-muted-foreground flex items-center gap-2 text-xs">
                  <span className="inline-block h-3 w-3 animate-spin rounded-full border-2 border-current border-t-transparent" />
                  {t("agent.polling")} ({statusLabel(job?.status)})
                </span>
              )}
            </div>

            {job && job.job_id && (
              <p className="text-muted-foreground text-xs">
                {t("agent.jobId")}: <code className="font-mono">{job.job_id}</code> ·{" "}
                {statusLabel(job.status)}
              </p>
            )}

            {job?.status === "failed" && (
              <p className="text-destructive text-xs">{job.error ?? t("agent.failed")}</p>
            )}

            {job?.status === "completed" && job.strategy && (
              <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
                <Card className="border-muted">
                  <CardHeader>
                    <CardTitle className="text-sm">{t("agent.strategyResult")}</CardTitle>
                  </CardHeader>
                  <CardContent>
                    <div className="flex flex-wrap gap-3">
                      <div className="rounded-md border px-3 py-2">
                        <p className="text-muted-foreground text-xs">{t("agent.releaseRate")}</p>
                        <p className="font-mono text-lg tabular-nums">
                          {formatNumber(job.strategy.release_rate, 2)}
                        </p>
                      </div>
                      <div className="rounded-md border px-3 py-2">
                        <p className="text-muted-foreground text-xs">{t("agent.aerationIntensity")}</p>
                        <p className="font-mono text-lg tabular-nums">
                          {formatNumber(job.strategy.aeration_intensity, 2)}
                        </p>
                      </div>
                      <div className="rounded-md border px-3 py-2">
                        <p className="text-muted-foreground text-xs">{t("agent.chemicalDosage")}</p>
                        <p className="font-mono text-lg tabular-nums">
                          {formatNumber(job.strategy.chemical_dosage, 2)}
                        </p>
                      </div>
                    </div>
                  </CardContent>
                </Card>

                {job.metrics && (
                  <Card className="border-muted">
                    <CardHeader>
                      <CardTitle className="text-sm">{t("agent.metricsResult")}</CardTitle>
                    </CardHeader>
                    <CardContent>
                      <ul className="space-y-1.5">
                        {[
                          ["turbidity_reduction", t("agent.turbidityReduction")],
                          ["turbidity_reduction_ratio", t("agent.turbidityReductionRatio")],
                          ["energy_cost", t("agent.energyCost")],
                          ["cost_saving_ratio", t("agent.costSavingRatio")],
                          ["stability", t("agent.stability")],
                          ["response_time_hours", t("agent.responseTimeHours")],
                        ].map(([key, label]) => (
                          <li
                            key={key}
                            className="flex items-center justify-between rounded-md border px-3 py-1.5 text-sm"
                          >
                            <span className="text-muted-foreground">{label}</span>
                            <span className="font-mono tabular-nums">
                              {formatNumber(job.metrics?.[key], 3)}
                            </span>
                          </li>
                        ))}
                      </ul>
                    </CardContent>
                  </Card>
                )}
              </div>
            )}
          </CardContent>
        </Card>
      </div>
    </AppShell>
  );
}
