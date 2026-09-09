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
  Key01Icon,
  UserIcon,
  AlertCircleIcon,
  Github01Icon,
} from "@hugeicons/core-free-icons";

// OAuth session consumption must be idempotent across re-mounts of the login
// page. The landing URL /login?access_token=... can mount the page more than
// once during the initial client navigation; a per-mount ref lets a later
// re-mount re-consume a leftover ?access_token entry and silently log the user
// back in — which made "log out" appear broken after a GitHub sign-in. This
// flag lives at module scope so it survives those re-mounts. A real GitHub
// round-trip always reloads the page (→ GitHub → back), which resets it, so a
// later sign-in in the same tab still works.
let oauthSessionConsumed = false;

export default function LoginPage() {
  const { t } = useT();
  const router = useRouter();
  const session = useAppStore((s) => s.session);
  const setSession = useAppStore((s) => s.setSession);

  const [username, setUsername] = React.useState("");
  const [password, setPassword] = React.useState("");
  const [error, setError] = React.useState<string | null>(null);
  const [busy, setBusy] = React.useState(false);

  React.useEffect(() => {
    if (session) router.replace("/");
  }, [session, router]);

  // GitHub OAuth lands back here via /ui/login?access_token=...&username=...
  // (the backend 302's after minting the session). Consume it once, store the
  // session, then drop the token from the URL before navigating home.
  React.useEffect(() => {
    if (oauthSessionConsumed) return;
    const params = new URLSearchParams(window.location.search);
    if (!params.has("access_token") && !params.has("error")) return;
    oauthSessionConsumed = true;
    const token = params.get("access_token");
    const error = params.get("error");
    window.history.replaceState({}, "", window.location.pathname);
    if (token) {
      const username = params.get("username") ?? "";
      setSession({
        username,
        display_name: params.get("display_name") ?? username,
        role: params.get("role") ?? "reviewer",
        access_token: token,
      });
      // Full-document redirect rather than router.replace("/"): hand-editing the
      // URL with history.replaceState while next/router is mid-navigation left
      // duplicate ?access_token history entries, and a later logout landed back
      // on one of them and re-logged the user in (logout "failed" after GitHub
      // sign-in). A hard replace gives one clean history entry for the app root.
      window.location.replace("/ui/");
    } else {
      setError(
        error === "oauth_failed" ? t("auth.oauthFailed") : t("auth.loginFailed")
      );
    }
  }, [router, setSession, t]);

  const handleGithub = async () => {
    setError(null);
    try {
      const { authorization_url } = await endpoints.githubOAuthAuthorize();
      window.location.href = authorization_url;
    } catch {
      setError(t("auth.oauthNotConfigured"));
    }
  };

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
          access_token: profile.access_token,
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
    if (busy || !username || !password) return;
    doLogin(username, password);
  };

  return (
    <AuthShell formTitle={t("auth.login")} formDescription={t("auth.loginSubtitle")}>
      <form onSubmit={handleSubmit} className="space-y-4">
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
              autoComplete="username"
              autoFocus
            />
          </div>
        </div>

        <div className="space-y-1.5">
          <div className="flex items-center justify-between">
            <Label htmlFor="password">{t("auth.password")}</Label>
            <Link
              href="/forgot-password"
              className="text-sm font-medium text-primary underline-offset-4 hover:underline"
            >
              {t("auth.forgotPassword")}
            </Link>
          </div>
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
              autoComplete="current-password"
            />
          </div>
        </div>

        {error && (
          <div className="flex items-start gap-2 rounded-md border border-destructive/30 bg-destructive/5 px-3 py-2">
            <HugeiconsIcon
              icon={AlertCircleIcon}
              className="text-destructive mt-0.5 size-4 shrink-0"
            />
            <p className="text-destructive text-xs leading-snug">{error}</p>
          </div>
        )}

        <Button
          type="submit"
          className="h-10 w-full bg-linear-to-br from-sky-500 to-blue-700 text-white hover:from-sky-600 hover:to-blue-800"
          disabled={busy || !username || !password}
        >
          {busy ? t("auth.loggingIn") : t("auth.login")}
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
          disabled={busy}
        >
          <HugeiconsIcon icon={Github01Icon} className="size-4" />
          {t("auth.githubSignIn")}
        </Button>

        <p className="text-muted-foreground text-center text-sm">
          {t("auth.noAccount")}{" "}
          <Link
            href="/register"
            className="text-primary font-semibold underline-offset-4 hover:underline"
          >
            {t("auth.signUpNow")}
          </Link>
        </p>
      </form>
    </AuthShell>
  );
}
