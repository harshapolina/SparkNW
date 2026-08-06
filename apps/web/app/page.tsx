"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { getStoredUser, getUserRole } from "@/lib/api";

export default function HomePage() {
  const router = useRouter();
  useEffect(() => {
    const token = localStorage.getItem("is_access_token");
    if (!token) {
      router.replace("/top-10");
      return;
    }
    const role = getUserRole(getStoredUser());
    if (role === "student") router.replace("/student-dashboard");
    else if (role === "admin") router.replace("/admin-dashboard");
    else router.replace("/overview");
  }, [router]);
  return (
    <div className="min-h-screen grid place-items-center bg-bg text-muted text-sm">
      Loading…
    </div>
  );
}
