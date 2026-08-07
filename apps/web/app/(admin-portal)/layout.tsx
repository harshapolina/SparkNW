"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import {
  Bell,
  BookOpen,
  Database,
  Download,
  FileSpreadsheet,
  LayoutDashboard,
  Medal,
  RefreshCw,
  Settings,
  BarChart3,
  Trophy,
  Upload,
} from "lucide-react";
import { clearTokens, getStoredUser, type User } from "@/lib/api";
import { BrandLogo } from "@/components/brand-logo";
import { useRequireRole } from "@/lib/spark/auth-guard";
import { cn } from "@/lib/utils";

const nav = [
  { href: "/admin-dashboard", label: "Dashboard", icon: LayoutDashboard },
  { href: "/admin-leaderboard", label: "Leaderboard", icon: Trophy },
  { href: "/admin-scraping", label: "Scraping", icon: RefreshCw },
  { href: "/admin-analytics", label: "Analytics", icon: BarChart3 },
  { href: "/admin-alerts", label: "Alerts", icon: Bell },
  { href: "/admin-import", label: "Import roster", icon: Upload },
  { href: "/admin-unimported", label: "Unimported", icon: FileSpreadsheet },
  { href: "/admin-settings", label: "Settings", icon: Settings },
  { href: "/top-10", label: "Public Top 10", icon: Medal },
  { href: "/admin-how-it-works", label: "How it works", icon: BookOpen },
];

export default function AdminPortalLayout({ children }: { children: React.ReactNode }) {
  const ready = useRequireRole("admin", "/admin-login");
  const pathname = usePathname();
  const router = useRouter();
  const [user, setUser] = useState<User | null>(null);

  useEffect(() => {
    setUser(getStoredUser());
  }, [ready]);

  if (!ready) {
    return (
      <div className="grid min-h-screen place-items-center bg-black text-sm text-zinc-500">
        Loading admin portal…
      </div>
    );
  }

  return (
    <div className="flex min-h-screen bg-black text-white">
      <aside className="sticky top-0 hidden h-screen w-[220px] shrink-0 flex-col border-r border-white/[0.06] bg-[#0a0a0a] lg:flex">
        <div className="px-4 py-5">
          <Link href="/admin-dashboard" className="inline-flex items-center">
            <BrandLogo height={26} priority />
          </Link>
          <div className="mt-2 text-[10px] font-semibold uppercase tracking-[0.16em] text-[#ff3b30]">
            Admin
          </div>
        </div>
        <nav className="flex-1 space-y-0.5 overflow-y-auto px-3 py-2">
          {nav.map((item) => {
            const Icon = item.icon;
            const active =
              item.href === "/admin-scraping"
                ? pathname.startsWith("/admin-scraping")
                : pathname === item.href || pathname.startsWith(item.href + "/");
            return (
              <Link
                key={item.href}
                href={item.href === "/admin-scraping" ? adminScrapingListHref() : item.href}
                className={cn(
                  "flex items-center gap-2.5 rounded-xl px-3 py-2.5 text-[13px] transition",
                  active
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
            <Link href="/admin-scraping">Scraping</Link>
            <Link href="/admin-import">Import</Link>
            <Link href="/admin-leaderboard">Board</Link>
          </div>
        </header>
        <main className="px-4 py-6 md:px-7 md:py-7">{children}</main>
      </div>
    </div>
  );
}
