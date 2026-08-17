"use client";

import Link from "next/link";
import { useMemo, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Download, FileSpreadsheet, Loader2, Sheet, Upload } from "lucide-react";
import Papa from "papaparse";
import * as XLSX from "xlsx";
import { api } from "@/lib/api";
import { saveDuplicatesFromImport } from "@/lib/import-duplicates";
import { saveUnimportedFromImport, saveUnimportedFromParse } from "@/lib/import-unimported";
import { cn } from "@/lib/utils";
import { downloadImportableCsv, parseSheetMatrixDetailed, type SheetStudent } from "@/lib/student-sheet";
import { type ScrapeStatusResponse } from "@/lib/scrape-progress";
import { ScrapeActivityBanner, ScrapeProgressBar } from "@/components/scrape-progress";

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

function parseMatrix(matrix: string[][], sheetLabel?: string): { rows: Row[]; rejectedCount: number } {
  const { rows, rejected } = parseSheetMatrixDetailed(matrix);
  if (rejected.length) saveUnimportedFromParse(rejected, sheetLabel);
  return {
    rows: rows.map((r, i) => ({
      id: `${r.username}-${i}`,
      raw: r.url,
      username: r.username,
      student: r.student,
      selected: true,
    })),
    rejectedCount: rejected.length,
  };
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

export default function AdminImportPage() {
  const qc = useQueryClient();
  const fileRef = useRef<HTMLInputElement>(null);
  const [tab, setTab] = useState<SourceTab>("upload");
  const [rows, setRows] = useState<Row[]>([]);
  const [paste, setPaste] = useState("");
  const [sheetUrl, setSheetUrl] = useState("");
  const [fileName, setFileName] = useState("");
  const [error, setError] = useState("");
  const [result, setResult] = useState("");
  const [loadingSheet, setLoadingSheet] = useState(false);
  const [progress, setProgress] = useState<{ done: number; total: number } | null>(null);
  const [watchScrapes, setWatchScrapes] = useState(false);
  const [rejectedCount, setRejectedCount] = useState(0);

  const selected = useMemo(() => rows.filter((r) => r.selected), [rows]);
  const missingStudentId = useMemo(
    () => selected.filter((r) => !String(r.student.student_id || "").trim()).length,
    [selected]
  );

  const scrapeStatusQ = useQuery({
    queryKey: ["scrape-status"],
    queryFn: () => api<ScrapeStatusResponse>("/profiles/scrape-status"),
    enabled: watchScrapes,
    refetchInterval: (query) => {
      const n = query.state.data?.active_count || 0;
      return n > 0 ? 2500 : 8000;
    },
  });

  function applyRows(next: Row[], sourceLabel?: string, rejected = 0) {
    setRows(next);
    setRejectedCount(rejected);
    setResult("");
    if (!next.length) {
      setError(
        rejected > 0
          ? `No importable Instagram rows. ${rejected} line(s) saved under Unimported.`
          : "No Instagram usernames found in that sheet."
      );
    } else {
      setError("");
    }
    if (sourceLabel && (next.length || rejected)) setFileName(sourceLabel);
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
          const parsed = parseMatrix(matrix, file.name);
          applyRows(parsed.rows, file.name, parsed.rejectedCount);
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
        const parsed = parseMatrix(matrix, file.name);
        applyRows(parsed.rows, file.name, parsed.rejectedCount);
      },
      error: () => setError("Could not parse that CSV file."),
    });
  }

  async function loadFromGoogleSheet() {
    setLoadingSheet(true);
    setError("");
    try {
      const csvUrl = googleSheetToCsvUrl(sheetUrl);
      if (!csvUrl) {
        setError("Paste a Google Sheets link (Share → Anyone with the link).");
        return;
      }
      const res = await fetch(csvUrl);
      if (!res.ok) {
        setError("Could not fetch the sheet. Check sharing settings.");
        return;
      }
      const text = await res.text();
      const parsed = Papa.parse<string[]>(text, { header: false });
      const matrix = (parsed.data as string[][]).filter((r) => r.some((c) => String(c || "").trim()));
      const result = parseMatrix(matrix, "Google Sheet");
      applyRows(result.rows, "Google Sheet", result.rejectedCount);
    } catch {
      setError("Failed to load Google Sheet.");
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
      const rejectNote =
        rejectedCount > 0
          ? ` · ${rejectedCount} sheet row(s) not importable (see Unimported)`
          : "";
      setResult(
        `Imported ${r.imported} · updated ${r.updated || 0} · duplicates ${r.duplicates || 0} · skipped ${r.skipped} · failed ${r.failed}${rejectNote}` +
          (r.scraping
            ? ". Instagram scrape started — watch live progress below."
            : ".") +
          " YouTube links/@handles auto-connect + sync (Scraping → YouTube queue)."
      );
      setError("");
      setProgress(null);
      if (r.scraping) setWatchScrapes(true);
      qc.invalidateQueries({ queryKey: ["profiles"] });
      qc.invalidateQueries({ queryKey: ["spark"] });
      qc.invalidateQueries({ queryKey: ["scrape-status"] });
      qc.invalidateQueries({ queryKey: ["youtube", "sync-status"] });
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

  const importPct =
    progress && progress.total > 0 ? Math.round((100 * progress.done) / progress.total) : 0;

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Roster import</h1>
        <p className="mt-1 text-sm text-zinc-500">
          Import the SPARK registration sheet. Each row needs an Instagram handle; include{" "}
          <span className="text-zinc-300">Student ID</span> so students can log in after scrape.
          YouTube Link / Username columns are connected and synced automatically; Instagram scrapes when you import.
          Daily YouTube updates run at 08:00 IST like Instagram (when the YouTube toggle is on).
        </p>
      </div>

      {watchScrapes ? (
        scrapeStatusQ.data && (scrapeStatusQ.data.active_count || 0) > 0 ? (
          <ScrapeActivityBanner status={scrapeStatusQ.data} />
        ) : (
          <div className="rounded-2xl border border-[#ff3b30]/35 bg-[#ff3b30]/10 px-4 py-4 text-sm text-zinc-200">
            {scrapeStatusQ.isLoading
              ? "Loading live scrape progress…"
              : "Scrapes queued — waiting for the first account to start. Progress (account, posts scraped/total, %) will appear here."}
          </div>
        )
      ) : null}

      <div className="grid gap-4 lg:grid-cols-[320px_minmax(0,1fr)]">
        <aside className="rounded-2xl border border-white/[0.06] bg-[#121212] p-4">
          <div className="flex gap-1 rounded-xl bg-black p-1">
            {tabs.map((t) => {
              const Icon = t.icon;
              return (
                <button
                  key={t.id}
                  type="button"
                  onClick={() => setTab(t.id)}
                  className={cn(
                    "flex flex-1 items-center justify-center gap-1.5 rounded-lg px-2 py-2 text-xs font-medium",
                    tab === t.id ? "bg-[#ff3b30] text-white" : "text-zinc-400 hover:text-white"
                  )}
                >
                  <Icon size={13} />
                  {t.label}
                </button>
              );
            })}
          </div>

          <div className="mt-4">
            {tab === "upload" && (
              <div
                role="button"
                tabIndex={0}
                onClick={() => fileRef.current?.click()}
                onKeyDown={(e) => e.key === "Enter" && fileRef.current?.click()}
                className="flex cursor-pointer flex-col items-center justify-center rounded-xl border border-dashed border-white/15 bg-black/40 px-4 py-10 text-center"
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
                <Upload size={18} className="text-[#ff3b30]" />
                <div className="mt-3 text-sm font-medium">Drop CSV / Excel or click</div>
                <p className="mt-1 text-[11px] text-zinc-500">Columns auto-mapped from sheet headers</p>
                {fileName && <div className="mt-3 text-[11px] text-zinc-400">{fileName}</div>}
              </div>
            )}

            {tab === "sheet" && (
              <div className="space-y-3">
                <input
                  value={sheetUrl}
                  onChange={(e) => setSheetUrl(e.target.value)}
                  placeholder="Google Sheets URL"
                  className="w-full rounded-xl border border-white/10 bg-black px-3 py-2.5 text-sm outline-none focus:border-[#ff3b30]"
                />
                <button
                  type="button"
                  disabled={loadingSheet}
                  onClick={loadFromGoogleSheet}
                  className="inline-flex w-full items-center justify-center gap-2 rounded-xl bg-[#ff3b30] px-3 py-2.5 text-sm font-semibold disabled:opacity-60"
                >
                  {loadingSheet ? <Loader2 size={14} className="animate-spin" /> : null}
                  Load sheet
                </button>
              </div>
            )}

            {tab === "paste" && (
              <div className="space-y-3">
                <textarea
                  value={paste}
                  onChange={(e) => setPaste(e.target.value)}
                  rows={10}
                  placeholder={"Paste TSV rows including Student ID + Instagram columns"}
                  className="w-full rounded-xl border border-white/10 bg-black px-3 py-2.5 text-sm outline-none focus:border-[#ff3b30]"
                />
                <button
                  type="button"
                  onClick={() => {
                    const lines = paste.split(/\r?\n/).map((l) => l.trim()).filter(Boolean);
                    const matrix = lines.map((l) => l.split("\t").map((c) => c.trim()));
                    const result = parseMatrix(matrix, "Pasted sheet");
                    applyRows(result.rows, "Pasted sheet", result.rejectedCount);
                  }}
                  className="w-full rounded-xl bg-[#ff3b30] px-3 py-2.5 text-sm font-semibold"
                >
                  Parse paste
                </button>
              </div>
            )}
          </div>
        </aside>

        <section className="rounded-2xl border border-white/[0.06] bg-[#121212] p-5">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div>
              <div className="text-sm font-semibold">
                Preview · {selected.length} selected of {rows.length}
                {rejectedCount > 0 ? (
                  <span className="ml-2 font-normal text-amber-400">
                    · {rejectedCount} unimported{" "}
                    <Link href="/admin-unimported" className="underline">
                      view
                    </Link>
                  </span>
                ) : null}
              </div>
              {missingStudentId > 0 && (
                <p className="mt-1 text-xs text-amber-400">
                  {missingStudentId} selected row(s) missing Student ID — they can be scraped but students won’t be able
                  to log in until you add NIAT IDs.
                </p>
              )}
            </div>
            <div className="flex flex-wrap gap-2">
              <button
                type="button"
                disabled={!selected.length}
                onClick={() =>
                  downloadImportableCsv(
                    selected.map((r) => ({ username: r.username, url: r.raw, student: r.student }))
                  )
                }
                className="inline-flex items-center gap-1.5 rounded-lg border border-white/10 px-3 py-1.5 text-xs disabled:opacity-40"
              >
                <Download size={13} /> Download CSV
              </button>
              <button
                type="button"
                onClick={() => setRows((prev) => prev.map((r) => ({ ...r, selected: true })))}
                className="rounded-lg border border-white/10 px-3 py-1.5 text-xs"
              >
                Select all
              </button>
              <button
                type="button"
                onClick={() => setRows((prev) => prev.map((r) => ({ ...r, selected: false })))}
                className="rounded-lg border border-white/10 px-3 py-1.5 text-xs"
              >
                Clear
              </button>
              <button
                type="button"
                disabled={!selected.length || importAll.isPending}
                onClick={() => importAll.mutate()}
                className="rounded-xl bg-[#ff3b30] px-4 py-2 text-xs font-semibold disabled:opacity-40"
              >
                {importAll.isPending
                  ? `Importing ${progress?.done || 0}/${progress?.total || 0}…`
                  : `Import & scrape ${selected.length}`}
              </button>
            </div>
          </div>

          {progress ? (
            <div className="mt-4 space-y-2 rounded-xl border border-white/10 bg-black/40 px-3 py-3">
              <div className="flex items-center justify-between text-xs text-zinc-300">
                <span>
                  Importing rows {progress.done} / {progress.total}
                </span>
                <span className="tabular">{importPct}%</span>
              </div>
              <ScrapeProgressBar percent={importPct} />
            </div>
          ) : null}

          {error && <p className="mt-3 text-sm text-rose-400">{error}</p>}
          {result && (
            <p className="mt-3 text-sm text-lime-400">
              {result}{" "}
              <Link href="/admin-scraping" className="underline">
                Open scraping table
              </Link>
              {" · "}
              <Link href="/admin-unimported" className="underline">
                Unimported rows
              </Link>
              {" · "}
              <Link href="/admin-duplicates" className="underline">
                View duplicates
              </Link>
            </p>
          )}

          <div className="mt-4 overflow-x-auto">
            {!rows.length ? (
              <div className="rounded-xl border border-dashed border-white/10 px-4 py-12 text-center text-sm text-zinc-500">
                Load a roster sheet to preview creators.
              </div>
            ) : (
              <table className="min-w-[720px] w-full text-left text-sm">
                <thead>
                  <tr className="border-b border-white/[0.06] text-[10px] uppercase tracking-[0.12em] text-zinc-500">
                    <th className="px-2 py-2" />
                    <th className="px-2 py-2">Instagram</th>
                    <th className="px-2 py-2">Student ID</th>
                    <th className="px-2 py-2">Name</th>
                    <th className="px-2 py-2">Campus</th>
                  </tr>
                </thead>
                <tbody>
                  {rows.map((r) => (
                    <tr key={r.id} className="border-b border-white/[0.04]">
                      <td className="px-2 py-2">
                        <input
                          type="checkbox"
                          checked={r.selected}
                          onChange={(e) =>
                            setRows((prev) =>
                              prev.map((row) => (row.id === r.id ? { ...row, selected: e.target.checked } : row))
                            )
                          }
                        />
                      </td>
                      <td className="px-2 py-2">@{r.username}</td>
                      <td className={cn("px-2 py-2", !r.student.student_id && "text-amber-400")}>
                        {r.student.student_id || "missing"}
                      </td>
                      <td className="px-2 py-2 text-zinc-400">{r.student.full_name || "—"}</td>
                      <td className="px-2 py-2 text-zinc-400">{r.student.university || "—"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        </section>
      </div>
    </div>
  );
}
