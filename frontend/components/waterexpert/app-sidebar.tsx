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
  SidebarTrigger,
} from "@/components/ui/sidebar";
import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import { Button } from "@/components/ui/button";
import { useT } from "@/lib/i18n/use-t";
import { useAppStore } from "@/lib/stores/app-store";
import { HugeiconsIcon, type IconSvgElement } from "@hugeicons/react";
import {
  DashboardSquare01Icon,
  Database01Icon,
  ChartLineData01Icon,
  Activity01Icon,
  Search01Icon,
  SatelliteIcon,
  ClipboardIcon,
  Atom01Icon,
  Logout01Icon,
  Globe02Icon,
  Book01Icon,
  AiNetworkIcon,
  Task01Icon,
  Folder02Icon,
  AiBrain01Icon,
  DocumentAttachmentIcon,
  Alert01Icon,
} from "@hugeicons/core-free-icons";

type NavItem = {
  href: string;
  labelKey: string;
  icon: IconSvgElement;
};

const NAV_GROUPS: { labelKey: string; items: NavItem[] }[] = [
  {
    labelKey: "nav.groupOverview",
    items: [
      { href: "/", labelKey: "nav.overview", icon: DashboardSquare01Icon },
      { href: "/tasks", labelKey: "nav.tasks", icon: Task01Icon },
      { href: "/cases", labelKey: "nav.cases", icon: Folder02Icon },
    ],
  },
  {
    labelKey: "nav.groupGovernance",
    items: [
      { href: "/models", labelKey: "nav.models", icon: AiBrain01Icon },
      { href: "/reports", labelKey: "nav.reports", icon: DocumentAttachmentIcon },
      { href: "/events", labelKey: "nav.events", icon: Alert01Icon },
    ],
  },
  {
    labelKey: "nav.groupDatabase",
    items: [
      { href: "/database", labelKey: "nav.importDatabase", icon: Database01Icon },
      { href: "/query", labelKey: "nav.queryVisualization", icon: ChartLineData01Icon },
    ],
  },
  {
    labelKey: "nav.groupPrediction",
    items: [
      { href: "/prediction", labelKey: "nav.predictionValidation", icon: Activity01Icon },
      { href: "/diagnosis", labelKey: "nav.diagnosis", icon: Search01Icon },
      { href: "/response", labelKey: "nav.responsePlaybook", icon: ClipboardIcon },
      { href: "/boundary", labelKey: "nav.boundary", icon: SatelliteIcon },
    ],
  },
  {
    labelKey: "nav.groupLab",
    items: [
      { href: "/sensitivity", labelKey: "nav.sensitivity", icon: Atom01Icon },
      { href: "/knowledge-graph", labelKey: "nav.knowledgeGraph", icon: Book01Icon },
      { href: "/knowledge-graph/qa", labelKey: "nav.waterExpert", icon: AiNetworkIcon },
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
      <SidebarHeader className="border-b">
        <div className="flex h-14 items-center gap-2 px-3 group-data-[collapsible=icon]:justify-center group-data-[collapsible=icon]:px-0">
          <Link
            href="/"
            className="flex min-w-0 flex-1 items-center group-data-[collapsible=icon]:hidden"
          >
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img
              src="/ui/assets/waterexpert.png"
              alt={t("app.shortName")}
              className="h-11 w-auto"
            />
          </Link>
          <SidebarTrigger className="hidden shrink-0 md:inline-flex" />
        </div>
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
                      tooltip={t(item.labelKey)}
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
