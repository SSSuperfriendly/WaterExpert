"use client";

import * as React from "react";
import { useT } from "@/lib/i18n/use-t";
import { useApi } from "@/lib/hooks/use-api";
import { endpoints } from "@/lib/api/endpoints";
import { ApiError } from "@/lib/api/client";
import { describeApiError, translateRole } from "@/lib/domain";
import { getStoredToken } from "@/lib/auth-token";
import { useAppStore } from "@/lib/stores/app-store";
import type { UserProfile } from "@/lib/api/contracts";
import { AppShell } from "@/components/waterexpert/app-shell";
import { LoadingState, ErrorState } from "@/components/waterexpert/ui-states";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import { HugeiconsIcon } from "@hugeicons/react";
import {
  AlertCircleIcon,
  CheckmarkCircle01Icon,
  Github01Icon,
  Key01Icon,
  UserIcon,
} from "@hugeicons/core-free-icons";

function InlineMessage({ kind, text }: { kind: "error" | "success"; text: string }) {
  if (!text) return null;
  const isError = kind === "error";
  return (
    <div
      className={
        isError
          ? "flex items-start gap-2 rounded-md border border-destructive/30 bg-destructive/5 px-3 py-2"
          : "flex items-start gap-2 rounded-md border border-emerald-500/30 bg-emerald-500/5 px-3 py-2"
      }
    >
      <HugeiconsIcon
        icon={isError ? AlertCircleIcon : CheckmarkCircle01Icon}
        className={
          isError
            ? "text-destructive mt-0.5 size-4 shrink-0"
            : "text-emerald-600 mt-0.5 size-4 shrink-0 dark:text-emerald-400"
        }
      />
      <p
        className={
          isError
            ? "text-destructive text-xs leading-snug"
            : "text-emerald-700 text-xs leading-snug dark:text-emerald-300"
        }
      >
        {text}
      </p>
    </div>
  );
}

function InfoRow({
  label,
  value,
  hint,
}: {
  label: string;
  value: React.ReactNode;
  hint?: string;
}) {
  return (
    <div className="flex items-start justify-between gap-4 border-b py-3 last:border-b-0 last:pb-0">
      <span className="text-muted-foreground text-sm">{label}</span>
      <div className="text-right">
        <div className="text-sm font-medium">{value}</div>
        {hint ? <p className="text-muted-foreground text-xs">{hint}</p> : null}
      </div>
    </div>
  );
}

export default function ProfilePage() {
  const { t } = useT();
  const session = useAppStore((s) => s.session);
  const setSession = useAppStore((s) => s.setSession);

  const profile = useApi<UserProfile>(() => endpoints.profile());
  // After a mutation the backend returns the freshly-updated profile; prefer it
  // over the on-mount fetch so the summary reflects the change without a reload.
  const [liveProfile, setLiveProfile] = React.useState<UserProfile | null>(null);
  const current = liveProfile ?? profile.data;

  const errorText = (err: unknown): string => {
    if (err instanceof ApiError && err.status === 0) return t("auth.networkError");
    const message = describeApiError(t, err);
    return message.startsWith("errors.") ? t("common.error") : message;
  };

  // The display name is the one edit that needs no current password; it also
  // drives the sidebar/header, so a change updates the session in place.
  const [displayName, setDisplayName] = React.useState(session?.display_name ?? "");
  const [busyDisplay, setBusyDisplay] = React.useState(false);
  const [displayError, setDisplayError] = React.useState("");
  const [displaySaved, setDisplaySaved] = React.useState("");

  const applyProfile = (p: UserProfile) => {
    setLiveProfile(p);
    setDisplayName(p.display_name);
    setSession({
      username: p.username,
      display_name: p.display_name,
      role: p.role,
      access_token: getStoredToken() ?? undefined,
    });
  };

  const saveDisplayName = async (e: React.FormEvent) => {
    e.preventDefault();
    const name = displayName.trim();
    if (busyDisplay || !name) return;
    setBusyDisplay(true);
    setDisplayError("");
    setDisplaySaved("");
    try {
      applyProfile(await endpoints.updateProfile({ display_name: name }));
      setDisplaySaved(t("profile.displayNameSaved"));
    } catch (err) {
      setDisplayError(errorText(err));
    } finally {
      setBusyDisplay(false);
    }
  };

  // Change username: requires the current password (re-auth on the backend).
  const [username, setUsername] = React.useState("");
  const [usernamePassword, setUsernamePassword] = React.useState("");
  const [busyUsername, setBusyUsername] = React.useState(false);
  const [usernameError, setUsernameError] = React.useState("");
  const [usernameSaved, setUsernameSaved] = React.useState("");

  const saveUsername = async (e: React.FormEvent) => {
    e.preventDefault();
    const next = username.trim();
    if (busyUsername || !next || !usernamePassword) return;
    setBusyUsername(true);
    setUsernameError("");
    setUsernameSaved("");
    try {
      applyProfile(
        await endpoints.updateUsername({ username: next, current_password: usernamePassword })
      );
      setUsername("");
      setUsernamePassword("");
      setUsernameSaved(t("profile.usernameSaved"));
    } catch (err) {
      setUsernameError(errorText(err));
    } finally {
      setBusyUsername(false);
    }
  };

  // Change email: also re-authenticated with the current password.
  const [email, setEmail] = React.useState("");
  const [emailPassword, setEmailPassword] = React.useState("");
  const [busyEmail, setBusyEmail] = React.useState(false);
  const [emailError, setEmailError] = React.useState("");
  const [emailSaved, setEmailSaved] = React.useState("");

  const saveEmail = async (e: React.FormEvent) => {
    e.preventDefault();
    const next = email.trim();
    if (busyEmail || !next || !emailPassword) return;
    setBusyEmail(true);
    setEmailError("");
    setEmailSaved("");
    try {
      applyProfile(
        await endpoints.updateEmail({ email: next, current_password: emailPassword })
      );
      setEmail("");
      setEmailPassword("");
      setEmailSaved(t("profile.emailSaved"));
    } catch (err) {
      setEmailError(errorText(err));
    } finally {
      setBusyEmail(false);
    }
  };

  // Change password (for accounts that already have one).
  const [currentPassword, setCurrentPassword] = React.useState("");
  const [newPassword, setNewPassword] = React.useState("");
  const [confirmPassword, setConfirmPassword] = React.useState("");
  const [busyPassword, setBusyPassword] = React.useState(false);
  const [passwordError, setPasswordError] = React.useState("");

  const savePassword = async (e: React.FormEvent) => {
    e.preventDefault();
    if (busyPassword || !currentPassword || !newPassword || !confirmPassword) return;
    if (newPassword.length < 8) {
      setPasswordError(t("profile.passwordTooShort"));
      return;
    }
    if (newPassword !== confirmPassword) {
      setPasswordError(t("profile.passwordMismatch"));
      return;
    }
    setBusyPassword(true);
    setPasswordError("");
    try {
      applyProfile(
        await endpoints.changePassword({
          current_password: currentPassword,
          new_password: newPassword,
        })
      );
      setCurrentPassword("");
      setNewPassword("");
      setConfirmPassword("");
    } catch (err) {
      setPasswordError(errorText(err));
    } finally {
      setBusyPassword(false);
    }
  };

  // ---- Set a first password (OAuth-only account, empty hash) ----
  // The account holder proves identity with a fresh GitHub re-auth: the backend
  // callback lands back here on /profile?reauth_token=... (or ?reauth=denied),
  // which we consume once and drop from the URL so a refresh cannot replay it.
  const [reauthToken, setReauthToken] = React.useState<string | null>(null);
  const [reauthDenied, setReauthDenied] = React.useState(false);
  const [reauthBusy, setReauthBusy] = React.useState(false);
  // A success that outlives the set-password card (once the password is set the
  // page flips to the password-gated cards, so the banner lives above them).
  const [passwordSetFlash, setPasswordSetFlash] = React.useState("");

  React.useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const token = params.get("reauth_token");
    const denied = params.get("reauth") === "denied";
    if (!token && !denied) return;
    window.history.replaceState({}, "", window.location.pathname);
    // One-time consumption of an external handoff the OAuth callback left in the
    // URL (same pattern as the login page's ?access_token landing). State set
    // after hydration, so the URL is the source of truth exactly once.
    /* eslint-disable react-hooks/set-state-in-effect -- consume reauth handoff from URL */
    if (token) setReauthToken(token);
    if (denied) setReauthDenied(true);
    /* eslint-enable react-hooks/set-state-in-effect */
  }, []);

  const startReauth = async () => {
    setReauthBusy(true);
    setPasswordError("");
    setReauthDenied(false);
    try {
      const { authorization_url } = await endpoints.setPasswordAuthorize();
      window.location.href = authorization_url;
    } catch (err) {
      setPasswordError(errorText(err));
      setReauthBusy(false);
    }
  };

  const submitSetPassword = async (e: React.FormEvent) => {
    e.preventDefault();
    if (busyPassword || !reauthToken || !newPassword || !confirmPassword) return;
    if (newPassword.length < 8) {
      setPasswordError(t("profile.passwordTooShort"));
      return;
    }
    if (newPassword !== confirmPassword) {
      setPasswordError(t("profile.passwordMismatch"));
      return;
    }
    setBusyPassword(true);
    setPasswordError("");
    try {
      applyProfile(
        await endpoints.setPassword({
          new_password: newPassword,
          confirm_password: confirmPassword,
          reauth_token: reauthToken,
        })
      );
      setReauthToken(null);
      setNewPassword("");
      setConfirmPassword("");
      setPasswordSetFlash(t("profile.passwordSetSaved"));
    } catch (err) {
      setPasswordError(errorText(err));
    } finally {
      setBusyPassword(false);
    }
  };

  const initials = (current?.display_name || session?.display_name || "WE")
    .slice(0, 2)
    .toUpperCase();

  // OAuth-only accounts report has_password=false until they set one; everything
  // else (password-registered and set-password graduates) goes through the
  // password-gated username/email/password cards below.
  const hasPassword = current ? current.has_password : true;

  return (
    <AppShell title={t("profile.title")}>
      {profile.loading ? (
        <LoadingState />
      ) : profile.error ? (
        <ErrorState error={profile.error} onRetry={profile.reload} />
      ) : (
        <>
          <div className="space-y-4">
            {/* Identity summary */}
            <Card>
              <CardHeader>
                <CardTitle className="text-base">{t("profile.accountInfo")}</CardTitle>
              </CardHeader>
              <CardContent>
                <div className="flex items-center gap-4 pb-4">
                  <Avatar className="size-12">
                    <AvatarFallback className="text-sm">{initials}</AvatarFallback>
                  </Avatar>
                  <div className="min-w-0">
                    <p className="truncate text-base font-semibold">
                      {current?.display_name}
                    </p>
                    <p className="text-muted-foreground text-sm">
                      {current?.email || current?.username}
                    </p>
                  </div>
                </div>
                <div className="divide-y divide-border">
                  <InfoRow
                    label={t("profile.username")}
                    value={current?.username ?? "—"}
                    hint={t("profile.usernameHint")}
                  />
                  <InfoRow
                    label={t("profile.email")}
                    value={
                      current ? (
                        <span className="flex items-center justify-end gap-2">
                          {current.email}
                          {current.is_verified ? (
                            <Badge variant="outline">{t("profile.verified")}</Badge>
                          ) : (
                            <Badge variant="secondary">{t("profile.unverified")}</Badge>
                          )}
                        </span>
                      ) : (
                        "—"
                      )
                    }
                    hint={t("profile.emailHint")}
                  />
                  <InfoRow
                    label={t("profile.role")}
                    value={current ? translateRole(t, current.role) : "—"}
                    hint={t("profile.roleImmutable")}
                  />
                  <InfoRow
                    label={t("profile.linkedAccounts")}
                    value={
                      current && current.oauth_providers.length > 0
                        ? current.oauth_providers
                            .map((provider) =>
                              provider === "github"
                                ? t("profile.linkedGithub")
                                : provider
                            )
                            .join(", ")
                        : t("profile.noLinkedAccounts")
                    }
                  />
                </div>
              </CardContent>
            </Card>

            {/* Display name */}
            <Card>
              <CardHeader>
                <CardTitle className="text-base">{t("profile.basic")}</CardTitle>
                <CardDescription>{t("profile.displayNameHint")}</CardDescription>
              </CardHeader>
              <CardContent>
                <form onSubmit={saveDisplayName} className="space-y-4">
                  <div className="max-w-md space-y-1.5">
                    <Label htmlFor="display-name">{t("profile.displayName")}</Label>
                    <div className="relative">
                      <HugeiconsIcon
                        icon={UserIcon}
                        className="text-muted-foreground absolute left-3 top-1/2 size-4 -translate-y-1/2"
                      />
                      <Input
                        id="display-name"
                        className="h-10 pl-9"
                        value={displayName}
                        onChange={(e) => setDisplayName(e.target.value)}
                        maxLength={120}
                      />
                    </div>
                  </div>
                  <InlineMessage kind="error" text={displayError} />
                  <InlineMessage kind="success" text={displaySaved} />
                  <Button
                    type="submit"
                    disabled={busyDisplay || !displayName.trim()}
                  >
                    {busyDisplay ? t("profile.saving") : t("profile.save")}
                  </Button>
                </form>
              </CardContent>
            </Card>

            {passwordSetFlash && (
              <InlineMessage kind="success" text={passwordSetFlash} />
            )}

            {hasPassword ? (
              <>
                {/* Username / email / password share one security hint */}
                <Card>
                  <CardHeader>
                    <CardTitle className="text-base">{t("profile.changeUsername")}</CardTitle>
                    <CardDescription>{t("profile.securityHint")}</CardDescription>
                  </CardHeader>
                  <CardContent>
                    <form onSubmit={saveUsername} className="space-y-4">
                      <div className="grid max-w-2xl gap-4 sm:grid-cols-2">
                        <div className="space-y-1.5">
                          <Label htmlFor="new-username">{t("profile.newUsername")}</Label>
                          <Input
                            id="new-username"
                            className="h-10"
                            value={username}
                            onChange={(e) => setUsername(e.target.value)}
                            autoComplete="off"
                            maxLength={64}
                          />
                        </div>
                        <div className="space-y-1.5">
                          <Label htmlFor="username-current-password">
                            {t("profile.currentPassword")}
                          </Label>
                          <Input
                            id="username-current-password"
                            type="password"
                            className="h-10"
                            value={usernamePassword}
                            onChange={(e) => setUsernamePassword(e.target.value)}
                            autoComplete="current-password"
                          />
                        </div>
                      </div>
                      <InlineMessage kind="error" text={usernameError} />
                      <InlineMessage kind="success" text={usernameSaved} />
                      <Button
                        type="submit"
                        disabled={busyUsername || !username.trim() || !usernamePassword}
                      >
                        {busyUsername ? t("profile.saving") : t("profile.save")}
                      </Button>
                    </form>
                  </CardContent>
                </Card>

                <Card>
                  <CardHeader>
                    <CardTitle className="text-base">{t("profile.changeEmail")}</CardTitle>
                  </CardHeader>
                  <CardContent>
                    <form onSubmit={saveEmail} className="space-y-4">
                      <div className="grid max-w-2xl gap-4 sm:grid-cols-2">
                        <div className="space-y-1.5">
                          <Label htmlFor="new-email">{t("profile.newEmail")}</Label>
                          <Input
                            id="new-email"
                            type="email"
                            className="h-10"
                            value={email}
                            onChange={(e) => setEmail(e.target.value)}
                            autoComplete="email"
                            maxLength={254}
                          />
                        </div>
                        <div className="space-y-1.5">
                          <Label htmlFor="email-current-password">
                            {t("profile.currentPassword")}
                          </Label>
                          <Input
                            id="email-current-password"
                            type="password"
                            className="h-10"
                            value={emailPassword}
                            onChange={(e) => setEmailPassword(e.target.value)}
                            autoComplete="current-password"
                          />
                        </div>
                      </div>
                      <InlineMessage kind="error" text={emailError} />
                      <InlineMessage kind="success" text={emailSaved} />
                      <Button
                        type="submit"
                        disabled={busyEmail || !email.trim() || !emailPassword}
                      >
                        {busyEmail ? t("profile.saving") : t("profile.save")}
                      </Button>
                    </form>
                  </CardContent>
                </Card>

                <Card>
                  <CardHeader>
                    <CardTitle className="text-base">{t("profile.changePassword")}</CardTitle>
                    <CardDescription>{t("profile.passwordChangeNote")}</CardDescription>
                  </CardHeader>
                  <CardContent>
                    <form onSubmit={savePassword} className="space-y-4">
                      <div className="grid max-w-2xl gap-4 sm:grid-cols-3">
                        <div className="space-y-1.5">
                          <Label htmlFor="password-current">{t("profile.currentPassword")}</Label>
                          <div className="relative">
                            <HugeiconsIcon
                              icon={Key01Icon}
                              className="text-muted-foreground absolute left-3 top-1/2 size-4 -translate-y-1/2"
                            />
                            <Input
                              id="password-current"
                              type="password"
                              className="h-10 pl-9"
                              value={currentPassword}
                              onChange={(e) => setCurrentPassword(e.target.value)}
                              autoComplete="current-password"
                            />
                          </div>
                        </div>
                        <div className="space-y-1.5">
                          <Label htmlFor="password-new">{t("profile.newPassword")}</Label>
                          <Input
                            id="password-new"
                            type="password"
                            className="h-10"
                            value={newPassword}
                            onChange={(e) => setNewPassword(e.target.value)}
                            autoComplete="new-password"
                          />
                        </div>
                        <div className="space-y-1.5">
                          <Label htmlFor="password-confirm">
                            {t("profile.confirmNewPassword")}
                          </Label>
                          <Input
                            id="password-confirm"
                            type="password"
                            className="h-10"
                            value={confirmPassword}
                            onChange={(e) => setConfirmPassword(e.target.value)}
                            autoComplete="new-password"
                          />
                        </div>
                      </div>
                      <InlineMessage kind="error" text={passwordError} />
                      <Button
                        type="submit"
                        disabled={
                          busyPassword ||
                          !currentPassword ||
                          !newPassword ||
                          !confirmPassword
                        }
                      >
                        {busyPassword ? t("profile.saving") : t("profile.save")}
                      </Button>
                    </form>
                  </CardContent>
                </Card>
              </>
            ) : (
              <>
                {/* Set a first password on an OAuth-only account */}
                <Card>
                  <CardHeader>
                    <CardTitle className="text-base">{t("profile.setPasswordTitle")}</CardTitle>
                    <CardDescription>{t("profile.setPasswordIntro")}</CardDescription>
                  </CardHeader>
                  <CardContent className="space-y-4">
                    {reauthDenied && <InlineMessage kind="error" text={t("profile.reauthDenied")} />}
                    <InlineMessage kind="error" text={passwordError} />
                    {reauthToken ? (
                      <form onSubmit={submitSetPassword} className="space-y-4">
                        <div className="flex items-start gap-2 text-xs text-muted-foreground">
                          <HugeiconsIcon icon={CheckmarkCircle01Icon} className="mt-0.5 size-4 shrink-0 text-emerald-600 dark:text-emerald-400" />
                          <p>{t("profile.setPasswordNote")}</p>
                        </div>
                        <div className="grid max-w-2xl gap-4 sm:grid-cols-2">
                          <div className="space-y-1.5">
                            <Label htmlFor="set-password-new">{t("profile.newPassword")}</Label>
                            <Input
                              id="set-password-new"
                              type="password"
                              className="h-10"
                              value={newPassword}
                              onChange={(e) => setNewPassword(e.target.value)}
                              autoComplete="new-password"
                            />
                          </div>
                          <div className="space-y-1.5">
                            <Label htmlFor="set-password-confirm">
                              {t("profile.confirmNewPassword")}
                            </Label>
                            <Input
                              id="set-password-confirm"
                              type="password"
                              className="h-10"
                              value={confirmPassword}
                              onChange={(e) => setConfirmPassword(e.target.value)}
                              autoComplete="new-password"
                            />
                          </div>
                        </div>
                        <Button
                          type="submit"
                          disabled={busyPassword || !newPassword || !confirmPassword}
                        >
                          {busyPassword ? t("profile.saving") : t("profile.setPasswordConfirmAction")}
                        </Button>
                      </form>
                    ) : (
                      <div className="space-y-3">
                        <div className="flex items-start gap-2 text-xs text-muted-foreground">
                          <HugeiconsIcon icon={Key01Icon} className="mt-0.5 size-4 shrink-0" />
                          <p>{t("profile.setPasswordReauthHint")}</p>
                        </div>
                        <Button
                          type="button"
                          variant="outline"
                          onClick={startReauth}
                          disabled={reauthBusy}
                        >
                          <HugeiconsIcon icon={Github01Icon} className="size-4" />
                          {reauthBusy
                            ? t("profile.setPasswordReauthing")
                            : t("profile.setPasswordAction")}
                        </Button>
                      </div>
                    )}
                  </CardContent>
                </Card>

                {/* What unlocks once a password is set */}
                <Card>
                  <CardContent>
                    <div className="flex items-start gap-3">
                      <HugeiconsIcon icon={Key01Icon} className="text-muted-foreground mt-0.5 size-4 shrink-0" />
                      <div className="min-w-0">
                        <p className="text-sm font-medium">{t("profile.passwordUnlockHint")}</p>
                        <p className="text-muted-foreground text-xs">
                          {t("profile.changeUsername")} · {t("profile.changeEmail")} ·{" "}
                          {t("profile.changePassword")}
                        </p>
                      </div>
                    </div>
                  </CardContent>
                </Card>
              </>
            )}
          </div>
        </>
      )}
    </AppShell>
  );
}
