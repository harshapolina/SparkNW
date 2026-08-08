"use client";

import { Check, ExternalLink, Pencil } from "lucide-react";
import { cn } from "@/lib/utils";

type Props = {
  /** Current draft URL or @handle (controlled). */
  value: string;
  onChange: (next: string) => void;
  /** Saved Instagram profile URL for the open link. */
  href: string;
  editing: boolean;
  onEditingChange: (editing: boolean) => void;
  dirty: boolean;
  disabled?: boolean;
  saving?: boolean;
  error?: string | null;
  tone?: "dark" | "light";
  onSave: () => void | Promise<void>;
  onCancel: () => void;
  className?: string;
};

/**
 * Editable Instagram handle/URL. Parent owns the draft so Refresh can
 * auto-save a dirty link before scraping — existing scrape flow unchanged.
 */
export function EditableInstagramLink({
  value,
  onChange,
  href,
  editing,
  onEditingChange,
  dirty,
  disabled,
  saving,
  error,
  tone = "dark",
  onSave,
  onCancel,
  className,
}: Props) {
  const dark = tone === "dark";

  if (!editing) {
    return (
      <div className={cn("mt-3 flex flex-wrap items-center gap-2", className)}>
        <a
          href={href}
          target="_blank"
          rel="noreferrer"
          className={cn(
            "inline-flex max-w-full items-center gap-1 truncate text-sm hover:underline",
            dark ? "text-[#ff4d00]" : "text-accent"
          )}
        >
          <span className="truncate">{href}</span>
          <ExternalLink size={12} className="shrink-0 opacity-70" />
        </a>
        <button
          type="button"
          disabled={disabled || saving}
          onClick={() => onEditingChange(true)}
          className={cn(
            "inline-flex items-center gap-1 rounded-lg px-2 py-1 text-[11px] font-medium transition",
            dark
              ? "border border-white/10 bg-black/40 text-zinc-300 hover:border-[#ff4d00]/40 hover:text-white"
              : "border border-black/10 bg-white text-foreground/70 hover:border-accent/40 hover:text-foreground"
          )}
          title="Edit Instagram link"
        >
          <Pencil size={11} />
          Edit link
        </button>
      </div>
    );
  }

  return (
    <div className={cn("mt-3 space-y-1.5", className)}>
      <div className="flex flex-wrap items-center gap-2">
        <input
          value={value}
          onChange={(e) => onChange(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") {
              e.preventDefault();
              void onSave();
            }
            if (e.key === "Escape") onCancel();
          }}
          disabled={disabled || saving}
          placeholder="@username or https://instagram.com/…"
          autoFocus
          className={cn(
            "min-w-[220px] flex-1 rounded-xl border px-3 py-2 text-sm outline-none",
            dark
              ? "border-white/15 bg-black/50 text-zinc-100 placeholder:text-zinc-600 focus:border-[#ff4d00]/50"
              : "border-black/10 bg-white text-foreground placeholder:text-foreground/40 focus:border-accent/50"
          )}
        />
        <button
          type="button"
          disabled={disabled || saving || !value.trim()}
          onClick={() => void onSave()}
          className={cn(
            "inline-flex items-center gap-1.5 rounded-xl px-3 py-2 text-xs font-semibold disabled:opacity-50",
            dark ? "bg-[#ff3b30] text-white" : "bg-accent text-white"
          )}
        >
          <Check size={13} />
          {saving ? "Saving…" : dirty ? "Save link" : "Done"}
        </button>
        <button
          type="button"
          disabled={saving}
          onClick={onCancel}
          className={cn(
            "rounded-xl border px-3 py-2 text-xs",
            dark ? "border-white/10 text-zinc-400" : "border-black/10 text-foreground/60"
          )}
        >
          Cancel
        </button>
      </div>
      <p className={cn("text-[11px]", dark ? "text-zinc-500" : "text-foreground/50")}>
        Paste @handle or Instagram profile URL. Save or click Refresh / Scrape — it will use this account.
      </p>
      {error ? (
        <p className={cn("text-[11px]", dark ? "text-rose-400" : "text-danger")}>{error}</p>
      ) : null}
    </div>
  );
}

export function normalizeIgDraft(raw: string): string {
  return raw.trim().replace(/\/+$/, "").toLowerCase();
}

export function profileIgHref(username: string, profileUrl?: string | null): string {
  const u = profileUrl?.trim();
  if (u) return u.endsWith("/") ? u : `${u}/`;
  return `https://www.instagram.com/${username}/`;
}
