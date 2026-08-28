"use client";

import * as React from "react";
import Link from "next/link";
import {
  ResponsiveContainer,
  AreaChart,
  Area,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
} from "recharts";
import { useT } from "@/lib/i18n/use-t";
import { ThemeToggle } from "@/components/theme-toggle";
import { Button } from "@/components/ui/button";
import { HugeiconsIcon, type IconSvgElement } from "@hugeicons/react";
import {
  Activity01Icon,
  Search01Icon,
  ClipboardIcon,
  AiNetworkIcon,
  Globe02Icon,
} from "@hugeicons/core-free-icons";

/**
 * Shared two-column auth layout (login / register).
 *
 * Reuses the landing-page vocabulary — top nav, a two-column hero with
 * marketing copy + feature cards on the left and the auth form on the right —
 * while staying on the existing Square UI theme tokens. The showcase visual is
 * a real turbidity prediction trend (observed vs. predicted), not a generic
 * illustration.
 */

const FEATURES: { labelKey: string; descKey: string; icon: IconSvgElement }[] = [
  {
    labelKey: "auth.featurePredict",
    descKey: "auth.featurePredictDesc",
    icon: Activity01Icon,
  },
  {
    labelKey: "auth.featureDiagnosis",
    descKey: "auth.featureDiagnosisDesc",
    icon: Search01Icon,
  },
  {
    labelKey: "auth.featureResponse",
    descKey: "auth.featureResponseDesc",
    icon: ClipboardIcon,
  },
  {
    labelKey: "auth.featureKg",
    descKey: "auth.featureKgDesc",
    icon: AiNetworkIcon,
  },
];

// Deterministic sample series (no Date.now/random) so static export stays stable.
function buildTrend(): { label: string; turbidity: number; predicted: number }[] {
  const points: { label: string; turbidity: number; predicted: number }[] = [];
  const days = 30;
  for (let i = 0; i < days; i++) {
    const base = 22 + 7 * Math.sin((i * Math.PI) / 7);
    const surge =
      i >= 20 && i <= 25 ? Math.sin(((i - 20) * Math.PI) / 5) * 14 : 0;
    const noise = Math.sin(i * 1.7) * 2.5;
    const turbidity = Math.max(8, Math.round((base + surge + noise) * 10) / 10);
    const predicted = Math.max(
      8,
      Math.round((turbidity + Math.sin(i * 0.9) * 2) * 10) / 10
    );
    points.push({
      label: `08-${String(i + 1).padStart(2, "0")}`,
      turbidity,
      predicted,
    });
  }
  return points;
}

const TREND = buildTrend();

function TrendCard() {
  const { t } = useT();
  return (
    <div className="rounded-xl border bg-card p-4 shadow-xs">
      <div className="flex items-center justify-between">
        <p className="text-sm font-medium">{t("auth.trendTitle")}</p>
        <span className="text-muted-foreground text-xs">{t("auth.trendUnit")}</span>
      </div>
      <div className="mt-3 h-44 w-full">
        <ResponsiveContainer width="100%" height="100%">
          <AreaChart data={TREND} margin={{ top: 8, right: 8, left: -18, bottom: 0 }}>
            <defs>
              <linearGradient id="turbidityFill" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor="#0ea5e9" stopOpacity={0.28} />
                <stop offset="100%" stopColor="#0ea5e9" stopOpacity={0} />
              </linearGradient>
            </defs>
            <CartesianGrid
              strokeDasharray="3 3"
              className="stroke-border/50"
              vertical={false}
            />
            <XAxis
              dataKey="label"
              tick={{ fontSize: 10 }}
              tickMargin={6}
              minTickGap={28}
              axisLine={false}
              tickLine={false}
            />
            <YAxis
              tick={{ fontSize: 10 }}
              width={30}
              axisLine={false}
              tickLine={false}
            />
            <Tooltip contentStyle={{ fontSize: 12, borderRadius: 8 }} />
            <Area
              type="monotone"
              dataKey="turbidity"
              name={t("auth.trendActual")}
              stroke="#0ea5e9"
              strokeWidth={2}
              fill="url(#turbidityFill)"
              dot={false}
              activeDot={{ r: 3 }}
            />
            <Line
              type="monotone"
              dataKey="predicted"
              name={t("auth.trendPredicted")}
              stroke="#6366f1"
              strokeWidth={1.5}
              strokeDasharray="5 5"
              dot={false}
            />
          </AreaChart>
        </ResponsiveContainer>
      </div>
      <div className="mt-3 flex items-center gap-4 text-xs">
        <span className="text-muted-foreground flex items-center gap-1.5">
          <span className="size-2 rounded-full bg-sky-500" />
          {t("auth.trendActual")}
        </span>
        <span className="text-muted-foreground flex items-center gap-1.5">
          <span className="w-4 border-t border-dashed border-indigo-500" />
          {t("auth.trendPredicted")}
        </span>
      </div>
    </div>
  );
}

export function AuthShell({
  formTitle,
  formDescription,
  children,
}: {
  formTitle: string;
  formDescription?: string;
  children: React.ReactNode;
}) {
  const { t, locale, setLocale } = useT();

  return (
    <div className="flex min-h-svh flex-col bg-background">
      {/* Top nav */}
      <header className="sticky top-0 z-20 border-b bg-background/80 backdrop-blur">
        <div className="mx-auto flex h-16 w-full max-w-6xl items-center justify-between px-4 sm:px-6">
          <Link href="/" className="flex items-center">
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img
              src="/ui/assets/waterexpert.png"
              alt={t("app.shortName")}
              className="h-14 w-auto"
            />
          </Link>

          <div className="flex items-center gap-1">
            <Button
              variant="ghost"
              size="icon"
              onClick={() => setLocale(locale === "zh-CN" ? "en-US" : "zh-CN")}
              title={locale === "zh-CN" ? "English" : "简体中文"}
            >
              <HugeiconsIcon icon={Globe02Icon} className="size-5" />
              <span className="sr-only">Language</span>
            </Button>
            <ThemeToggle />
          </div>
        </div>
      </header>

      {/* Two-column hero */}
      <main className="mx-auto grid w-full max-w-6xl flex-1 gap-10 px-4 py-8 sm:px-6 lg:grid-cols-[1.05fr_1fr] lg:items-center lg:gap-16 lg:py-14">
        {/* Left: marketing copy + feature cards + real trend showcase */}
        <section className="order-2 lg:order-1">
          <h1 className="bg-linear-to-r from-sky-500 via-blue-600 to-violet-600 bg-clip-text text-3xl font-bold leading-tight tracking-tight text-transparent sm:text-4xl">
            {t("auth.heroTitle")}
          </h1>

          <div className="mt-8 grid grid-cols-1 gap-3 sm:grid-cols-2">
            {FEATURES.map((feature) => (
              <div
                key={feature.labelKey}
                className="rounded-xl border bg-card p-4 shadow-xs"
              >
                <div className="flex size-9 items-center justify-center rounded-lg bg-linear-to-br from-sky-500 to-blue-700 text-white">
                  <HugeiconsIcon icon={feature.icon} className="size-5" />
                </div>
                <p className="mt-3 text-sm font-semibold">
                  {t(feature.labelKey)}
                </p>
                <p className="text-muted-foreground mt-1 text-xs">
                  {t(feature.descKey)}
                </p>
              </div>
            ))}
          </div>

          <div className="mt-6 hidden sm:block">
            <TrendCard />
          </div>
        </section>

        {/* Right: auth form */}
        <section className="order-1 lg:order-2">
          <div className="rounded-2xl border bg-card p-6 shadow-sm sm:p-8">
            <div className="mb-5 space-y-1">
              <h2 className="text-xl font-semibold">{formTitle}</h2>
              {formDescription && (
                <p className="text-muted-foreground text-sm">{formDescription}</p>
              )}
            </div>
            {children}
          </div>
        </section>
      </main>
    </div>
  );
}
