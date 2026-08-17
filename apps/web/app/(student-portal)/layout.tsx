"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { clearTokens, getStoredUser, type User } from "@/lib/api";
import { BrandLogo } from "@/components/brand-logo";
import { useRequireRole } from "@/lib/spark/auth-guard";
import { prefetchStudentSpark } from "@/lib/spark/prefetch";
import { studentDashboardHref, withStudentId } from "@/lib/spark/student-routes";
import { cn } from "@/lib/utils";

const nav = [
  { href: "/student-dashboard", label: "Dashboard" },
  { href: "/student-leaderboard", label: "Leaderboard" },
  { href: "/top-10", label: "Top 10" },
];

export default function StudentPortalLayout({ children }: { children: React.ReactNode }) {
  const ready = useRequireRole("student", "/student-login");
  const pathname = usePathname();
  const router = useRouter();
  const qc = useQueryClient();
  const [user, setUser] = useState<User | null>(null);

  useEffect(() => {
    setUser(getStoredUser());
  }, [ready]);

  useEffect(() => {
    if (!ready || !user?.student_id) return;
    const params = new URLSearchParams(window.location.search);
    if (params.get("student_id") === user.student_id) return;
    params.set("student_id", user.student_id);
    const qs = params.toString();
    router.replace(qs ? `${pathname}?${qs}` : pathname);
  }, [ready, user, pathname, router]);

  useEffect(() => {
    const token = typeof window !== "undefined" ? localStorage.getItem("is_access_token") : null;
    if (!token) return;
    prefetchStudentSpark(qc);
  }, [qc]);

  if (!ready) {
    return (
      <div className="min-h-screen bg-black text-white">
        <header className="sticky top-0 z-20 border-b border-white/[0.06] bg-black/90">
          <div className="mx-auto flex h-14 max-w-6xl items-center px-4 md:px-6">
            <BrandLogo height={24} priority />
          </div>
        </header>
        <main className="mx-auto max-w-6xl px-4 py-6 md:px-6 md:py-8">
          <div className="space-y-6">
            <div className="h-12 w-2/3 animate-pulse rounded-xl bg-zinc-900" />
            <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-6">
              {Array.from({ length: 6 }).map((_, i) => (
                <div key={i} className="h-28 animate-pulse rounded-2xl bg-zinc-900" />
              ))}
            </div>
          </div>
        </main>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-black text-white">
      <header className="sticky top-0 z-20 border-b border-white/[0.06] bg-black/90 backdrop-blur">
        <div className="mx-auto max-w-6xl px-4 md:px-6">
          <div className="flex h-14 items-center justify-between gap-3">
            <Link href={studentDashboardHref(user?.student_id)} className="inline-flex min-w-0 shrink-0 items-center">
              <BrandLogo height={24} priority />
            </Link>
            <div className="flex min-w-0 items-center gap-3 text-xs text-zinc-400">
              <span className="hidden truncate sm:inline">{user?.name || "Student"}</span>
              <button
                type="button"
                className="shrink-0 hover:text-white"
                onClick={() => {
                  clearTokens();
                  router.replace("/student-login");
                }}
              >
                Sign out
              </button>
            </div>
          </div>
          <nav className="-mx-4 flex items-center gap-1 overflow-x-auto px-4 pb-3 [-ms-overflow-style:none] [scrollbar-width:none] [&::-webkit-scrollbar]:hidden md:mx-0 md:px-0">
            {nav.map((item) => (
              <Link
                key={item.href}
                href={item.href === "/top-10" ? item.href : withStudentId(item.href, user?.student_id)}
                className={cn(
                  "shrink-0 rounded-full px-3 py-1.5 text-xs font-medium transition",
                  pathname === item.href ? "bg-white text-black" : "text-zinc-400 hover:text-white"
                )}
              >
                {item.label}
              </Link>
            ))}
          </nav>
        </div>
      </header>
      <main className="mx-auto min-w-0 max-w-6xl px-4 py-6 md:px-6 md:py-8">{children}</main>
    </div>
  );
}
