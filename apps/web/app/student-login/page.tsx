"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { FormEvent, useState } from "react";
import { BrandLogo } from "@/components/brand-logo";
import { api, saveUser, setTokens, type User } from "@/lib/api";
import { studentDashboardHref } from "@/lib/spark/student-routes";
import { useQueryClient } from "@tanstack/react-query";
import type { StudentDashboardResponse } from "@/lib/spark/api-types";

export default function StudentLoginPage() {
  const router = useRouter();
  const qc = useQueryClient();
  const [studentId, setStudentId] = useState("");
  const [instagram, setInstagram] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setLoading(true);
    setError("");
    try {
      const res = await api<{ user: User; tokens: { access_token: string; refresh_token: string; token_type: string } }>(
        "/auth/student-login",
        {
          method: "POST",
          body: JSON.stringify({
            student_id: studentId.trim(),
            instagram_username: instagram.trim(),
          }),
        }
      );
      setTokens(res.tokens);
      saveUser(res.user);
      void qc.prefetchQuery({
        queryKey: ["spark", "student"],
        queryFn: () => api<StudentDashboardResponse>("/spark/student"),
      });
      router.push(studentDashboardHref(res.user.student_id || studentId.trim()));
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
            Student login
          </h1>
          <p className="mt-2 text-sm text-zinc-400">
            Enter your NIAT student ID and Instagram handle to open your portal.
          </p>
        </div>

        <form onSubmit={onSubmit} className="space-y-4 rounded-2xl border border-white/10 bg-[#121212] p-6">
          <label className="block space-y-1.5">
            <span className="text-[11px] uppercase tracking-[0.12em] text-zinc-500">Student ID</span>
            <input
              value={studentId}
              onChange={(e) => setStudentId(e.target.value)}
              required
              className="w-full rounded-xl border border-white/10 bg-black px-3 py-2.5 text-sm outline-none focus:border-[#ff3b30]"
              placeholder="e.g. NIAT24XXXX"
            />
          </label>
          <label className="block space-y-1.5">
            <span className="text-[11px] uppercase tracking-[0.12em] text-zinc-500">Instagram handle</span>
            <input
              value={instagram}
              onChange={(e) => setInstagram(e.target.value)}
              required
              className="w-full rounded-xl border border-white/10 bg-black px-3 py-2.5 text-sm outline-none focus:border-[#ff3b30]"
              placeholder="@yourhandle"
            />
          </label>
          {error && <p className="text-sm text-rose-400">{error}</p>}
          <button
            type="submit"
            disabled={loading}
            className="w-full rounded-xl bg-[#ff3b30] px-4 py-2.5 text-sm font-semibold text-white disabled:opacity-60"
          >
            {loading ? "Signing in…" : "Open my portal"}
          </button>
        </form>

        <div className="mt-6 text-xs text-zinc-500">
          <Link href="/top-10" className="hover:text-zinc-300">
            Public Top 10
          </Link>
        </div>
      </div>
    </div>
  );
}
