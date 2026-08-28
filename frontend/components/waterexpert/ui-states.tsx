"use client";

import { Skeleton } from "@/components/ui/skeleton";
import { Button } from "@/components/ui/button";
import { useT } from "@/lib/i18n/use-t";
import { HugeiconsIcon } from "@hugeicons/react";
import { FileEmpty01Icon, AlertCircleIcon, RefreshIcon } from "@hugeicons/core-free-icons";

export function LoadingState({ rows = 4 }: { rows?: number }) {
  return (
    <div className="space-y-3">
      {Array.from({ length: rows }).map((_, i) => (
        <Skeleton key={i} className="h-10 w-full" />
      ))}
    </div>
  );
}

export function EmptyState({ title, description }: { title?: string; description?: string }) {
  const { t } = useT();
  return (
    <div className="flex flex-col items-center justify-center gap-2 rounded-lg border border-dashed py-12 text-center">
      <HugeiconsIcon icon={FileEmpty01Icon} className="text-muted-foreground size-8" />
      <p className="text-sm font-medium">{title ?? t("common.noData")}</p>
      {description && <p className="text-muted-foreground text-xs">{description}</p>}
    </div>
  );
}

export function ErrorState({
  message,
  onRetry,
}: {
  message?: string;
  onRetry?: () => void;
}) {
  const { t } = useT();
  return (
    <div className="flex flex-col items-center justify-center gap-3 rounded-lg border border-destructive/30 bg-destructive/5 py-10 text-center">
      <HugeiconsIcon icon={AlertCircleIcon} className="text-destructive size-8" />
      <p className="text-sm font-medium text-destructive">{t("common.error")}</p>
      {message && <p className="text-muted-foreground max-w-md text-xs">{message}</p>}
      {onRetry && (
        <Button variant="outline" size="sm" onClick={onRetry}>
          <HugeiconsIcon icon={RefreshIcon} className="size-4" />
          {t("common.retry")}
        </Button>
      )}
    </div>
  );
}
