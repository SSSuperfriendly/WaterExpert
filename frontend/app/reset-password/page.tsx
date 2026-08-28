"use client";

import * as React from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useT } from "@/lib/i18n/use-t";
import { endpoints } from "@/lib/api/endpoints";
import { ApiError } from "@/lib/api/client";
import { AuthShell } from "@/components/waterexpert/auth-shell";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { HugeiconsIcon } from "@hugeicons/react";
import { Key01Icon, AlertCircleIcon, CheckmarkCircle01Icon } from "@hugeicons/core-free-icons";

export default function ResetPasswordPage() {
  const { t } = useT();
  const router = useRouter();
  const [token] = React.useState(() => {
    if (typeof window === "undefined") return "";
    return new URLSearchParams(window.location.search).get("token") ?? "";
  });

  const [password, setPassword] = React.useState("");
  const [error, setError] = React.useState<string | null>(null);
  const [done, setDone] = React.useState(false);
  const [busy, setBusy] = React.useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (busy) return;
    if (password.length < 8) {
      setError(t("auth.passwordTooShort"));
      return;
    }
    setBusy(true);
    setError(null);
    try {
      await endpoints.resetPassword(token, password);
      setDone(true);
      setTimeout(() => router.replace("/login"), 1500);
    } catch (err) {
      if (err instanceof ApiError && err.status === 0) {
        setError(t("auth.networkError"));
      } else {
        setError(t("auth.invalidResetToken"));
      }
    } finally {
      setBusy(false);
    }
  };

  return (
    <AuthShell
      formTitle={t("auth.resetPasswordTitle")}
      formDescription={t("auth.resetPasswordSubtitle")}
    >
      <form onSubmit={handleSubmit} noValidate className="space-y-4">
        {done ? (
          <div className="flex items-start gap-2 rounded-md border border-primary/30 bg-primary/5 px-3 py-2">
            <HugeiconsIcon
              icon={CheckmarkCircle01Icon}
              className="text-primary mt-0.5 size-4 shrink-0"
            />
            <p className="text-sm leading-snug">{t("auth.resetSuccess")}</p>
          </div>
        ) : (
          <div className="space-y-1.5">
            <Label htmlFor="password">{t("auth.newPassword")}</Label>
            <div className="relative">
              <HugeiconsIcon
                icon={Key01Icon}
                className="text-muted-foreground absolute left-3 top-1/2 size-4 -translate-y-1/2"
              />
              <Input
                id="password"
                type="password"
                className="h-10 pl-9"
                placeholder={t("auth.passwordPlaceholder")}
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                autoComplete="new-password"
                autoFocus
              />
            </div>
          </div>
        )}

        {error && (
          <div className="flex items-start gap-2 rounded-md border border-destructive/30 bg-destructive/5 px-3 py-2">
            <HugeiconsIcon
              icon={AlertCircleIcon}
              className="text-destructive mt-0.5 size-4 shrink-0"
            />
            <p className="text-destructive text-xs leading-snug">{error}</p>
          </div>
        )}

        {!done && (
          <Button
            type="submit"
            className="h-10 w-full bg-linear-to-br from-sky-500 to-blue-700 text-white hover:from-sky-600 hover:to-blue-800"
            disabled={busy || !password}
          >
            {busy ? t("auth.resettingPassword") : t("auth.resetPasswordButton")}
          </Button>
        )}

        <p className="text-muted-foreground text-center text-sm">
          <Link
            href="/login"
            className="text-primary font-medium underline-offset-4 hover:underline"
          >
            {t("auth.backToLogin")}
          </Link>
        </p>
      </form>
    </AuthShell>
  );
}
