"use client";

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { ArrowUpRight } from "lucide-react";
import { Card, EmptyState } from "@/components/ui/card";
import { api, type Profile } from "@/lib/api";
import { formatNumber } from "@/lib/utils";
import { Avatar } from "@/components/ui/avatar";

export default function AnalyticsPage() {
  const { data, isLoading } = useQuery({
    queryKey: ["profiles-analytics-page"],
    queryFn: () => api<{ items: Profile[] }>("/profiles?page_size=50"),
  });

  return (
    <div className="space-y-7">
      {isLoading && (
        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
          {Array.from({ length: 6 }).map((_, i) => (
            <div key={i} className="h-36 skeleton" />
          ))}
        </div>
      )}

      {!isLoading && !data?.items.length && (
        <EmptyState title="Nothing to analyze yet" description="Add profiles first, then return here for portfolio shortcuts." />
      )}

      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
        {(data?.items || []).map((p) => (
          <Link key={p.id} href={`/profiles/${p.id}`}>
            <Card hover className="h-full">
              <div className="flex items-start justify-between gap-3">
                <div className="flex items-center gap-3 min-w-0">
                  <Avatar name={p.username} size="md" />
                  <div className="min-w-0">
                    <div className="truncate font-semibold tracking-tight">@{p.username}</div>
                    <div className="truncate text-xs text-muted">{p.full_name}</div>
                  </div>
                </div>
                <ArrowUpRight size={15} className="shrink-0 text-slate-300" />
              </div>
              <div className="mt-5 grid grid-cols-3 gap-3 border-t border-border pt-4">
                <div>
                  <div className="eyebrow">Followers</div>
                  <div className="mt-1 text-sm font-semibold tabular">{formatNumber(p.followers)}</div>
                </div>
                <div>
                  <div className="eyebrow">Engage</div>
                  <div className="mt-1 text-sm font-semibold tabular">{p.engagement_rate.toFixed(2)}%</div>
                </div>
                <div>
                  <div className="eyebrow">Avg likes</div>
                  <div className="mt-1 text-sm font-semibold tabular">{formatNumber(p.avg_likes)}</div>
                </div>
              </div>
            </Card>
          </Link>
        ))}
      </div>
    </div>
  );
}
