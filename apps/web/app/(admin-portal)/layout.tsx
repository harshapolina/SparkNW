"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Bell,
  BookOpen,
  Camera,
  ChevronDown,
  Database,
  Download,
  FileSpreadsheet,
  Layers,
  LayoutDashboard,
  Medal,
  Moon,
  RefreshCw,
  Settings,
  Sun,
  BarChart3,
  Trophy,
  Upload,
  Video,
} from "lucide-react";
import { clearTokens, getStoredUser, type User, api } from "@/lib/api";
import { BrandLogo } from "@/components/brand-logo";
import { useRequireRole } from "@/lib/spark/auth-guard";
import { adminScrapingListHref } from "@/lib/admin-scraping-list-state";
import { applyDarkMode } from "@/lib/dark-mode";
import { cn } from "@/lib/utils";

const scrapingChildren = [
  { href: "/admin-scraping/youtube", label: "YouTube", icon: Video },
  { href: "/admin-scraping/instagram", label: "Instagram", icon: Camera },
  { href: "/admin-scraping", label: "Overall", icon: Layers, exact: true },
] as const;

const dashboardChildren = [
  { href: "/admin-dashboard/youtube", label: "YouTube", icon: Video },
  { href: "/admin-dashboard/instagram", label: "Instagram", icon: Camera },
  { href: "/admin-dashboard", label: "Overall", icon: Layers, exact: true },
] as const;

type NavChild = {
  href: string;
  label: string;
  icon: typeof Video;
  exact?: boolean;
};

const nav: {
  href: string;
  label: string;
  icon: typeof LayoutDashboard;
  children?: readonly NavChild[];
}[] = [
  { href: "/admin-dashboard", label: "Dashboard", icon: LayoutDashboard, children: dashboardChildren },
  { href: "/admin-leaderboard", label: "Leaderboard", icon: Trophy },
  { href: "/admin-scraping", label: "Scraping", icon: RefreshCw, children: scrapingChildren },
  { href: "/admin-analytics", label: "Analytics", icon: BarChart3 },
  { href: "/admin-alerts", label: "Alerts", icon: Bell },
  { href: "/admin-import", label: "Import roster", icon: Upload },
  { href: "/admin-unimported", label: "Unimported", icon: FileSpreadsheet },
  { href: "/admin-settings", label: "Settings", icon: Settings },
  { href: "/top-10", label: "Public Top 10", icon: Medal },
  { href: "/admin-how-it-works", label: "How it works", icon: BookOpen },
];

function sectionChildActive(pathname: string, base: string, href: string, exact?: boolean) {
  if (href === `${base}/youtube`) return pathname.startsWith(`${base}/youtube`);
  if (href === `${base}/instagram`) return pathname.startsWith(`${base}/instagram`);
  if (exact) {
    return (
      pathname === base ||
      (pathname.startsWith(`${base}/`) &&
        !pathname.startsWith(`${base}/youtube`) &&
        !pathname.startsWith(`${base}/instagram`))
    );
  }
  return pathname.startsWith(base);
}

function parentHref(itemHref: string) {
  if (itemHref === "/admin-scraping") return adminScrapingListHref();
  return itemHref;
}

function childHref(href: string) {
  if (href === "/admin-scraping") return adminScrapingListHref();
  return href;
}

export default function AdminPortalLayout({ children }: { children: React.ReactNode }) {
  const ready = useRequireRole("admin", "/admin-login");
  const pathname = usePathname();
  const router = useRouter();
  const qc = useQueryClient();
  const [user, setUser] = useState<User | null>(null);
  const [expanded, setExpanded] = useState<Record<string, boolean>>({
    "/admin-dashboard": pathname.startsWith("/admin-dashboard"),
    "/admin-scraping": pathname.startsWith("/admin-scraping"),
  });

  const settingsQ = useQuery({
    queryKey: ["settings"],
    queryFn: () => api<{ dark_mode: boolean }>("/settings"),
    enabled: ready,
  });
  const darkOn = settingsQ.data?.dark_mode !== false;

  const darkToggle = useMutation({
    mutationFn: (dark_mode: boolean) =>
      api<{ dark_mode: boolean }>("/settings", {
        method: "PATCH",
        body: JSON.stringify({ dark_mode }),
      }),
    onSuccess: (data) => {
      qc.setQueryData(["settings"], (prev: { dark_mode?: boolean } | undefined) => ({
        ...(prev || {}),
        ...data,
      }));
      applyDarkMode(data.dark_mode);
    },
  });

  useEffect(() => {
    setUser(getStoredUser());
  }, [ready]);

  useEffect(() => {
    if (typeof settingsQ.data?.dark_mode === "boolean") {
      applyDarkMode(settingsQ.data.dark_mode);
    }
  }, [settingsQ.data?.dark_mode]);

  useEffect(() => {
    setExpanded((prev) => {
      const next = { ...prev };
      if (pathname.startsWith("/admin-dashboard")) next["/admin-dashboard"] = true;
      if (pathname.startsWith("/admin-scraping")) next["/admin-scraping"] = true;
      return next;
    });
  }, [pathname]);

  if (!ready) {
    return (
      <div className="grid min-h-screen place-items-center bg-black text-sm text-zinc-500">
        Loading admin portal…
      </div>
    );
  }

  return (
    <div
      className={cn(
        "flex min-h-screen text-white transition-colors",
        darkOn
          ? "bg-[#050505] [background-image:radial-gradient(1200px_500px_at_10%_-10%,rgba(255,59,48,0.12),transparent),radial-gradient(800px_400px_at_100%_0%,rgba(88,28,135,0.12),transparent)]"
          : "bg-zinc-100 text-zinc-900"
      )}
    >
      <aside
        className={cn(
          "sticky top-0 hidden h-screen w-[232px] shrink-0 flex-col border-r lg:flex",
          darkOn ? "border-white/[0.06] bg-[#0a0a0a]/90 backdrop-blur-xl" : "border-zinc-200 bg-white"
        )}
      >
        <div className="px-4 py-5">
          <Link href="/admin-dashboard" className="inline-flex items-center">
            <BrandLogo height={26} priority />
          </Link>
          <div className="mt-2 text-[10px] font-semibold uppercase tracking-[0.16em] text-[#ff3b30]">
            Admin
          </div>
        </div>
        <nav className="admin-sidebar-nav flex-1 space-y-0.5 overflow-y-auto px-3 py-2">
          {nav.map((item) => {
            const Icon = item.icon;
            const hasChildren = Boolean(item.children?.length);
            const isOpen = Boolean(expanded[item.href]);
            const parentActive = hasChildren
              ? pathname.startsWith(item.href)
              : pathname === item.href || pathname.startsWith(item.href + "/");

            if (hasChildren && item.children) {
              return (
                <div key={item.href} className="pt-0.5">
                  <div
                    className={cn(
                      "flex items-center rounded-xl transition",
                      parentActive && !isOpen
                        ? "bg-[#ff3b30] text-white shadow-lg shadow-[#ff3b30]/20"
                        : parentActive
                          ? "bg-white/[0.04] text-zinc-100"
                          : "text-zinc-400 hover:bg-white/[0.04] hover:text-zinc-100"
                    )}
                  >
                    <Link
                      href={parentHref(item.href)}
                      className="flex min-w-0 flex-1 items-center gap-2.5 px-3 py-2.5 text-[13px]"
                      onClick={() => setExpanded((prev) => ({ ...prev, [item.href]: true }))}
                    >
                      <Icon size={16} />
                      {item.label}
                    </Link>
                    <button
                      type="button"
                      aria-label={isOpen ? `Collapse ${item.label}` : `Expand ${item.label}`}
                      aria-expanded={isOpen}
                      onClick={() =>
                        setExpanded((prev) => ({ ...prev, [item.href]: !prev[item.href] }))
                      }
                      className="mr-1 rounded-lg p-1.5 hover:bg-white/10"
                    >
                      <ChevronDown
                        size={14}
                        className={cn("transition-transform", isOpen && "rotate-180")}
                      />
                    </button>
                  </div>
                  <div
                    className={cn(
                      "grid transition-[grid-template-rows] duration-200 ease-out",
                      isOpen ? "grid-rows-[1fr]" : "grid-rows-[0fr]"
                    )}
                  >
                    <div className="overflow-hidden">
                      <div className="relative ml-[22px] mt-1 space-y-0.5 border-l border-white/10 pb-1 pl-3">
                        {item.children.map((child) => {
                          const ChildIcon = child.icon;
                          const childActive = sectionChildActive(
                            pathname,
                            item.href,
                            child.href,
                            child.exact
                          );
                          return (
                            <Link
                              key={child.href + child.label}
                              href={childHref(child.href)}
                              className={cn(
                                "flex items-center gap-2 rounded-lg px-2.5 py-1.5 text-[12px] transition",
                                childActive
                                  ? "bg-[#ff3b30] text-white shadow-md shadow-[#ff3b30]/15"
                                  : "text-zinc-500 hover:bg-white/[0.04] hover:text-zinc-200"
                              )}
                            >
                              <ChildIcon size={13} />
                              {child.label}
                            </Link>
                          );
                        })}
                      </div>
                    </div>
                  </div>
                </div>
              );
            }

            return (
              <Link
                key={item.href}
                href={item.href}
                className={cn(
                  "flex items-center gap-2.5 rounded-xl px-3 py-2.5 text-[13px] transition",
                  parentActive
                    ? "bg-[#ff3b30] text-white shadow-lg shadow-[#ff3b30]/20"
                    : "text-zinc-400 hover:bg-white/[0.04] hover:text-zinc-100"
                )}
              >
                <Icon size={16} />
                {item.label}
              </Link>
            );
          })}
        </nav>
        <div className={cn("space-y-2 border-t p-4 text-[11px]", darkOn ? "border-white/[0.06] text-zinc-500" : "border-zinc-200 text-zinc-500")}>
          <button
            type="button"
            disabled={darkToggle.isPending}
            onClick={() => darkToggle.mutate(!darkOn)}
            className={cn(
              "mb-2 flex w-full items-center justify-between rounded-xl px-2.5 py-2 text-left text-[12px] transition",
              darkOn ? "bg-white/[0.04] text-zinc-200 hover:bg-white/[0.07]" : "bg-zinc-100 text-zinc-800"
            )}
          >
            <span className="inline-flex items-center gap-2">
              {darkOn ? <Moon size={13} className="text-[#ff3b30]" /> : <Sun size={13} />}
              {darkOn ? "Void dark" : "Light desk"}
            </span>
            <span className="text-[10px] uppercase tracking-wide text-zinc-500">{darkOn ? "On" : "Off"}</span>
          </button>
          <div className="flex items-center gap-2 text-zinc-400">
            <Database size={12} /> Shared cohort scrapes
          </div>
          <div className="flex items-center gap-2 text-zinc-400">
            <Download size={12} /> Export from Scraping table
          </div>
          <div className="mb-2 mt-3 truncate">{user?.name || user?.email}</div>
          <button
            type="button"
            className="hover:text-[#ff4d00]"
            onClick={() => {
              clearTokens();
              router.replace("/admin-login");
            }}
          >
            Sign out
          </button>
        </div>
      </aside>
      <div className="min-w-0 flex-1">
        <header className="flex items-center justify-between gap-2 overflow-x-auto border-b border-white/[0.06] px-4 py-3 lg:hidden">
          <span className="text-xs font-bold uppercase tracking-[0.16em] text-[#ff3b30]">Spark</span>
          <div className="flex gap-3 text-xs text-zinc-400">
            <Link href="/admin-dashboard/youtube">YT dash</Link>
            <Link href="/admin-dashboard/instagram">IG dash</Link>
            <Link href="/admin-scraping/youtube">YT scrape</Link>
            <Link href="/admin-scraping/instagram">IG scrape</Link>
            <Link href="/admin-leaderboard">Board</Link>
          </div>
        </header>
        <main className="px-4 py-6 md:px-7 md:py-7">{children}</main>
      </div>
    </div>
  );
}
