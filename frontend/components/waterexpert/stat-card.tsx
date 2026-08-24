"use client";

import { Card, CardContent } from "@/components/ui/card";
import { HugeiconsIcon, type IconSvgElement } from "@hugeicons/react";

export function StatCard({
  label,
  value,
  hint,
  icon,
}: {
  label: string;
  value: React.ReactNode;
  hint?: React.ReactNode;
  icon?: IconSvgElement;
}) {
  return (
    <Card size="sm" className="gap-3">
      <CardContent className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="text-muted-foreground text-xs">{label}</p>
          <p className="mt-1 truncate text-lg font-semibold tabular-nums">{value}</p>
          {hint && <p className="text-muted-foreground mt-0.5 text-xs">{hint}</p>}
        </div>
        {icon && (
          <div className="bg-muted flex size-9 shrink-0 items-center justify-center rounded-lg">
            <HugeiconsIcon icon={icon} className="text-muted-foreground size-5" />
          </div>
        )}
      </CardContent>
    </Card>
  );
}
