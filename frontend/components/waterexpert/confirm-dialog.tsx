"use client";

import * as React from "react";
import { useT } from "@/lib/i18n/use-t";
import { Modal } from "@/components/waterexpert/modal";
import { Button } from "@/components/ui/button";

/** A yes/no confirmation with an optional destructive tone. */
export function ConfirmDialog({
  open,
  title,
  message,
  confirmLabel,
  destructive = false,
  busy = false,
  onConfirm,
  onCancel,
}: {
  open: boolean;
  title: string;
  message: string;
  confirmLabel: string;
  destructive?: boolean;
  busy?: boolean;
  onConfirm: () => void;
  onCancel: () => void;
}) {
  const { t } = useT();

  return (
    <Modal open={open} title={title} onClose={onCancel} size="sm">
      <p className="text-muted-foreground text-sm">{message}</p>
      <div className="mt-4 flex justify-end gap-2">
        <Button variant="ghost" size="sm" onClick={onCancel}>
          {t("common.cancel")}
        </Button>
        <Button
          variant={destructive ? "destructive" : "default"}
          size="sm"
          onClick={onConfirm}
          disabled={busy}
        >
          {busy ? t("common.loading") : confirmLabel}
        </Button>
      </div>
    </Modal>
  );
}
