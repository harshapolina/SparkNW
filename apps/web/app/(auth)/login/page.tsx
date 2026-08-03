"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { FormEvent, useState } from "react";
import { motion } from "framer-motion";
import { Sparkles } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { api, saveUser, setTokens, type User } from "@/lib/api";

export default function LoginPage() {
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
      setTokens(res.tokens);
      saveUser(res.user);
      router.push("/overview");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Login failed");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="min-h-screen grid lg:grid-cols-[1.05fr_0.95fr]">
      <div
        className="relative hidden lg:flex flex-col justify-between overflow-hidden p-12 text-white"
        style={{
          background:
            "radial-gradient(ellipse at 20% 20%, rgba(79,70,229,0.35), transparent 50%), radial-gradient(ellipse at 80% 80%, rgba(14,165,233,0.18), transparent 45%), #09090b",
        }}
      >
        <div
          className="pointer-events-none absolute inset-0 opacity-[0.35]"
          style={{
            backgroundImage:
              "linear-gradient(rgba(255,255,255,0.04) 1px, transparent 1px), linear-gradient(90deg, rgba(255,255,255,0.04) 1px, transparent 1px)",
            backgroundSize: "48px 48px",
          }}
        />
        <div className="relative z-10 flex items-center gap-2.5">
          <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-accent shadow-[0_0_32px_rgba(79,70,229,0.45)]">
            <Sparkles size={16} />
          </div>
          <span className="font-[family-name:var(--font-display)] text-lg font-semibold tracking-tight">InstaScope</span>
        </div>

        <div className="relative z-10 max-w-lg">
          <motion.div initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.6, ease: [0.22, 1, 0.36, 1] }}>
            <div className="text-[11px] uppercase tracking-[0.2em] text-indigo-200/70">Continuous intelligence</div>
            <h2 className="mt-4 font-[family-name:var(--font-display)] text-4xl font-semibold leading-[1.15] tracking-[-0.03em]">
              Monitor every signal that matters.
            </h2>
            <p className="mt-4 text-[15px] leading-relaxed text-zinc-400">
              Track public Instagram profiles daily — followers, engagement, posts, and growth — without lifting a finger.
            </p>
          </motion.div>

          <div className="mt-10 grid gap-3">
            {[
              ["Daily cadence", "Automatic refresh across your portfolio"],
              ["Growth alerts", "Know when followers spike or drop"],
              ["Post analytics", "Likes, views, and content mix over time"],
            ].map(([t, d], i) => (
              <motion.div
                key={t}
                initial={{ opacity: 0, y: 10 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: 0.15 + i * 0.08, duration: 0.45 }}
                className="rounded-2xl border border-white/[0.07] bg-white/[0.03] px-4 py-3.5 backdrop-blur"
              >
                <div className="text-sm font-medium text-white">{t}</div>
                <div className="mt-0.5 text-[13px] text-zinc-500">{d}</div>
              </motion.div>
            ))}
          </div>
        </div>

        <div className="relative z-10 text-xs text-zinc-600">Built for operators who measure what compounds.</div>
      </div>

      <div className="flex items-center justify-center p-6 md:p-10">
        <motion.form
          initial={{ opacity: 0, y: 12 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.45, ease: [0.22, 1, 0.36, 1] }}
          onSubmit={onSubmit}
          className="w-full max-w-[400px]"
        >
          <div className="lg:hidden mb-8 flex items-center gap-2">
            <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-accent text-white">
              <Sparkles size={14} />
            </div>
            <span className="font-[family-name:var(--font-display)] font-semibold">InstaScope</span>
          </div>

          <div className="eyebrow">Welcome back</div>
          <h1 className="mt-2 font-[family-name:var(--font-display)] text-3xl font-semibold tracking-[-0.03em]">Sign in</h1>
          <p className="mt-2 text-sm text-muted leading-relaxed">Access your monitoring workspace.</p>

          <div className="mt-8 space-y-3.5">
            <div>
              <label className="mb-1.5 block text-xs font-medium text-slate-500">Email</label>
              <Input type="email" placeholder="you@company.com" value={email} onChange={(e) => setEmail(e.target.value)} required />
            </div>
            <div>
              <label className="mb-1.5 block text-xs font-medium text-slate-500">Password</label>
              <Input type="password" placeholder="••••••••" value={password} onChange={(e) => setPassword(e.target.value)} required />
            </div>
          </div>

          {error && (
            <div className="mt-4 rounded-xl border border-red-200 bg-red-50 px-3.5 py-2.5 text-sm text-danger">{error}</div>
          )}

          <Button type="submit" className="mt-6 w-full" size="lg" disabled={loading}>
            {loading ? "Signing in…" : "Continue"}
          </Button>

          <div className="mt-6 flex items-center justify-between text-sm text-muted">
            <Link href="/forgot-password" className="transition hover:text-fg">Forgot password</Link>
            <Link href="/signup" className="font-medium text-accent hover:underline">Create account</Link>
          </div>
        </motion.form>
      </div>
    </div>
  );
}
