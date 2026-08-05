"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import {
  Bell,
  LogOut,
  Search,
  Settings,
  Sparkles,
} from "lucide-react";
import { api, clearTokens, getStoredUser, type Profile, type User } from "@/lib/api";
import { prefetchSparkData, sparkQueryKeyForApi } from "@/lib/spark/prefetch";
import { cn } from "@/lib/utils";

const SPARK_ROUTES = [
  "/spark/dashboard",
  "/spark/leaderboard",
  "/spark/admin",
  "/spark/admin/leaderboard",
] as const;

const nav = [
  { href: "/overview", label: "Overview", prefetch: "/analytics/overview" },
  { href: "/profiles", label: "Profiles", prefetch: "/profiles?page=1&page_size=20" },
  { href: "/imports", label: "Import" },
  { href: "/imports/duplicates", label: "Duplicates" },
  { href: "/analytics", label: "Analytics", prefetch: "/analytics/overview" },
  { href: "/spark/dashboard", label: "Student", prefetchApi: "/spark/student" },
  { href: "/spark/leaderboard", label: "Leaderboard", prefetchApi: "/spark/leaderboard?sort=overall" },
  { href: "/spark/admin", label: "Admin", prefetchApi: "/spark/admin" },
  { href: "/spark/admin/leaderboard", label: "Admin Board", prefetchApi: "/spark/leaderboard?sort=overall" },
  { href: "/notifications", label: "Alerts", prefetch: "/notifications" },
  { href: "/settings", label: "Settings", prefetch: "/settings" },
];

export function DashboardShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const qc = useQueryClient();
  const [user, setUser] = useState<User | null>(null);
  const [ready, setReady] = useState(false);

  useEffect(() => {
    setUser(getStoredUser());
    setReady(true);
  }, []);

  // Warm SPARK route chunks + API cache so nav doesn't stall on "Compiling…"
  useEffect(() => {
    if (!ready) return;
    const warm = () => {
      for (const href of SPARK_ROUTES) router.prefetch(href);
      prefetchSparkData(qc);
    };
    const ric = (window as Window & { requestIdleCallback?: (cb: () => void, opts?: { timeout: number }) => number })
      .requestIdleCallback;
    if (ric) {
      const id = ric(warm, { timeout: 1200 });
      return () => (window as Window & { cancelIdleCallback?: (id: number) => void }).cancelIdleCallback?.(id);
    }
    const t = window.setTimeout(warm, 250);
    return () => window.clearTimeout(t);
  }, [ready, router, qc]);

  const prefetchRoute = (href: string, apiPath?: string, prefetchApi?: string) => {
    router.prefetch(href);
    const path = prefetchApi || apiPath;
    if (!path) return;
    if (path.startsWith("/spark/")) {
      const key = sparkQueryKeyForApi(path);
      if (key) {
        void qc.prefetchQuery({
          queryKey: key,
          queryFn: () => api(path),
        });
      }
      return;
    }
    if (path.startsWith("/profiles")) {
      void qc.prefetchQuery({
        queryKey: ["profiles", "", 1],
        queryFn: () => api<{ items: Profile[]; total: number }>("/profiles?q=&page=1&page_size=20"),
      });
    } else if (path.includes("overview") || path.includes("analytics")) {
      void qc.prefetchQuery({
        queryKey: ["overview"],
        queryFn: () => api(path.includes("overview") ? "/analytics/overview" : path),
      });
    } else if (path.startsWith("/notifications")) {
      void qc.prefetchQuery({
        queryKey: ["notifications"],
        queryFn: () => api(path),
      });
    } else if (path.startsWith("/settings")) {
      void qc.prefetchQuery({
        queryKey: ["settings"],
        queryFn: () => api(path),
      });
    }
  };

  return (
    <div className="min-h-screen bg-cream text-stone-900">
      <header className="sticky top-0 z-30 border-b border-stone-200/70 bg-[#f3efe8]/85 backdrop-blur-xl">
        <div className="mx-auto flex h-[68px] max-w-[1600px] items-center gap-3 px-4 md:px-7">
          <Link href="/overview" className="flex shrink-0 items-center gap-2.5" onMouseEnter={() => prefetchRoute("/overview", "/analytics/overview")}>
            <div className="flex h-9 w-9 items-center justify-center rounded-2xl bg-stone-900 text-white shadow-card">
              <Sparkles size={15} />
            </div>
            <span className="font-[family-name:var(--font-display)] text-[17px] font-semibold tracking-tight">
              InstaScope
            </span>
          </Link>

          <nav className="ml-1 hidden items-center gap-0.5 xl:flex">
            {nav.map((item) => {
              const active =
                item.href === "/spark/admin"
                  ? pathname === "/spark/admin"
                  : pathname === item.href || pathname.startsWith(item.href + "/");
              return (
                <Link
                  key={item.href}
                  href={item.href}
                  onMouseEnter={() => prefetchRoute(item.href, item.prefetch, item.prefetchApi)}
                  className={cn(
                    "pill-nav whitespace-nowrap px-2.5 text-[13px]",
                    active
                      ? "bg-white text-stone-900 shadow-soft"
                      : "text-stone-500 hover:bg-white/60 hover:text-stone-800"
                  )}
                >
                  {item.label}
                </Link>
              );
            })}
          </nav>

          <div className="ml-auto flex items-center gap-2 md:gap-3">
            <span title="Live monitoring" className="relative mr-1 hidden h-2 w-2 sm:flex">
              <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-emerald-400 opacity-50" />
              <span className="relative inline-flex h-2 w-2 rounded-full bg-emerald-500" />
            </span>
            <Link
              href="/profiles"
              onMouseEnter={() => prefetchRoute("/profiles", "/profiles?page=1&page_size=20")}
              className="hidden h-10 w-10 items-center justify-center rounded-full bg-white/70 text-stone-500 shadow-soft transition hover:bg-white hover:text-stone-800 md:flex"
            >
              <Search size={16} />
            </Link>
            <Link
              href="/notifications"
              onMouseEnter={() => prefetchRoute("/notifications", "/notifications")}
              className="flex h-10 w-10 items-center justify-center rounded-full bg-white/70 text-stone-500 shadow-soft transition hover:bg-white hover:text-stone-800"
            >
              <Bell size={16} />
            </Link>
            <Link
              href="/settings"
              onMouseEnter={() => prefetchRoute("/settings", "/settings")}
              className="hidden h-10 w-10 items-center justify-center rounded-full bg-white/70 text-stone-500 shadow-soft transition hover:bg-white hover:text-stone-800 md:flex"
            >
              <Settings size={16} />
            </Link>
            <button
              onClick={() => {
                clearTokens();
                router.push("/login");
              }}
              className="flex items-center gap-2 rounded-full bg-white py-1.5 pl-1.5 pr-3 shadow-soft"
              title="Sign out"
            >
              <div className="flex h-8 w-8 items-center justify-center rounded-full bg-gradient-to-br from-[#c4b5fd] to-[#fda4af] text-xs font-semibold text-stone-800">
                {ready ? (user?.name?.[0] || "U").toUpperCase() : "·"}
              </div>
              <span className="hidden max-w-[100px] truncate text-sm font-medium sm:block" suppressHydrationWarning>
                {ready ? user?.name || "User" : ""}
              </span>
              <LogOut size={13} className="hidden text-stone-400 sm:block" />
            </button>
          </div>
        </div>

        <div className="flex gap-1 overflow-x-auto border-t border-stone-200/60 px-3 py-2 xl:hidden">
          {nav.map((item) => {
            const active =
              item.href === "/spark/admin"
                ? pathname === "/spark/admin"
                : pathname === item.href || pathname.startsWith(item.href + "/");
            return (
              <Link
                key={item.href}
                href={item.href}
                onMouseEnter={() => prefetchRoute(item.href, item.prefetch, item.prefetchApi)}
                className={cn(
                  "shrink-0 rounded-full px-3.5 py-1.5 text-xs font-medium",
                  active ? "bg-white text-stone-900 shadow-soft" : "text-stone-500"
                )}
              >
                {item.label}
              </Link>
            );
          })}
        </div>
      </header>

      <main className="mx-auto max-w-[1600px] px-4 py-6 md:px-7 md:py-7">{children}</main>
    </div>
  );
}
