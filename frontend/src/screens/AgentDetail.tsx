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

// Журнал последних действий сотрудника (отдельная вкладка, чтобы не прокручивать
// длинные списки объектов до самого низа).
function ActivityLog({ userId }: { userId: number }) {
  const { t, lang } = useApp();
  const [activity, setActivity] = useState<AgentEvent[] | null>(null);

  useEffect(() => {
    api<AgentEvent[]>(`/api/v1/apartments/agent/${userId}/activity`).then((r) => {
      setActivity(r.ok && Array.isArray(r.data) ? r.data : []);
    });
  }, [userId]);

  if (activity === null) return <Spinner />;
  if (activity.length === 0) return <Empty>{t("noActivity")}</Empty>;
  return (
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
  );
}

export function AgentDetailScreen({ userId, agentName }: { userId: number; agentName: string }) {
  const { t } = useApp();
  const [tab, setTab] = useState<"added" | "sold" | "activity">("added");

  return (
    <div>
      <div className="text-[15px] font-extrabold mb-2 mx-0.5">{agentName}</div>

      <Segmented
        value={tab}
        onChange={(v) => setTab(v)}
        options={[
          { value: "added", label: t("addedObjects") },
          { value: "sold", label: t("soldObjects") },
          { value: "activity", label: t("activityTab") },
        ]}
      />

      <div className="mt-2">
        {tab === "added" && <ObjectList params={{ created_by: userId, status: "all" }} />}
        {tab === "sold" && <ObjectList params={{ created_by: userId, status: "sold" }} />}
        {tab === "activity" && <ActivityLog userId={userId} />}
      </div>
    </div>
  );
}
