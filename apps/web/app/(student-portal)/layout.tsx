"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { clearTokens, getStoredUser, type User } from "@/lib/api";
import { useRequireRole } from "@/lib/spark/auth-guard";
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
  const [user, setUser] = useState<User | null>(null);

  useEffect(() => {
    setUser(getStoredUser());
  }, [ready]);

  if (!ready) {
    return (
      <div className="grid min-h-screen place-items-center bg-black text-sm text-zinc-500">
        Loading student portal…
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-black text-white">
      <header className="sticky top-0 z-20 border-b border-white/[0.06] bg-black/90 backdrop-blur">
        <div className="mx-auto flex h-14 max-w-6xl items-center justify-between gap-4 px-4 md:px-6">
          <div className="flex items-center gap-6">
            <Link href="/student-dashboard" className="text-xs font-bold uppercase tracking-[0.16em] text-[#ff3b30]">
              SPARK
            </Link>
            <nav className="flex items-center gap-1">
              {nav.map((item) => (
                <Link
                  key={item.href}
                  href={item.href}
                  className={cn(
                    "rounded-full px-3 py-1.5 text-xs font-medium transition",
                    pathname === item.href ? "bg-white text-black" : "text-zinc-400 hover:text-white"
                  )}
                >
                  {item.label}
                </Link>
              ))}
            </nav>
          </div>
          <div className="flex items-center gap-3 text-xs text-zinc-400">
            <span className="hidden sm:inline">{user?.name || "Student"}</span>
            <button
              type="button"
              className="hover:text-white"
              onClick={() => {
                clearTokens();
                router.replace("/student-login");
              }}
            >
              Sign out
            </button>
          </div>
        </div>
      </header>
      <main className="mx-auto max-w-6xl px-4 py-6 md:px-6 md:py-8">{children}</main>
    </div>
  );
}
