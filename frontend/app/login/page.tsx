"use client";

import * as React from "react";
import { useRouter } from "next/navigation";
import { useT } from "@/lib/i18n/use-t";
import { useAppStore } from "@/lib/stores/app-store";
import { endpoints } from "@/lib/api/endpoints";
import { ApiError } from "@/lib/api/client";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { HugeiconsIcon } from "@hugeicons/react";
import { Key01Icon, UserIcon, AlertCircleIcon } from "@hugeicons/core-free-icons";

export default function LoginPage() {
  const { t } = useT();
  const router = useRouter();
  const setSession = useAppStore((s) => s.setSession);

  const [username, setUsername] = React.useState("");
  const [password, setPassword] = React.useState("");
  const [error, setError] = React.useState<string | null>(null);
  const [busy, setBusy] = React.useState(false);
  const [hint, setHint] = React.useState<{ username: string; password: string } | null>(null);

  const doLogin = React.useCallback(
    async (user: string, pass: string) => {
      setBusy(true);
      setError(null);
      try {
        const profile = await endpoints.login(user, pass);
        setSession({
          username: profile.username,
          display_name: profile.display_name,
          role: profile.role,
        });
        router.replace("/");
      } catch (err) {
        if (err instanceof ApiError && err.status === 401) {
          setError(t("auth.invalidCredentials"));
        } else if (err instanceof ApiError && err.status === 0) {
          setError(t("auth.networkError"));
        } else {
          setError(err instanceof Error ? err.message : t("auth.loginFailed"));
        }
      } finally {
        setBusy(false);
      }
    },
    [setSession, router, t]
  );

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!username || !password) return;
    doLogin(username, password);
  };

  const fillDemo = async () => {
    setError(null);
    try {
      const h = hint ?? (await endpoints.credentialHint());
      setHint(h);
      setUsername(h.username);
      setPassword(h.password);
    } catch {
      setError(t("auth.networkError"));
    }
  };

  const oneClickLogin = () => {
    if (hint) {
      doLogin(hint.username, hint.password);
    } else {
      doLogin(username, password);
    }
  };

  return (
    <div className="relative flex min-h-svh items-center justify-center bg-muted/40 p-4">
      <div
        className="absolute inset-0 bg-cover bg-center opacity-20 dark:opacity-10"
        style={{ backgroundImage: "url(/ui/assets/login-background.png)" }}
      />
      <div className="relative z-10 w-full max-w-sm">
        <div className="mb-6 flex flex-col items-center gap-2 text-center">
          <div className="flex size-12 items-center justify-center rounded-xl bg-linear-to-br from-sky-500 to-blue-700 text-white shadow-lg">
            <span className="text-2xl leading-none">💧</span>
          </div>
          <div>
            <h1 className="text-lg font-semibold">{t("app.name")}</h1>
            <p className="text-muted-foreground text-sm">{t("auth.subtitle")}</p>
          </div>
        </div>

        <form
          onSubmit={handleSubmit}
          className="space-y-4 rounded-xl border bg-card p-6 shadow-sm"
        >
          <div className="space-y-1.5">
            <Label htmlFor="username">{t("auth.username")}</Label>
            <div className="relative">
              <HugeiconsIcon
                icon={UserIcon}
                className="text-muted-foreground absolute left-2.5 top-1/2 size-4 -translate-y-1/2"
              />
              <Input
                id="username"
                className="pl-8"
                placeholder={t("auth.usernamePlaceholder")}
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                autoComplete="username"
                autoFocus
              />
            </div>
          </div>

          <div className="space-y-1.5">
            <Label htmlFor="password">{t("auth.password")}</Label>
            <div className="relative">
              <HugeiconsIcon
                icon={Key01Icon}
                className="text-muted-foreground absolute left-2.5 top-1/2 size-4 -translate-y-1/2"
              />
              <Input
                id="password"
                type="password"
                className="pl-8"
                placeholder={t("auth.passwordPlaceholder")}
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                autoComplete="current-password"
              />
            </div>
          </div>

          {error && (
            <div className="flex items-start gap-2 rounded-md border border-destructive/30 bg-destructive/5 px-3 py-2">
              <HugeiconsIcon icon={AlertCircleIcon} className="text-destructive mt-0.5 size-4 shrink-0" />
              <p className="text-destructive text-xs leading-snug">{error}</p>
            </div>
          )}

          <Button type="submit" className="w-full" disabled={busy || !username || !password}>
            {busy ? t("auth.loggingIn") : t("auth.login")}
          </Button>

          <div className="flex gap-2">
            <Button type="button" variant="outline" className="flex-1" onClick={fillDemo}>
              {t("auth.fillDemo")}
            </Button>
            <Button type="button" variant="secondary" className="flex-1" onClick={oneClickLogin}>
              {t("auth.login")}
            </Button>
          </div>

          {hint && (
            <p className="text-muted-foreground text-center text-xs">
              {t("auth.username")}: <span className="font-mono">{hint.username}</span> ·{" "}
              {t("auth.password")}: <span className="font-mono">{hint.password}</span>
            </p>
          )}
        </form>
      </div>
    </div>
  );
}
