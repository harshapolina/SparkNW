"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { FormEvent, useState } from "react";
import { motion } from "framer-motion";
import { Sparkles } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { api, saveUser, setTokens, type User } from "@/lib/api";

export default function SignupPage() {
  const router = useRouter();
  const [name, setName] = useState("");
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
        "/auth/signup",
        { method: "POST", body: JSON.stringify({ name, email, password }) }
      );
      setTokens(res.tokens);
      saveUser(res.user);
      router.push("/overview");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Signup failed");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div
      className="min-h-screen grid place-items-center px-4 py-10"
      style={{
        background:
          "radial-gradient(ellipse at top, rgba(79,70,229,0.08), transparent 50%), #F4F6F9",
      }}
    >
      <motion.form
        initial={{ opacity: 0, y: 12 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.45, ease: [0.22, 1, 0.36, 1] }}
        onSubmit={onSubmit}
        className="w-full max-w-[420px] rounded-3xl border border-border bg-white p-8 md:p-9 shadow-lift"
      >
        <div className="flex items-center gap-2">
          <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-accent text-white">
            <Sparkles size={14} />
          </div>
          <span className="font-[family-name:var(--font-display)] text-sm font-semibold">InstaScope</span>
        </div>
        <h1 className="mt-6 font-[family-name:var(--font-display)] text-2xl font-semibold tracking-[-0.03em]">
          Create your workspace
        </h1>
        <p className="mt-1.5 text-sm text-muted leading-relaxed">
          Start monitoring Instagram profiles in under a minute.
        </p>

        <div className="mt-7 space-y-3.5">
          <div>
            <label className="mb-1.5 block text-xs font-medium text-slate-500">Full name</label>
            <Input placeholder="Harsh" value={name} onChange={(e) => setName(e.target.value)} required />
          </div>
          <div>
            <label className="mb-1.5 block text-xs font-medium text-slate-500">Work email</label>
            <Input type="email" placeholder="you@company.com" value={email} onChange={(e) => setEmail(e.target.value)} required />
          </div>
          <div>
            <label className="mb-1.5 block text-xs font-medium text-slate-500">Password</label>
            <Input type="password" placeholder="Min. 8 characters" value={password} onChange={(e) => setPassword(e.target.value)} minLength={8} required />
          </div>
        </div>

        {error && <div className="mt-4 rounded-xl border border-red-200 bg-red-50 px-3.5 py-2.5 text-sm text-danger">{error}</div>}

        <Button type="submit" className="mt-6 w-full" size="lg" disabled={loading}>
          {loading ? "Creating…" : "Create account"}
        </Button>

        <p className="mt-5 text-center text-sm text-muted">
          Already have an account?{" "}
          <Link href="/login" className="font-medium text-accent hover:underline">Sign in</Link>
        </p>
      </motion.form>
    </div>
  );
}
