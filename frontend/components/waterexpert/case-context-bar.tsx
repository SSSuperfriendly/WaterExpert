"use client";

import * as React from "react";
import Link from "next/link";
import { useT } from "@/lib/i18n/use-t";
import { useAppStore } from "@/lib/stores/app-store";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { HugeiconsIcon } from "@hugeicons/react";
import { Folder02Icon, Calendar01Icon, Cancel01Icon } from "@hugeicons/core-free-icons";

/**
 * Global case-context bar rendered under the header. It surfaces the single
 * source of truth every result page resolves against (review item 4): the
 * active case + target date. When nothing is bound, results silently read the
 * shared integrated artifacts, so we call that out rather than hide it.
 */
export function CaseContextBar() {
  const { t } = useT();
  const activeCaseId = useAppStore((s) => s.activeCaseId);
  const targetDate = useAppStore((s) => s.targetDate);
  const clearCaseContext = useAppStore((s) => s.clearCaseContext);

  if (!activeCaseId) {
    return (
      <div className="flex items-center gap-2 rounded-md border border-dashed px-3 py-2 text-xs">
        <HugeiconsIcon icon={Folder02Icon} className="text-muted-foreground size-4 shrink-0" />
        <span className="text-muted-foreground min-w-0 flex-1 truncate">
          {t("case.noCaseBound")}
        </span>
      </div>
    );
  }

  return (
    <div className="flex flex-wrap items-center gap-2 rounded-md border px-3 py-2 text-xs">
      <HugeiconsIcon icon={Folder02Icon} className="text-muted-foreground size-4 shrink-0" />
      <span className="text-muted-foreground shrink-0">{t("case.caseId")}:</span>
      <Link href={`/cases/${activeCaseId}`} className="font-mono font-medium underline-offset-2 hover:underline">
        {activeCaseId}
      </Link>
      {targetDate && (
        <Badge variant="outline" className="gap-1 font-normal">
          <HugeiconsIcon icon={Calendar01Icon} className="size-3.5" />
          {t("case.targetDate")}: {targetDate}
        </Badge>
      )}
      <Button
        variant="ghost"
        size="sm"
        className="ml-auto h-7 gap-1 px-2 text-xs"
        onClick={clearCaseContext}
      >
        <HugeiconsIcon icon={Cancel01Icon} className="size-3.5" />
        {t("case.clear")}
      </Button>
    </div>
  );
}
