import React, { useEffect, useRef, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { useApp } from "../store";
import { api } from "../api";
import { Card, Empty, Segmented, Spinner } from "../components/ui";
import { fmtDate } from "../utils";
import { haptic } from "../telegram";
import { ObjectList } from "./Apartments";
import type { AgentEvent } from "../types";

const TABS = ["added", "sold", "activity"] as const;
type Tab = (typeof TABS)[number];

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
  const [tab, setTab] = useState<Tab>("added");
  // Направление анимации: 1 — листаем вперёд (вправо->влево), -1 — назад.
  const [dir, setDir] = useState(0);

  function goTab(next: Tab) {
    const cur = TABS.indexOf(tab);
    const nx = TABS.indexOf(next);
    if (nx === cur) return;
    setDir(nx > cur ? 1 : -1);
    setTab(next);
  }

  // Переключение вкладок свайпом в любом месте экрана (влево — следующая,
  // вправо — предыдущая). Вертикальные жесты (прокрутка) игнорируем.
  const touch = useRef<{ x: number; y: number } | null>(null);
  function onTouchStart(e: React.TouchEvent) {
    const p = e.touches[0];
    touch.current = { x: p.clientX, y: p.clientY };
  }
  function onTouchEnd(e: React.TouchEvent) {
    const s = touch.current;
    touch.current = null;
    if (!s) return;
    const p = e.changedTouches[0];
    const dx = p.clientX - s.x;
    const dy = p.clientY - s.y;
    // Свайп засчитываем, только если он явно горизонтальный и заметный.
    if (Math.abs(dx) < 55 || Math.abs(dx) < Math.abs(dy) * 1.6) return;
    const idx = TABS.indexOf(tab);
    const next = dx < 0 ? idx + 1 : idx - 1;
    if (next >= 0 && next < TABS.length) {
      haptic();
      goTab(TABS[next]);
    }
  }

  return (
    <div onTouchStart={onTouchStart} onTouchEnd={onTouchEnd} className="min-h-[70vh] overflow-x-hidden">
      <div className="text-[15px] font-extrabold mb-2 mx-0.5">{agentName}</div>

      <Segmented
        value={tab}
        onChange={(v) => goTab(v)}
        options={[
          { value: "added", label: t("addedObjects") },
          { value: "sold", label: t("soldObjects") },
          { value: "activity", label: t("activityTab") },
        ]}
      />

      <div className="mt-2 relative">
        <AnimatePresence mode="wait" custom={dir} initial={false}>
          <motion.div
            key={tab}
            custom={dir}
            initial={{ opacity: 0, x: dir === 0 ? 0 : dir * 60 }}
            animate={{ opacity: 1, x: 0 }}
            exit={{ opacity: 0, x: dir * -60 }}
            transition={{ duration: 0.22, ease: "easeOut" }}
          >
            {tab === "added" && <ObjectList params={{ created_by: userId, status: "all" }} />}
            {tab === "sold" && <ObjectList params={{ created_by: userId, status: "sold" }} />}
            {tab === "activity" && <ActivityLog userId={userId} />}
          </motion.div>
        </AnimatePresence>
      </div>
    </div>
  );
}
