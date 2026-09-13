"use client";

import * as React from "react";
import { useT } from "@/lib/i18n/use-t";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Label } from "@/components/ui/label";

/**
 * A small controlled modal for the one-field confirmations a workflow needs
 * (assign, post-mortem, refusal reason). It replaces ``window.prompt`` so the
 * action is styled, localised, validated and non-blocking, and so a failure can
 * be shown rather than swallowed.
 */
export function TextPromptDialog({
  open,
  title,
  label,
  placeholder,
  value,
  multiline = false,
  confirmLabel,
  busy = false,
  onChange,
  onConfirm,
  onCancel,
}: {
  open: boolean;
  title: string;
  label: string;
  placeholder?: string;
  value: string;
  multiline?: boolean;
  confirmLabel: string;
  busy?: boolean;
  onChange: (value: string) => void;
  onConfirm: () => void;
  onCancel: () => void;
}) {
  const { t } = useT();

  React.useEffect(() => {
    if (!open) return;
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") onCancel();
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [open, onCancel]);

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
      <div
        className="absolute inset-0 bg-black/40"
        onClick={onCancel}
        aria-hidden
      />
      <div
        role="dialog"
        aria-modal="true"
        aria-label={title}
        className="bg-background relative z-10 w-full max-w-md space-y-3 rounded-lg border p-5 shadow-lg"
      >
        <h3 className="text-sm font-medium">{title}</h3>
        <div className="space-y-1.5">
          <Label>{label}</Label>
          {multiline ? (
            <Textarea
              autoFocus
              rows={3}
              value={value}
              placeholder={placeholder}
              onChange={(event) => onChange(event.target.value)}
            />
          ) : (
            <Input
              autoFocus
              value={value}
              placeholder={placeholder}
              onChange={(event) => onChange(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === "Enter" && value.trim()) onConfirm();
              }}
            />
          )}
        </div>
        <div className="flex justify-end gap-2">
          <Button variant="ghost" size="sm" onClick={onCancel}>
            {t("common.cancel")}
          </Button>
          <Button size="sm" onClick={onConfirm} disabled={busy || !value.trim()}>
            {busy ? t("common.loading") : confirmLabel}
          </Button>
        </div>
      </div>
    </div>
  );
}
