"use client";

import Link from "next/link";
import { FormEvent, useState } from "react";
import { motion } from "framer-motion";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { api } from "@/lib/api";

export default function ForgotPasswordPage() {
  const [email, setEmail] = useState("");
  const [done, setDone] = useState(false);
  const [loading, setLoading] = useState(false);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setLoading(true);
    try {
      await api("/auth/forgot-password", { method: "POST", body: JSON.stringify({ email }) });
      setDone(true);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="min-h-screen grid place-items-center px-4 bg-bg">
      <motion.form
        initial={{ opacity: 0, y: 10 }}
        animate={{ opacity: 1, y: 0 }}
        onSubmit={onSubmit}
        className="w-full max-w-[400px] rounded-3xl border border-border bg-white p-8 shadow-lift space-y-5"
      >
        <div>
          <div className="eyebrow">Account recovery</div>
          <h1 className="mt-2 font-[family-name:var(--font-display)] text-2xl font-semibold tracking-tight">Reset password</h1>
          <p className="mt-1.5 text-sm text-muted leading-relaxed">
            We&apos;ll email reset instructions if the account exists.
          </p>
        </div>
        {done ? (
          <div className="rounded-xl border border-emerald-200 bg-emerald-50 px-3.5 py-3 text-sm text-success">
            If that email exists, a reset link has been sent.
          </div>
        ) : (
          <>
            <div>
              <label className="mb-1.5 block text-xs font-medium text-slate-500">Email</label>
              <Input type="email" placeholder="you@company.com" value={email} onChange={(e) => setEmail(e.target.value)} required />
            </div>
            <Button type="submit" className="w-full" size="lg" disabled={loading}>
              {loading ? "Sending…" : "Send reset link"}
            </Button>
          </>
        )}
        <Link href="/login" className="block text-center text-sm text-muted hover:text-fg">Back to login</Link>
      </motion.form>
    </div>
  );
}
