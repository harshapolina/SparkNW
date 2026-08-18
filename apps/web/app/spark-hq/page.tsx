"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { FormEvent, useState } from "react";
import { BrandLogo } from "@/components/brand-logo";
import { api, saveUser, setTokens, type User } from "@/lib/api";

export default function AdminLoginPage() {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setLoading(true);
    setError("");
    try {
      const res = await api<{ user: User; tokens: { access_token: string; refresh_token: string; token_type: string } }>(
        "/auth/login",
        { method: "POST", body: JSON.stringify({ email, password }) }
      );
      if (res.user.role === "student") {
        setError("Students must use student login");
        return;
      }
      setTokens(res.tokens);
      saveUser({ ...res.user, role: res.user.role || "admin" });
      router.push("/admin-dashboard");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Login failed");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="min-h-screen bg-black text-white">
      <div className="mx-auto flex min-h-screen max-w-md flex-col justify-center px-4 py-12">
        <div className="mb-8">
          <Link href="/top-10" className="inline-flex items-center">
            <BrandLogo height={32} priority />
          </Link>
          <h1 className="mt-4 font-[family-name:var(--font-display)] text-3xl font-semibold tracking-tight">
            Admin login
          </h1>
          <p className="mt-2 text-sm text-zinc-400">Sign in with your admin email and password.</p>
        </div>

        <form onSubmit={onSubmit} className="space-y-4 rounded-2xl border border-white/10 bg-[#121212] p-6">
          <label className="block space-y-1.5">
            <span className="text-[11px] uppercase tracking-[0.12em] text-zinc-500">Email</span>
            <input
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              required
              className="w-full rounded-xl border border-white/10 bg-black px-3 py-2.5 text-sm outline-none focus:border-[#ff3b30]"
            />
          </label>
          <label className="block space-y-1.5">
            <span className="text-[11px] uppercase tracking-[0.12em] text-zinc-500">Password</span>
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
              className="w-full rounded-xl border border-white/10 bg-black px-3 py-2.5 text-sm outline-none focus:border-[#ff3b30]"
            />
          </label>
          {error && <p className="text-sm text-rose-400">{error}</p>}
          <button
            type="submit"
            disabled={loading}
            className="w-full rounded-xl bg-[#ff3b30] px-4 py-2.5 text-sm font-semibold text-white disabled:opacity-60"
          >
            {loading ? "Signing in…" : "Open admin portal"}
          </button>
        </form>
      </div>
    </div>
  );
}
