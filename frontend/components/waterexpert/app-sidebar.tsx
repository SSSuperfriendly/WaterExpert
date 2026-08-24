"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import {
  Sidebar,
  SidebarContent,
  SidebarFooter,
  SidebarGroup,
  SidebarGroupContent,
  SidebarGroupLabel,
  SidebarHeader,
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
} from "@/components/ui/sidebar";
import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import { Button } from "@/components/ui/button";
import { useT } from "@/lib/i18n/use-t";
import { useAppStore } from "@/lib/stores/app-store";
import { HugeiconsIcon, type IconSvgElement } from "@hugeicons/react";
import {
  DashboardSquare01Icon,
  Database01Icon,
  Upload01Icon,
  FilterHorizontalIcon,
  ChartLineData01Icon,
  Activity01Icon,
  Search01Icon,
  SlidersHorizontalIcon,
  SatelliteIcon,
  Flag01Icon,
  ClipboardIcon,
  Atom01Icon,
  RefreshIcon,
  Logout01Icon,
  Globe02Icon,
} from "@hugeicons/core-free-icons";

type NavItem = {
  href: string;
  labelKey: string;
  icon: IconSvgElement;
};

const NAV_GROUPS: { labelKey: string; items: NavItem[] }[] = [
  {
    labelKey: "nav.overview",
    items: [{ href: "/", labelKey: "nav.overview", icon: DashboardSquare01Icon }],
  },
  {
    labelKey: "nav.database",
    items: [
      { href: "/database", labelKey: "nav.database", icon: Database01Icon },
      { href: "/upload", labelKey: "nav.upload", icon: Upload01Icon },
      { href: "/preprocess", labelKey: "nav.preprocess", icon: FilterHorizontalIcon },
      { href: "/visualization", labelKey: "nav.visualization", icon: ChartLineData01Icon },
    ],
  },
  {
    labelKey: "nav.prediction",
    items: [
      { href: "/prediction", labelKey: "nav.prediction", icon: Activity01Icon },
      { href: "/diagnosis", labelKey: "nav.diagnosis", icon: Search01Icon },
      { href: "/thresholds", labelKey: "nav.thresholds", icon: SlidersHorizontalIcon },
    ],
  },
  {
    labelKey: "nav.boundary",
    items: [
      { href: "/boundary", labelKey: "nav.boundary", icon: SatelliteIcon },
      { href: "/scenario", labelKey: "nav.scenario", icon: Flag01Icon },
      { href: "/playbook", labelKey: "nav.playbook", icon: ClipboardIcon },
    ],
  },
  {
    labelKey: "nav.sensitivity",
    items: [
      { href: "/sensitivity", labelKey: "nav.sensitivity", icon: Atom01Icon },
      { href: "/realtime", labelKey: "nav.realtime", icon: RefreshIcon },
    ],
  },
];

export function AppSidebar({ ...props }: React.ComponentProps<typeof Sidebar>) {
  const { t, locale, setLocale } = useT();
  const session = useAppStore((s) => s.session);
  const clearSession = useAppStore((s) => s.clearSession);
  const pathname = usePathname();
  const router = useRouter();

  const isActive = (href: string) => {
    if (href === "/") return pathname === "/";
    return pathname === href || pathname.startsWith(`${href}/`);
  };

  const initials = (session?.display_name || "WE").slice(0, 2).toUpperCase();

  const handleLogout = () => {
    clearSession();
    router.replace("/login");
  };

  return (
    <Sidebar collapsible="icon" {...props}>
      <SidebarHeader className="gap-3 border-b p-4">
        <Link href="/" className="flex items-center gap-2.5 px-1">
          <div className="flex size-8 shrink-0 items-center justify-center rounded-md bg-linear-to-br from-sky-500 to-blue-700 text-white">
            <span className="text-base leading-none">💧</span>
          </div>
          <div className="min-w-0">
            <p className="truncate text-sm font-semibold leading-tight">
              {t("app.shortName")}
            </p>
            <p className="text-muted-foreground truncate text-[11px] leading-tight">
              {t("app.tagline")}
            </p>
          </div>
        </Link>
      </SidebarHeader>

      <SidebarContent className="gap-3 px-3 py-3">
        {NAV_GROUPS.map((group) => (
          <SidebarGroup key={group.labelKey} className="p-0">
            <SidebarGroupLabel>{t(group.labelKey)}</SidebarGroupLabel>
            <SidebarGroupContent>
              <SidebarMenu>
                {group.items.map((item) => (
                  <SidebarMenuItem key={item.href}>
                    <SidebarMenuButton
                      isActive={isActive(item.href)}
                      render={<Link href={item.href} />}
                    >
                      <HugeiconsIcon icon={item.icon} className="size-5" />
                      <span className="flex-1">{t(item.labelKey)}</span>
                    </SidebarMenuButton>
                  </SidebarMenuItem>
                ))}
              </SidebarMenu>
            </SidebarGroupContent>
          </SidebarGroup>
        ))}
      </SidebarContent>

      <SidebarFooter className="gap-2 border-t p-3">
        <Button
          variant="ghost"
          size="sm"
          className="w-full justify-start gap-2"
          onClick={() => setLocale(locale === "zh-CN" ? "en-US" : "zh-CN")}
        >
          <HugeiconsIcon icon={Globe02Icon} className="size-4" />
          <span className="flex-1 text-left">
            {locale === "zh-CN" ? "English" : "简体中文"}
          </span>
        </Button>

        <div className="flex items-center gap-2 rounded-md border p-2">
          <Avatar className="size-8">
            <AvatarFallback>{initials}</AvatarFallback>
          </Avatar>
          <div className="min-w-0 flex-1">
            <p className="truncate text-sm font-medium leading-tight">
              {session?.display_name}
            </p>
            <p className="text-muted-foreground truncate text-xs leading-tight">
              {t("auth.role")}: {session ? t(`roles.${session.role}`) : "—"}
            </p>
          </div>
          <Button variant="ghost" size="icon-sm" onClick={handleLogout} title={t("auth.logout")}>
            <HugeiconsIcon icon={Logout01Icon} className="size-4" />
          </Button>
        </div>
      </SidebarFooter>
    </Sidebar>
  );
}
