"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  BarChart3,
  Database,
  FileText,
  Flag,
  Gift,
  LayoutDashboard,
  Medal,
  Settings,
  Trophy,
  Users,
} from "lucide-react";
import { cn } from "@/lib/utils";

const nav = [
  { href: "/spark/admin", label: "Dashboard", icon: LayoutDashboard },
  { href: "/spark/admin/students", label: "Students", icon: Users },
  { href: "/spark/admin/leaderboard", label: "Leaderboard", icon: Trophy },
  { href: "/spark/admin/scraped", label: "Scraped Data", icon: Database },
  { href: "/spark/admin/submissions", label: "Submissions", icon: FileText },
  { href: "/spark/admin/analytics", label: "Analytics", icon: BarChart3 },
  { href: "/spark/admin/milestones", label: "Milestones", icon: Medal },
  { href: "/spark/admin/rewards", label: "Rewards", icon: Gift },
  { href: "/spark/admin/reports", label: "Reports", icon: Flag },
  { href: "/spark/admin/settings", label: "Settings", icon: Settings },
];

export default function SparkAdminLayout({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();

  return (
    <div className="spark-root -mx-4 -my-6 flex min-h-[calc(100vh-68px)] bg-black text-white md:-mx-7 md:-my-7">
      <aside className="sticky top-[68px] hidden h-[calc(100vh-68px)] w-[220px] shrink-0 flex-col border-r border-white/[0.06] bg-[#0a0a0a] lg:flex">
        <nav className="flex-1 space-y-0.5 overflow-y-auto px-3 py-4">
          {nav.map((item) => {
            const Icon = item.icon;
            const active =
              item.href === "/spark/admin"
                ? pathname === "/spark/admin"
                : pathname.startsWith(item.href);
            return (
              <Link
                key={item.href}
                href={item.href}
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
        <div className="border-t border-white/[0.06] p-4 text-[11px] text-zinc-500">
          <Link href="/spark/dashboard" className="hover:text-[#ff4d00]">
            ← Student view
          </Link>
          <div className="mt-2">
            <Link href="/profiles" className="hover:text-zinc-300">
              InstaScope profiles →
            </Link>
          </div>
        </div>
      </aside>
      <div className="min-w-0 flex-1 px-4 py-6 md:px-7 md:py-7">{children}</div>
    </div>
  );
}
