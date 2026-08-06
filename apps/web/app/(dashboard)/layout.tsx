"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { getStoredUser, getUserRole } from "@/lib/api";
import { DashboardShell } from "@/components/layout/shell";

export default function DashboardLayout({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  useEffect(() => {
    const user = getStoredUser();
    const token = localStorage.getItem("is_access_token");
    if (!user && !token) {
      router.replace("/admin-login");
      return;
    }
    const role = getUserRole(user);
    if (role === "student") {
      router.replace("/student-dashboard");
    }
  }, [router]);
  return <DashboardShell>{children}</DashboardShell>;
}
