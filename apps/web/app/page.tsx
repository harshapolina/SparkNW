"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";

export default function HomePage() {
  const router = useRouter();
  useEffect(() => {
    const token = localStorage.getItem("is_access_token");
    router.replace(token ? "/overview" : "/login");
  }, [router]);
  return (
    <div className="min-h-screen grid place-items-center bg-bg text-muted text-sm">
      Loading InstaScope…
    </div>
  );
}
