"use client";

import * as React from "react";
import Link from "next/link";
import { useT } from "@/lib/i18n/use-t";
import { endpoints } from "@/lib/api/endpoints";
import { ApiError } from "@/lib/api/client";
import { AuthShell } from "@/components/waterexpert/auth-shell";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { HugeiconsIcon } from "@hugeicons/react";
import { Mail01Icon, AlertCircleIcon, CheckmarkCircle01Icon } from "@hugeicons/core-free-icons";

const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

export default function ForgotPasswordPage() {
  const { t } = useT();
  const [email, setEmail] = React.useState("");
  const [error, setError] = React.useState<string | null>(null);
  const [sent, setSent] = React.useState(false);
  const [busy, setBusy] = React.useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (busy) return;
    if (!EMAIL_RE.test(email.trim())) {
      setError(t("auth.invalidEmail"));
      return;
    }
    setBusy(true);
    setError(null);
    try {
      await endpoints.forgotPassword(email.trim());
      setSent(true);
    } catch (err) {
      if (err instanceof ApiError && err.status === 0) {
        setError(t("auth.networkError"));
      } else {
        setError(t("auth.loginFailed"));
      }
    } finally {
      setBusy(false);
    }
  };

  return (
    <AuthShell formTitle={t("auth.forgotTitle")} formDescription={t("auth.forgotSubtitle")}>
      <form onSubmit={handleSubmit} noValidate className="space-y-4">
        {sent ? (
          <div className="flex items-start gap-2 rounded-md border border-primary/30 bg-primary/5 px-3 py-2">
            <HugeiconsIcon
              icon={CheckmarkCircle01Icon}
              className="text-primary mt-0.5 size-4 shrink-0"
            />
            <p className="text-sm leading-snug">{t("auth.resetLinkSent")}</p>
          </div>
        ) : (
          <div className="space-y-1.5">
            <Label htmlFor="email">{t("auth.email")}</Label>
            <div className="relative">
              <HugeiconsIcon
                icon={Mail01Icon}
                className="text-muted-foreground absolute left-3 top-1/2 size-4 -translate-y-1/2"
              />
              <Input
                id="email"
                type="email"
                className="h-10 pl-9"
                placeholder={t("auth.emailPlaceholder")}
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                autoComplete="email"
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

        {!sent && (
          <Button
            type="submit"
            className="h-10 w-full bg-linear-to-br from-sky-500 to-blue-700 text-white hover:from-sky-600 hover:to-blue-800"
            disabled={busy || !email}
          >
            {busy ? t("auth.sendingResetLink") : t("auth.sendResetLink")}
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
