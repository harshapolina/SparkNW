"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { getStoredUser } from "@/lib/api";
import { DashboardShell } from "@/components/layout/shell";

export default function DashboardLayout({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  useEffect(() => {
    if (!getStoredUser() && !localStorage.getItem("is_access_token")) {
      router.replace("/login");
    }
  }, [router]);
  return <DashboardShell>{children}</DashboardShell>;
}
