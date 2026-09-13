"use client";

import * as React from "react";
import { useT } from "@/lib/i18n/use-t";
import { Modal } from "@/components/waterexpert/modal";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Label } from "@/components/ui/label";

/**
 * A one-field confirmation (assign, post-mortem, refusal reason). It replaces
 * ``window.prompt`` so the action is styled, localised, validated and
 * non-blocking, and so a failure can be shown rather than swallowed.
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

  return (
    <Modal open={open} title={title} onClose={onCancel} size="sm">
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
      <div className="mt-4 flex justify-end gap-2">
        <Button variant="ghost" size="sm" onClick={onCancel}>
          {t("common.cancel")}
        </Button>
        <Button size="sm" onClick={onConfirm} disabled={busy || !value.trim()}>
          {busy ? t("common.loading") : confirmLabel}
        </Button>
      </div>
    </Modal>
  );
}
