"use client";

import { useT } from "@/lib/i18n/use-t";
import { HugeiconsIcon } from "@hugeicons/react";
import { InformationCircleIcon } from "@hugeicons/core-free-icons";

/**
 * Fact-boundary / disclaimer banner. Guardrails come from the backend
 * (dashboard.metadata / artifact payloads) so the exact wording stays the
 * source of truth. Falls back to a generic prototype disclaimer.
 */
export function GuardrailBanner({ items }: { items?: string[] }) {
  const { t } = useT();
  const list = items && items.length > 0 ? items : null;

  return (
    <div className="rounded-lg border border-amber-500/30 bg-amber-500/5 px-4 py-3">
      <div className="flex items-start gap-2">
        <HugeiconsIcon
          icon={InformationCircleIcon}
          className="text-amber-600 dark:text-amber-400 mt-0.5 size-4 shrink-0"
        />
        <div className="min-w-0 space-y-1">
          <p className="text-xs font-medium">{t("common.guardrails")}</p>
          {list ? (
            <ul className="list-disc space-y-1 pl-4">
              {list.map((item, i) => (
                <li key={i} className="text-muted-foreground text-xs leading-snug">
                  {item}
                </li>
              ))}
            </ul>
          ) : (
            <p className="text-muted-foreground text-xs leading-snug">
              {t("overview.prototypeScope")}
            </p>
          )}
        </div>
      </div>
    </div>
  );
}
