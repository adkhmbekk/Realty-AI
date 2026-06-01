import React, { useEffect, useState } from "react";
import { useApp } from "../store";
import { api } from "../api";
import { Card, Empty, Segmented, Spinner } from "../components/ui";
import { fmtDate } from "../utils";
import { ObjectList } from "./Apartments";
import type { AgentEvent } from "../types";

const ACTION_KEY: Record<string, string> = {
  created: "evCreated",
  updated: "evUpdated",
  status: "evStatusChanged",
};

export function AgentDetailScreen({ userId, agentName }: { userId: number; agentName: string }) {
  const { t, lang } = useApp();
  const [tab, setTab] = useState<"added" | "sold">("added");
  const [activity, setActivity] = useState<AgentEvent[] | null>(null);

  useEffect(() => {
    api<AgentEvent[]>(`/api/v1/apartments/agent/${userId}/activity`).then((r) => {
      setActivity(r.ok && Array.isArray(r.data) ? r.data : []);
    });
  }, [userId]);

  return (
    <div>
      <div className="text-[15px] font-extrabold mb-2 mx-0.5">{agentName}</div>

      <Segmented
        value={tab}
        onChange={(v) => setTab(v)}
        options={[
          { value: "added", label: t("addedObjects") },
          { value: "sold", label: t("soldObjects") },
        ]}
      />

      <div className="mt-2">
        {tab === "added" ? (
          <ObjectList params={{ created_by: userId, status: "all" }} />
        ) : (
          <ObjectList params={{ created_by: userId, status: "sold" }} />
        )}
      </div>

      <div className="text-[13px] font-extrabold uppercase tracking-wider text-muted mx-0.5 mt-6 mb-2">
        {t("recentActivity")}
      </div>
      {activity === null ? (
        <Spinner />
      ) : activity.length === 0 ? (
        <Empty>{t("noActivity")}</Empty>
      ) : (
        <Card className="py-1">
          {activity.map((e, i) => (
            <div
              key={i}
              className="flex items-center justify-between gap-2 py-2.5 text-sm border-t border-[var(--border)] first:border-t-0"
            >
              <span className="font-semibold">
                №{e.display_id}{" "}
                <span className="text-muted font-normal">{t(ACTION_KEY[e.action] || "evUpdated")}</span>
              </span>
              <span className="text-[12px] text-muted shrink-0">{fmtDate(e.created_at, lang)}</span>
            </div>
          ))}
        </Card>
      )}
    </div>
  );
}
