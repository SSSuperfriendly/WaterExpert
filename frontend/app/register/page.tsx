"use client";

import * as React from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useT } from "@/lib/i18n/use-t";
import { useAppStore } from "@/lib/stores/app-store";
import { endpoints } from "@/lib/api/endpoints";
import { ApiError } from "@/lib/api/client";
import { AuthShell } from "@/components/waterexpert/auth-shell";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Separator } from "@/components/ui/separator";
import { HugeiconsIcon } from "@hugeicons/react";
import {
  UserIcon,
  Mail01Icon,
  Key01Icon,
  Github01Icon,
  AlertCircleIcon,
} from "@hugeicons/core-free-icons";

const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

type FieldErrors = Partial<
  Record<"username" | "email" | "password" | "confirm", string>
>;

function FieldError({ id, message }: { id: string; message?: string }) {
  if (!message) return null;
  return (
    <p id={id} role="alert" className="text-destructive text-xs leading-snug">
      {message}
    </p>
  );
}

export default function RegisterPage() {
  const { t } = useT();
  const router = useRouter();
  const session = useAppStore((s) => s.session);
  const setSession = useAppStore((s) => s.setSession);

  const [username, setUsername] = React.useState("");
  const [email, setEmail] = React.useState("");
  const [password, setPassword] = React.useState("");
  const [confirm, setConfirm] = React.useState("");
  const [fieldErrors, setFieldErrors] = React.useState<FieldErrors>({});
  const [formError, setFormError] = React.useState<string | null>(null);
  const [busy, setBusy] = React.useState(false);

  React.useEffect(() => {
    if (session) router.replace("/");
  }, [session, router]);

  const validate = (): FieldErrors => {
    const errors: FieldErrors = {};
    if (!username.trim()) errors.username = t("auth.usernameRequired");
    if (!email.trim()) errors.email = t("auth.emailRequired");
    else if (!EMAIL_RE.test(email.trim())) errors.email = t("auth.invalidEmail");
    if (!password) errors.password = t("auth.passwordRequired");
    else if (password.length < 8) errors.password = t("auth.passwordTooShort");
    if (!confirm) errors.confirm = t("auth.confirmRequired");
    else if (confirm !== password) errors.confirm = t("auth.passwordMismatch");
    return errors;
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (busy) return;

    const errors = validate();
    setFieldErrors(errors);
    if (Object.keys(errors).length > 0) return;

    setBusy(true);
    setFormError(null);
    try {
      const profile = await endpoints.register({
        username: username.trim(),
        email: email.trim(),
        password,
        confirm_password: confirm,
      });
      setSession({
        username: profile.username,
        display_name: profile.display_name,
        role: profile.role,
        access_token: profile.access_token,
      });
      router.replace("/");
    } catch (err) {
      if (err instanceof ApiError && err.status === 0) {
        setFormError(t("auth.registerNetworkError"));
      } else if (err instanceof ApiError && err.status === 409) {
        setFormError(t("auth.accountExists"));
      } else if (err instanceof ApiError && err.detail) {
        setFormError(err.detail);
      } else {
        setFormError(
          err instanceof Error ? err.message : t("auth.registerFailed")
        );
      }
    } finally {
      setBusy(false);
    }
  };

  const handleGithub = async () => {
    setFormError(null);
    try {
      const { authorization_url } = await endpoints.githubOAuthAuthorize();
      window.location.href = authorization_url;
    } catch {
      setFormError(t("auth.oauthNotConfigured"));
    }
  };

  return (
    <AuthShell
      formTitle={t("auth.registerTitle")}
      formDescription={t("auth.registerSubtitle")}
    >
      <form onSubmit={handleSubmit} noValidate className="space-y-4">
        <div className="space-y-1.5">
          <Label htmlFor="username">{t("auth.username")}</Label>
          <div className="relative">
            <HugeiconsIcon
              icon={UserIcon}
              className="text-muted-foreground absolute left-3 top-1/2 size-4 -translate-y-1/2"
            />
            <Input
              id="username"
              className="h-10 pl-9"
              placeholder={t("auth.usernamePlaceholder")}
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              aria-invalid={!!fieldErrors.username}
              aria-describedby={fieldErrors.username ? "username-error" : undefined}
              autoComplete="username"
              autoFocus
            />
          </div>
          <FieldError id="username-error" message={fieldErrors.username} />
        </div>

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
              aria-invalid={!!fieldErrors.email}
              aria-describedby={fieldErrors.email ? "email-error" : undefined}
              autoComplete="email"
            />
          </div>
          <FieldError id="email-error" message={fieldErrors.email} />
        </div>

        <div className="space-y-1.5">
          <Label htmlFor="password">{t("auth.password")}</Label>
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
              aria-invalid={!!fieldErrors.password}
              aria-describedby={fieldErrors.password ? "password-error" : undefined}
              autoComplete="new-password"
            />
          </div>
          <FieldError id="password-error" message={fieldErrors.password} />
        </div>

        <div className="space-y-1.5">
          <Label htmlFor="confirm">{t("auth.confirmPassword")}</Label>
          <div className="relative">
            <HugeiconsIcon
              icon={Key01Icon}
              className="text-muted-foreground absolute left-3 top-1/2 size-4 -translate-y-1/2"
            />
            <Input
              id="confirm"
              type="password"
              className="h-10 pl-9"
              placeholder={t("auth.confirmPasswordPlaceholder")}
              value={confirm}
              onChange={(e) => setConfirm(e.target.value)}
              aria-invalid={!!fieldErrors.confirm}
              aria-describedby={fieldErrors.confirm ? "confirm-error" : undefined}
              autoComplete="new-password"
            />
          </div>
          <FieldError id="confirm-error" message={fieldErrors.confirm} />
        </div>

        {formError && (
          <div className="flex items-start gap-2 rounded-md border border-destructive/30 bg-destructive/5 px-3 py-2">
            <HugeiconsIcon
              icon={AlertCircleIcon}
              className="text-destructive mt-0.5 size-4 shrink-0"
            />
            <p className="text-destructive text-xs leading-snug">{formError}</p>
          </div>
        )}

        <Button
          type="submit"
          className="h-10 w-full bg-linear-to-br from-sky-500 to-blue-700 text-white hover:from-sky-600 hover:to-blue-800"
          disabled={busy}
        >
          {busy ? t("auth.creatingAccount") : t("auth.createAccount")}
        </Button>

        <div className="flex items-center gap-3">
          <Separator className="flex-1" />
          <span className="text-muted-foreground text-xs">{t("auth.or")}</span>
          <Separator className="flex-1" />
        </div>

        <Button
          type="button"
          variant="outline"
          className="h-10 w-full"
          onClick={handleGithub}
        >
          <HugeiconsIcon icon={Github01Icon} className="size-4" />
          {t("auth.githubRegister")}
        </Button>

        <p className="text-muted-foreground text-center text-sm">
          {t("auth.haveAccount")}{" "}
          <Link
            href="/login"
            className="text-primary font-semibold underline-offset-4 hover:underline"
          >
            {t("auth.signInNow")}
          </Link>
        </p>
      </form>
    </AuthShell>
  );
}
