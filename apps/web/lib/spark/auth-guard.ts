"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { clearTokens, getStoredUser, getUserRole, type UserRole } from "@/lib/api";

export function useRequireRole(role: UserRole, loginPath: string) {
  const router = useRouter();
  const [ready, setReady] = useState(false);

  useEffect(() => {
    const user = getStoredUser();
    const token = typeof window !== "undefined" ? localStorage.getItem("is_access_token") : null;
    if (!user || !token) {
      router.replace(loginPath);
      return;
    }
    const actual = getUserRole(user);
    if (actual !== role) {
      clearTokens();
      router.replace(loginPath);
      return;
    }
    setReady(true);
  }, [router, role, loginPath]);

  return ready;
}
