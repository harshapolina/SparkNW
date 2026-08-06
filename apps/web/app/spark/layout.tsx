"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { getStoredUser, getUserRole } from "@/lib/api";
import { DashboardShell } from "@/components/layout/shell";

/** Legacy /spark/* redirects — keep InstaScope shell for stub pages; gate students out of admin. */
export default function SparkRootLayout({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  useEffect(() => {
    const user = getStoredUser();
    const token = localStorage.getItem("is_access_token");
    if (!user && !token) {
      router.replace("/student-login");
      return;
    }
    if (getUserRole(user) === "student") {
      // Allow only redirects / stubs that send them to student routes
      return;
    }
  }, [router]);
  return <DashboardShell>{children}</DashboardShell>;
}
