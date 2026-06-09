import React, { useEffect, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { User } from "lucide-react";
import { useApp } from "../store";
import { api } from "../api";
import { Card, Empty, Segmented, Spinner, Swipeable } from "../components/ui";
import { fmtDate, initials } from "../utils";
import { haptic } from "../telegram";
import { ObjectList } from "./Apartments";
import type { AgentEvent } from "../types";

// Две вкладки: «Добавленные объекты» (внутри — подвкладки «В работе» / «Проданные»)
// и «Действия» (журнал). «Добавленные» включает ВСЕ объекты сотрудника, поэтому
// они разделены на не проданные (в работе) и проданные — чтобы не путаться.
const TABS = ["added", "activity"] as const;
type Tab = (typeof TABS)[number];

const ACTION_KEY: Record<string, string> = {
  created: "evCreated",
  updated: "evUpdated",
  status: "evStatusChanged",
};

// Журнал последних действий сотрудника.
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
  const loc = lang === "ru" ? "ru-RU" : lang === "uz" ? "uz-UZ" : "en-US";
  const dayLabel = (iso: string) => {
    const d = new Date(iso);
    return isNaN(+d) ? iso : d.toLocaleDateString(loc, { day: "2-digit", month: "long", year: "numeric" });
  };
  const timeOnly = (iso: string) => {
    const d = new Date(iso);
    return isNaN(+d) ? "" : d.toLocaleTimeString(loc, { hour: "2-digit", minute: "2-digit" });
  };
  return (
    <Card className="py-1">
      {activity.map((e, i) => {
        const day = (e.created_at || "").slice(0, 10);
        const prevDay = i > 0 ? (activity[i - 1].created_at || "").slice(0, 10) : null;
        const showHeader = day !== prevDay;
        return (
          <React.Fragment key={i}>
            {showHeader && (
              <div className="text-[11px] font-bold uppercase tracking-wider text-muted pt-3 pb-1 mt-1 border-t border-[var(--border)] first:border-t-0 first:mt-0 first:pt-1.5">
                {dayLabel(e.created_at)}
              </div>
            )}
            <div className="flex items-center justify-between gap-2 py-2 text-sm">
              <span className="font-semibold">
                №{e.display_id}{" "}
                <span className="text-muted font-normal">{t(ACTION_KEY[e.action] || "evUpdated")}</span>
              </span>
              <span className="text-[12px] text-muted shrink-0">{timeOnly(e.created_at)}</span>
            </div>
          </React.Fragment>
        );
      })}
    </Card>
  );
}

// Вкладка «Добавленные объекты» с двумя подвкладками:
//   in_work — добавленные этим сотрудником, но ещё не проданные (status=unsold);
//   sold    — добавленные им и уже проданные (status=sold).
function AddedObjects({ userId }: { userId: number }) {
  const { t } = useApp();
  const subs = ["in_work", "sold", "archived"] as const;
  const [sub, setSub] = useState<(typeof subs)[number]>("in_work");

  // Свайп переключает ТОЛЬКО подвкладки (в работе / проданные / архив).
  function swipeSub(d: 1 | -1) {
    const i = subs.indexOf(sub);
    const n = i + d;
    if (n >= 0 && n < subs.length) {
      haptic();
      setSub(subs[n]);
    }
  }

  const status = sub === "sold" ? "sold" : sub === "archived" ? "archived" : "unsold";

  return (
    <Swipeable onSwipe={swipeSub}>
      <Segmented
        value={sub}
        onChange={(v) => {
          haptic();
          setSub(v);
        }}
        options={[
          { value: "in_work", label: t("agentInWork") },
          { value: "sold", label: t("soldObjects") },
          { value: "archived", label: t("archive") },
        ]}
      />
      <div className="mt-2 relative">
        <AnimatePresence mode="wait" initial={false}>
          <motion.div
            key={sub}
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.16, ease: "easeOut" }}
          >
            <ObjectList params={{ created_by: userId, status }} />
          </motion.div>
        </AnimatePresence>
      </div>
    </Swipeable>
  );
}

export function AgentDetailScreen({ userId, agentName }: { userId: number; agentName: string }) {
  const { t } = useApp();
  const [tab, setTab] = useState<Tab>("added");
  // Направление анимации: 1 — вперёд, -1 — назад.
  const [dir, setDir] = useState(0);

  function goTab(next: Tab) {
    const cur = TABS.indexOf(tab);
    const nx = TABS.indexOf(next);
    if (nx === cur) return;
    setDir(nx > cur ? 1 : -1);
    setTab(next);
  }

  // Внешние вкладки («Добавленные» / «Действия») переключаются ТОЛЬКО нажатием.
  // Свайп работает внутри «Добавленных» и переключает лишь подвкладки.
  return (
    <div className="min-h-[70vh] overflow-x-hidden">
      <div className="flex items-center gap-3 mb-3 mx-0.5">
        <span
          className="w-11 h-11 shrink-0 rounded-xl flex items-center justify-center text-white text-[15px] font-extrabold"
          style={{ background: "var(--grad)" }}
        >
          {initials(agentName) || <User size={20} />}
        </span>
        <div className="text-[17px] font-extrabold truncate">{agentName}</div>
      </div>

      <Segmented
        value={tab}
        onChange={(v) => goTab(v)}
        options={[
          { value: "added", label: t("agentTabAdded") },
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
            {tab === "added" && <AddedObjects userId={userId} />}
            {tab === "activity" && <ActivityLog userId={userId} />}
          </motion.div>
        </AnimatePresence>
      </div>
    </div>
  );
}
