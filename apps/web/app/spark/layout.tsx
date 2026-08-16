"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { getStoredUser, getUserRole } from "@/lib/api";
import { DashboardShell } from "@/components/layout/shell";
import { studentDashboardHref } from "@/lib/spark/student-routes";

/** Legacy /spark/* — students never stay here; they go to the student portal. */
export default function SparkRootLayout({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const [allowShell, setAllowShell] = useState(false);

  useEffect(() => {
    const user = getStoredUser();
    const token = localStorage.getItem("is_access_token");
    if (!user && !token) {
      router.replace("/student-login");
      return;
    }
    if (getUserRole(user) === "student") {
      router.replace(studentDashboardHref(user?.student_id));
      return;
    }
    setAllowShell(true);
  }, [router]);

  if (!allowShell) {
    return (
      <div className="grid min-h-screen place-items-center bg-black text-sm text-zinc-500">
        Opening your portal…
      </div>
    );
  }

  return <DashboardShell>{children}</DashboardShell>;
}
