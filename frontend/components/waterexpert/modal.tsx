"use client";

import * as React from "react";
import { useT } from "@/lib/i18n/use-t";
import { Button } from "@/components/ui/button";
import { HugeiconsIcon } from "@hugeicons/react";
import { Cancel01Icon } from "@hugeicons/core-free-icons";
import { cn } from "@/lib/utils";

/**
 * The app's one modal shell: a backdrop, Escape-to-close, a titled panel and a
 * scroll area. Confirm, text-prompt, edit and detail dialogs all build on it so
 * the overlay behaviour only exists once.
 */
export function Modal({
  open,
  title,
  children,
  onClose,
  size = "md",
}: {
  open: boolean;
  title: string;
  children: React.ReactNode;
  onClose: () => void;
  size?: "sm" | "md" | "lg";
}) {
  const { t } = useT();

  React.useEffect(() => {
    if (!open) return;
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [open, onClose]);

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
      <div className="absolute inset-0 bg-black/40" onClick={onClose} aria-hidden />
      <div
        role="dialog"
        aria-modal="true"
        aria-label={title}
        className={cn(
          "bg-background relative z-10 w-full space-y-3 rounded-lg border p-5 shadow-lg",
          size === "sm" ? "max-w-sm" : size === "lg" ? "max-w-3xl" : "max-w-lg"
        )}
      >
        <div className="flex items-center justify-between gap-3">
          <h3 className="text-sm font-medium">{title}</h3>
          <Button
            variant="ghost"
            size="icon-sm"
            onClick={onClose}
            aria-label={t("common.close")}
          >
            <HugeiconsIcon icon={Cancel01Icon} className="size-4" />
          </Button>
        </div>
        <div className="max-h-[70vh] overflow-y-auto">{children}</div>
      </div>
    </div>
  );
}
