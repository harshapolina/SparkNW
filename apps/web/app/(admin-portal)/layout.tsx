"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState } from "react";
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
  RefreshCw,
  Settings,
  BarChart3,
  Trophy,
  Upload,
  Video,
} from "lucide-react";
import { clearTokens, getStoredUser, type User } from "@/lib/api";
import { BrandLogo } from "@/components/brand-logo";
import { useRequireRole } from "@/lib/spark/auth-guard";
import { adminScrapingListHref } from "@/lib/admin-scraping-list-state";
import { cn } from "@/lib/utils";

const scrapingChildren = [
  { href: "/admin-scraping/youtube", label: "YouTube", icon: Video },
  { href: "/admin-scraping/instagram", label: "Instagram", icon: Camera },
  { href: "/admin-scraping", label: "Overall", icon: Layers, exact: true },
] as const;

const nav = [
  { href: "/admin-dashboard", label: "Dashboard", icon: LayoutDashboard },
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

function scrapingSectionActive(pathname: string, href: string, exact?: boolean) {
  if (href === "/admin-scraping/youtube") return pathname.startsWith("/admin-scraping/youtube");
  if (href === "/admin-scraping/instagram") return pathname.startsWith("/admin-scraping/instagram");
  if (exact) {
    return (
      pathname === "/admin-scraping" ||
      (pathname.startsWith("/admin-scraping/") &&
        !pathname.startsWith("/admin-scraping/youtube") &&
        !pathname.startsWith("/admin-scraping/instagram"))
    );
  }
  return pathname.startsWith("/admin-scraping");
}

export default function AdminPortalLayout({ children }: { children: React.ReactNode }) {
  const ready = useRequireRole("admin", "/admin-login");
  const pathname = usePathname();
  const router = useRouter();
  const [user, setUser] = useState<User | null>(null);
  const scrapingOpen = pathname.startsWith("/admin-scraping");
  const [scrapingExpanded, setScrapingExpanded] = useState(scrapingOpen);

  useEffect(() => {
    setUser(getStoredUser());
  }, [ready]);

  useEffect(() => {
    if (scrapingOpen) setScrapingExpanded(true);
  }, [scrapingOpen]);

  if (!ready) {
    return (
      <div className="grid min-h-screen place-items-center bg-black text-sm text-zinc-500">
        Loading admin portal…
      </div>
    );
  }

  return (
    <div className="flex min-h-screen bg-black text-white">
      <aside className="sticky top-0 hidden h-screen w-[232px] shrink-0 flex-col border-r border-white/[0.06] bg-[#0a0a0a] lg:flex">
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
            const hasChildren = "children" in item && item.children;
            const branchOpen = hasChildren && scrapingExpanded;
            const parentActive = hasChildren
              ? scrapingOpen
              : pathname === item.href || pathname.startsWith(item.href + "/");

            if (hasChildren) {
              return (
                <div key={item.href} className="pt-0.5">
                  <div
                    className={cn(
                      "flex items-center rounded-xl transition",
                      parentActive && !scrapingExpanded
                        ? "bg-[#ff3b30] text-white shadow-lg shadow-[#ff3b30]/20"
                        : parentActive
                          ? "bg-white/[0.04] text-zinc-100"
                          : "text-zinc-400 hover:bg-white/[0.04] hover:text-zinc-100"
                    )}
                  >
                    <Link
                      href={adminScrapingListHref()}
                      className="flex min-w-0 flex-1 items-center gap-2.5 px-3 py-2.5 text-[13px]"
                      onClick={() => setScrapingExpanded(true)}
                    >
                      <Icon size={16} />
                      {item.label}
                    </Link>
                    <button
                      type="button"
                      aria-label={scrapingExpanded ? "Collapse Scraping" : "Expand Scraping"}
                      aria-expanded={scrapingExpanded}
                      onClick={() => setScrapingExpanded((open) => !open)}
                      className="mr-1 rounded-lg p-1.5 hover:bg-white/10"
                    >
                      <ChevronDown
                        size={14}
                        className={cn("transition-transform", scrapingExpanded && "rotate-180")}
                      />
                    </button>
                  </div>
                  <div
                    className={cn(
                      "grid transition-[grid-template-rows] duration-200 ease-out",
                      branchOpen ? "grid-rows-[1fr]" : "grid-rows-[0fr]"
                    )}
                  >
                    <div className="overflow-hidden">
                      <div className="relative ml-[22px] mt-1 space-y-0.5 border-l border-white/10 pb-1 pl-3">
                        {item.children.map((child) => {
                          const ChildIcon = child.icon;
                          const childActive = scrapingSectionActive(
                            pathname,
                            child.href,
                            "exact" in child ? child.exact : false
                          );
                          return (
                            <Link
                              key={child.href + child.label}
                              href={
                                child.href === "/admin-scraping"
                                  ? adminScrapingListHref()
                                  : child.href
                              }
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
        <div className="space-y-2 border-t border-white/[0.06] p-4 text-[11px] text-zinc-500">
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
            <Link href="/admin-scraping/youtube">YouTube</Link>
            <Link href="/admin-scraping/instagram">Instagram</Link>
            <Link href={adminScrapingListHref()}>Overall</Link>
            <Link href="/admin-leaderboard">Board</Link>
          </div>
        </header>
        <main className="px-4 py-6 md:px-7 md:py-7">{children}</main>
      </div>
    </div>
  );
}
