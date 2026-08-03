"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Bell } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, EmptyState } from "@/components/ui/card";
import { api } from "@/lib/api";

type Notification = {
  id: string;
  type: string;
  title: string;
  body: string;
  is_read: boolean;
  created_at: string;
};

export default function NotificationsPage() {
  const qc = useQueryClient();
  const { data = [], isLoading } = useQuery({
    queryKey: ["notifications"],
    queryFn: () => api<Notification[]>("/notifications"),
  });

  const markAll = useMutation({
    mutationFn: () => api("/notifications/read-all", { method: "POST" }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["notifications"] }),
  });

  return (
    <div className="space-y-7">
      <div className="flex justify-end">
        <Button variant="secondary" onClick={() => markAll.mutate()} disabled={markAll.isPending}>
          Mark all read
        </Button>
      </div>

      <div className="space-y-3">
        {isLoading && Array.from({ length: 3 }).map((_, i) => <div key={i} className="h-24 skeleton" />)}
        {data.map((n) => (
          <Card key={n.id} hover className={n.is_read ? "opacity-65" : ""}>
            <div className="flex items-start gap-4">
              <div className={`mt-0.5 flex h-10 w-10 shrink-0 items-center justify-center rounded-xl ${n.is_read ? "bg-slate-100 text-slate-400" : "bg-accent-soft text-accent"}`}>
                <Bell size={16} />
              </div>
              <div className="min-w-0 flex-1">
                <div className="flex items-start justify-between gap-3">
                  <div className="text-sm font-semibold tracking-tight">{n.title}</div>
                  {!n.is_read && <span className="mt-1.5 h-2 w-2 shrink-0 rounded-full bg-accent shadow-[0_0_8px_rgba(79,70,229,0.6)]" />}
                </div>
                <p className="mt-1 text-sm leading-relaxed text-muted">{n.body}</p>
                <div className="mt-2.5 text-[11px] uppercase tracking-[0.12em] text-slate-400">
                  {new Date(n.created_at).toLocaleString()} · {n.type.replaceAll("_", " ")}
                </div>
              </div>
            </div>
          </Card>
        ))}
        {!isLoading && !data.length && (
          <EmptyState title="All quiet" description="You’ll see growth and scrape alerts here as they happen." />
        )}
      </div>
    </div>
  );
}
