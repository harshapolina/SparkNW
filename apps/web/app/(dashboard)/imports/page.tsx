"use client";

import Link from "next/link";
import { useMemo, useRef, useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import {
  CheckSquare,
  Download,
  FileSpreadsheet,
  Link2,
  Loader2,
  Sheet,
  Square,
  Trash2,
  Upload,
} from "lucide-react";
import Papa from "papaparse";
import * as XLSX from "xlsx";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { api } from "@/lib/api";
import { saveDuplicatesFromImport } from "@/lib/import-duplicates";
import { saveUnimportedFromImport, saveUnimportedFromParse } from "@/lib/import-unimported";
import { cn } from "@/lib/utils";
import { downloadImportableCsv, extractUsername, parseSheetMatrixDetailed, type SheetStudent } from "@/lib/student-sheet";

type Row = {
  id: string;
  raw: string;
  username: string;
  student: SheetStudent;
  selected: boolean;
};

type BulkImportResponse = {
  imported: number;
  skipped: number;
  failed: number;
  updated?: number;
  duplicates?: number;
  scraping: boolean;
  items: { url: string; username?: string; status: string; message?: string; profile_id?: string }[];
};

type SourceTab = "upload" | "sheet" | "paste";

function parseMatrix(matrix: string[][], sheetLabel?: string): Row[] {
  const { rows, rejected } = parseSheetMatrixDetailed(matrix);
  if (rejected.length) saveUnimportedFromParse(rejected, sheetLabel);
  return rows.map((r, i) => ({
    id: `${r.username}-${i}`,
    raw: r.url,
    username: r.username,
    student: r.student,
    selected: true,
  }));
}

function googleSheetToCsvUrl(input: string): string | null {
  const raw = input.trim();
  if (!raw) return null;
  if (raw.includes("output=csv") || raw.includes("export?format=csv")) return raw;
  const m = raw.match(/docs\.google\.com\/spreadsheets\/d\/([a-zA-Z0-9-_]+)/);
  if (!m) return null;
  const id = m[1];
  const gidMatch = raw.match(/[?#&]gid=([0-9]+)/);
  const gid = gidMatch?.[1] || "0";
  return `https://docs.google.com/spreadsheets/d/${id}/export?format=csv&gid=${gid}`;
}

export default function ImportsPage() {
  const qc = useQueryClient();
  const fileRef = useRef<HTMLInputElement>(null);
  const [tab, setTab] = useState<SourceTab>("upload");
  const [rows, setRows] = useState<Row[]>([]);
  const [paste, setPaste] = useState("");
  const [sheetUrl, setSheetUrl] = useState("");
  const [fileName, setFileName] = useState("");
  const [dragging, setDragging] = useState(false);
  const [error, setError] = useState("");
  const [result, setResult] = useState("");
  const [loadingSheet, setLoadingSheet] = useState(false);
  const [progress, setProgress] = useState<{ done: number; total: number } | null>(null);

  const selected = useMemo(() => rows.filter((r) => r.selected), [rows]);
  const selectedCount = selected.length;
  const allSelected = rows.length > 0 && rows.every((r) => r.selected);

  function applyRows(next: Row[], sourceLabel?: string) {
    setRows(next);
    setResult("");
    setError(next.length ? "" : "No Instagram usernames found in that sheet.");
    if (sourceLabel && next.length) setFileName(sourceLabel);
  }

  function handleFile(file: File) {
    setError("");
    setResult("");
    setFileName(file.name);
    const lower = file.name.toLowerCase();

    if (lower.endsWith(".xlsx") || lower.endsWith(".xls")) {
      const reader = new FileReader();
      reader.onload = (e) => {
        try {
          const data = new Uint8Array(e.target?.result as ArrayBuffer);
          const wb = XLSX.read(data, { type: "array" });
          const sheet = wb.Sheets[wb.SheetNames[0]];
          const matrix = XLSX.utils.sheet_to_json<string[]>(sheet, { header: 1, defval: "" }) as string[][];
          applyRows(parseMatrix(matrix), file.name);
        } catch {
          setError("Could not read that Excel file.");
        }
      };
      reader.readAsArrayBuffer(file);
      return;
    }

    Papa.parse(file, {
      complete: (res) => {
        const matrix = (res.data as string[][]).filter((r) => r.some((c) => String(c || "").trim()));
        applyRows(parseMatrix(matrix), file.name);
      },
      error: () => setError("Could not parse that CSV file."),
    });
  }

  function loadFromPaste() {
    const lines = paste
      .split(/\r?\n/)
      .map((l) => l.trim())
      .filter(Boolean);
    const matrix = lines.map((l) => l.split("\t").map((c) => c.trim()));
    applyRows(parseMatrix(matrix), "Pasted from sheet");
  }

  async function loadFromGoogleSheet() {
    setLoadingSheet(true);
    setError("");
    setResult("");
    try {
      const csvUrl = googleSheetToCsvUrl(sheetUrl);
      if (!csvUrl) {
        setError("Paste a Google Sheets link (File → Share → Anyone with the link).");
        return;
      }
      const res = await fetch(csvUrl);
      if (!res.ok) {
        setError("Could not fetch the sheet. Make sure it’s shared as “Anyone with the link”.");
        return;
      }
      const text = await res.text();
      const parsed = Papa.parse<string[]>(text, { header: false });
      const matrix = (parsed.data as string[][]).filter((r) => r.some((c) => String(c || "").trim()));
      applyRows(parseMatrix(matrix), "Google Sheet");
    } catch {
      setError("Failed to load Google Sheet. Check sharing settings and try again.");
    } finally {
      setLoadingSheet(false);
    }
  }

  const importAll = useMutation({
    mutationFn: async () => {
      const payloadRows = selected.map((r) => ({ url: r.raw, student: r.student }));
      setProgress({ done: 0, total: payloadRows.length });
      const chunkSize = 50;
      let imported = 0;
      let skipped = 0;
      let failed = 0;
      let updated = 0;
      let duplicates = 0;
      let scraping = false;
      const allItems: BulkImportResponse["items"] = [];

      for (let i = 0; i < payloadRows.length; i += chunkSize) {
        const chunk = payloadRows.slice(i, i + chunkSize);
        const res = await api<BulkImportResponse>("/profiles/bulk/import", {
          method: "POST",
          body: JSON.stringify({ rows: chunk, scrape_now: true }),
        });
        imported += res.imported;
        skipped += res.skipped;
        failed += res.failed;
        updated += res.updated || 0;
        duplicates += res.duplicates || 0;
        scraping = scraping || res.scraping;
        allItems.push(...res.items);
        setProgress({ done: Math.min(i + chunk.length, payloadRows.length), total: payloadRows.length });
      }

      return { imported, skipped, failed, updated, duplicates, scraping, items: allItems };
    },
    onSuccess: (r) => {
      saveDuplicatesFromImport(r.items);
      saveUnimportedFromImport(r.items);
      const dupPart = r.duplicates ? ` · ${r.duplicates} duplicates` : "";
      setResult(
        `Imported ${r.imported} · updated ${r.updated || 0}${dupPart} · skipped ${r.skipped} · failed ${r.failed}` +
          (r.scraping ? ". Live scraping started for new accounts — open Profiles to watch updates." : ".") +
          (r.duplicates ? " Duplicates saved — open Duplicates to review." : "")
      );
      setError("");
      setProgress(null);
      setRows((prev) =>
        prev.map((row) => {
          const item = r.items.find((i) => extractUsername(i.url) === row.username);
          if (item?.status === "imported") return { ...row, selected: false };
          return row;
        })
      );
      qc.invalidateQueries({ queryKey: ["profiles"] });
      qc.invalidateQueries({ queryKey: ["overview"] });
    },
    onError: (e: Error) => {
      setError(e.message);
      setProgress(null);
    },
  });

  const tabs: { id: SourceTab; label: string; icon: typeof Upload }[] = [
    { id: "upload", label: "Upload", icon: Upload },
    { id: "sheet", label: "Sheet link", icon: Sheet },
    { id: "paste", label: "Paste", icon: FileSpreadsheet },
  ];

  return (
    <div className="grid gap-4 lg:grid-cols-[340px_minmax(0,1fr)] lg:items-stretch lg:min-h-[calc(100vh-140px)]">
      {/* Source panel */}
      <aside className="flex flex-col overflow-hidden rounded-[22px] bg-[#FFE8D6] shadow-card">
        <div className="border-b border-stone-900/5 px-5 py-4">
          <div className="text-[11px] font-medium uppercase tracking-[0.14em] text-stone-500">Bring accounts in</div>
          <div className="mt-1 font-[family-name:var(--font-display)] text-xl font-semibold tracking-tight text-stone-900">
            Import
          </div>
          <p className="mt-1 text-xs leading-relaxed text-stone-600">
            CSV, Excel, Google Sheets, or paste — then import the selection.
          </p>
        </div>

        <div className="flex gap-1 p-3">
          {tabs.map((t) => {
            const Icon = t.icon;
            const active = tab === t.id;
            return (
              <button
                key={t.id}
                type="button"
                onClick={() => setTab(t.id)}
                className={cn(
                  "flex flex-1 items-center justify-center gap-1.5 rounded-xl px-2 py-2.5 text-xs font-medium transition",
                  active ? "bg-white text-stone-900 shadow-soft" : "text-stone-600 hover:bg-white/50"
                )}
              >
                <Icon size={13} />
                {t.label}
              </button>
            );
          })}
        </div>

        <div className="flex flex-1 flex-col gap-3 px-4 pb-4">
          {tab === "upload" && (
            <div
              role="button"
              tabIndex={0}
              onClick={() => fileRef.current?.click()}
              onKeyDown={(e) => e.key === "Enter" && fileRef.current?.click()}
              onDragOver={(e) => {
                e.preventDefault();
                setDragging(true);
              }}
              onDragLeave={() => setDragging(false)}
              onDrop={(e) => {
                e.preventDefault();
                setDragging(false);
                const f = e.dataTransfer.files?.[0];
                if (f) handleFile(f);
              }}
              className={cn(
                "flex flex-1 cursor-pointer flex-col items-center justify-center rounded-2xl border border-dashed bg-white/70 px-4 py-8 text-center transition",
                dragging ? "border-stone-800 bg-white" : "border-stone-400/40 hover:border-stone-500 hover:bg-white"
              )}
            >
              <input
                ref={fileRef}
                type="file"
                accept=".csv,.tsv,.txt,.xlsx,.xls"
                className="hidden"
                onChange={(e) => {
                  const f = e.target.files?.[0];
                  if (f) handleFile(f);
                  e.target.value = "";
                }}
              />
              <div className="flex h-11 w-11 items-center justify-center rounded-2xl bg-stone-900 text-white">
                <Upload size={18} />
              </div>
              <div className="mt-3 text-sm font-semibold text-stone-900">Drop file or click</div>
              <p className="mt-1 max-w-[220px] text-[11px] leading-relaxed text-stone-500">
                .csv · .tsv · .xlsx — username / url columns auto-detected
              </p>
              {fileName && (
                <div className="mt-3 max-w-full truncate rounded-full bg-white px-3 py-1 text-[11px] font-medium text-stone-700 shadow-soft">
                  {fileName}
                </div>
              )}
            </div>
          )}

          {tab === "sheet" && (
            <div className="flex flex-1 flex-col rounded-2xl bg-white/70 p-4">
              <div className="flex items-center gap-2">
                <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-emerald-100 text-emerald-700">
                  <Sheet size={15} />
                </div>
                <div>
                  <div className="text-sm font-semibold">Google Sheets</div>
                  <p className="text-[11px] text-stone-500">Share → Anyone with the link</p>
                </div>
              </div>
              <Input
                className="mt-4"
                placeholder="https://docs.google.com/spreadsheets/d/..."
                value={sheetUrl}
                onChange={(e) => setSheetUrl(e.target.value)}
              />
              <Button
                className="mt-3 w-full"
                onClick={loadFromGoogleSheet}
                disabled={loadingSheet || !sheetUrl.trim()}
                variant="secondary"
              >
                {loadingSheet ? <Loader2 size={15} className="animate-spin" /> : <Link2 size={15} />}
                Load sheet
              </Button>
            </div>
          )}

          {tab === "paste" && (
            <div className="flex flex-1 flex-col rounded-2xl bg-white/70 p-4">
              <div className="flex items-center gap-2">
                <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-sky-100 text-sky-700">
                  <FileSpreadsheet size={15} />
                </div>
                <div>
                  <div className="text-sm font-semibold">Paste rows</div>
                  <p className="text-[11px] text-stone-500">From Excel or Sheets</p>
                </div>
              </div>
              <textarea
                className="mt-3 min-h-[160px] flex-1 w-full resize-none rounded-xl border border-stone-200/80 bg-white p-3 text-sm leading-relaxed outline-none placeholder:text-stone-400 focus:border-stone-400"
                placeholder={"username\ncristiano\nleomessi\nnatgeo"}
                value={paste}
                onChange={(e) => setPaste(e.target.value)}
              />
              <Button className="mt-3 w-full" variant="secondary" onClick={loadFromPaste} disabled={!paste.trim()}>
                Parse rows
              </Button>
            </div>
          )}

          <div className="rounded-2xl bg-white/50 px-3.5 py-3">
            <div className="text-[11px] font-medium uppercase tracking-[0.12em] text-stone-500">Quick tip</div>
            <p className="mt-1 text-xs leading-relaxed text-stone-600">
              One username or profile URL per row. Duplicates are removed automatically.
            </p>
          </div>
        </div>
      </aside>

      {/* Preview panel */}
      <section className="flex min-h-[520px] flex-col overflow-hidden rounded-[22px] bg-white shadow-card">
        <div className="flex flex-wrap items-center justify-between gap-3 border-b border-stone-200/70 px-5 py-4">
          <div className="flex items-center gap-3">
            <div>
              <div className="text-sm font-semibold tracking-tight">Preview</div>
              <p className="text-xs text-stone-500">
                <span className="tabular font-medium text-stone-800">{rows.length}</span> unique
                {" · "}
                <span className="tabular font-medium text-stone-800">{selectedCount}</span> selected
              </p>
            </div>
            {fileName && rows.length > 0 && (
              <span className="hidden rounded-full bg-stone-100 px-2.5 py-1 text-[11px] font-medium text-stone-600 sm:inline">
                {fileName}
              </span>
            )}
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <Button
              size="sm"
              variant="secondary"
              disabled={!selectedCount}
              onClick={() =>
                downloadImportableCsv(
                  selected.map((r) => ({ username: r.username, url: r.raw, student: r.student }))
                )
              }
            >
              <Download size={14} /> Download CSV
            </Button>
            <Button
              size="sm"
              variant="secondary"
              disabled={!rows.length}
              onClick={() => setRows((prev) => prev.map((r) => ({ ...r, selected: !allSelected })))}
            >
              {allSelected ? <CheckSquare size={14} /> : <Square size={14} />}
              {allSelected ? "Deselect" : "Select all"}
            </Button>
            <Button size="sm" variant="ghost" disabled={!rows.length} onClick={() => setRows([])}>
              <Trash2 size={14} /> Clear
            </Button>
            <Link
              href="/imports/duplicates"
              className="inline-flex h-9 items-center rounded-xl border border-stone-200/80 bg-white px-3 text-sm font-medium text-stone-700 shadow-soft hover:bg-stone-50"
            >
              Duplicates
            </Link>
            <Button
              disabled={!selectedCount || importAll.isPending}
              onClick={() => importAll.mutate()}
              className="min-w-[132px]"
            >
              {importAll.isPending ? (
                <>
                  <Loader2 size={15} className="animate-spin" />
                  Importing…
                </>
              ) : (
                <>Import ({selectedCount})</>
              )}
            </Button>
          </div>
        </div>

        {progress && (
          <div className="border-b border-stone-100 px-5 py-3">
            <div className="mb-1.5 flex justify-between text-xs text-stone-500">
              <span>Importing…</span>
              <span className="tabular">
                {progress.done}/{progress.total}
              </span>
            </div>
            <div className="h-1.5 overflow-hidden rounded-full bg-stone-100">
              <div
                className="h-full rounded-full bg-stone-900 transition-[width] duration-300"
                style={{ width: `${(progress.done / Math.max(progress.total, 1)) * 100}%` }}
              />
            </div>
          </div>
        )}

        {(error || result) && (
          <div className="space-y-2 border-b border-stone-100 px-5 py-3">
            {error && <div className="rounded-xl bg-[#FFD9D2] px-3.5 py-2 text-sm text-[#9f1239]">{error}</div>}
            {result && <div className="rounded-xl bg-[#d1fae5] px-3.5 py-2 text-sm text-[#047857]">{result}</div>}
          </div>
        )}

        <div className="min-h-0 flex-1 overflow-auto">
          {rows.length === 0 ? (
            <div className="flex h-full min-h-[360px] flex-col items-center justify-center px-6 text-center">
              <div className="grid w-full max-w-md grid-cols-3 gap-2">
                {[
                  { n: "01", t: "Choose source", d: "Upload, sheet, or paste" },
                  { n: "02", t: "Review list", d: "Select who to track" },
                  { n: "03", t: "Import all", d: "Scrape starts live" },
                ].map((s) => (
                  <div key={s.n} className="rounded-2xl bg-[#f3efe8] px-3 py-4 text-left">
                    <div className="text-[10px] font-semibold tracking-wider text-stone-400">{s.n}</div>
                    <div className="mt-1 text-xs font-semibold text-stone-800">{s.t}</div>
                    <div className="mt-0.5 text-[10px] leading-snug text-stone-500">{s.d}</div>
                  </div>
                ))}
              </div>
              <p className="mt-6 max-w-sm text-sm text-stone-500">
                Load accounts on the left — the preview table fills here.
              </p>
            </div>
          ) : (
            <table className="table-premium">
              <thead className="sticky top-0 z-10 bg-white">
                <tr>
                  <th className="w-10 pl-5"></th>
                  <th>Username</th>
                  <th className="hidden sm:table-cell">Source</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((row) => (
                  <tr
                    key={row.id}
                    className="cursor-pointer"
                    onClick={() =>
                      setRows((prev) =>
                        prev.map((r) => (r.id === row.id ? { ...r, selected: !r.selected } : r))
                      )
                    }
                  >
                    <td className="pl-5" onClick={(e) => e.stopPropagation()}>
                      <input
                        type="checkbox"
                        className="rounded border-slate-300"
                        checked={row.selected}
                        onChange={(e) =>
                          setRows((prev) =>
                            prev.map((r) => (r.id === row.id ? { ...r, selected: e.target.checked } : r))
                          )
                        }
                      />
                    </td>
                    <td className="font-medium">@{row.username}</td>
                    <td className="hidden max-w-[280px] truncate text-muted sm:table-cell">{row.raw}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      </section>
    </div>
  );
}
