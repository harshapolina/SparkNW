"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { ArrowLeft, Trash2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, EmptyState } from "@/components/ui/card";
import {
  appendImportDuplicates,
  clearImportDuplicates,
  loadImportDuplicates,
  type ImportDuplicateItem,
} from "@/lib/import-duplicates";

export default function ImportDuplicatesPage() {
  const [items, setItems] = useState<ImportDuplicateItem[]>([]);
  const [ready, setReady] = useState(false);

  useEffect(() => {
    setItems(loadImportDuplicates());
    setReady(true);
  }, []);

  if (!ready) {
    return <div className="h-48 skeleton" />;
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <Link href="/imports" className="mb-2 inline-flex items-center gap-1 text-sm text-muted hover:text-fg">
            <ArrowLeft size={14} /> Back to import
          </Link>
          <h1 className="font-[family-name:var(--font-display)] text-2xl font-semibold tracking-tight">Duplicates</h1>
          <p className="mt-1 text-sm text-muted">
            Accounts that were already tracked when you imported a sheet. New rows were merged; scrapes were skipped for
            profiles that already succeeded.
          </p>
        </div>
        {items.length > 0 && (
          <Button
            variant="secondary"
            size="sm"
            onClick={() => {
              clearImportDuplicates();
              setItems([]);
            }}
          >
            <Trash2 size={14} /> Clear list
          </Button>
        )}
      </div>

      <Card padding="lg">
        {!items.length ? (
          <EmptyState
            title="No duplicates yet"
            description="When you re-import a sheet, accounts that already exist will appear here instead of being scraped again."
          />
        ) : (
          <div className="overflow-x-auto">
            <table className="table-premium min-w-[720px]">
              <thead>
                <tr>
                  <th>Username</th>
                  <th>Source URL</th>
                  <th>Note</th>
                  <th>When</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                {items.map((item) => (
                  <tr key={`${item.profile_id || item.url}-${item.imported_at}`}>
                    <td className="font-medium">@{item.username || "—"}</td>
                    <td className="max-w-[240px] truncate text-sm text-muted" title={item.url}>
                      {item.url}
                    </td>
                    <td className="text-sm text-muted">{item.message || "Already tracked"}</td>
                    <td className="whitespace-nowrap text-xs text-muted">
                      {new Date(item.imported_at).toLocaleString()}
                    </td>
                    <td>
                      {item.profile_id ? (
                        <Link href={`/profiles/${item.profile_id}`} className="text-sm text-accent hover:underline">
                          View profile
                        </Link>
                      ) : null}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>
    </div>
  );
}
