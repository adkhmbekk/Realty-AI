import React, { useEffect, useState } from "react";
import { useApp } from "../store";
import { api } from "../api";
import { Card, Empty, Spinner } from "../components/ui";
import type { ApartmentAnalytics } from "../types";

// Плитка с крупным числом и подписью.
function Tile({ value, label, accent }: { value: number; label: string; accent: string }) {
  return (
    <div className="rounded-xl2 bg-card border border-line shadow-soft p-3.5">
      <div className={"text-[26px] font-extrabold leading-none " + accent}>{value}</div>
      <div className="text-[12px] font-semibold text-muted mt-1">{label}</div>
    </div>
  );
}

export function AnalyticsScreen() {
  const { t } = useApp();
  const [data, setData] = useState<ApartmentAnalytics | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api<ApartmentAnalytics>("/api/v1/apartments/analytics").then((r) => {
      setLoading(false);
      if (r.ok && r.data) setData(r.data);
    });
  }, []);

  if (loading) return <Spinner />;
  if (!data) return <Empty>{t("noAnalytics")}</Empty>;

  const maxAgent = Math.max(1, ...data.agents.map((a) => a.total));

  return (
    <div>
      {/* Общие счётчики */}
      <div className="grid grid-cols-2 gap-2.5">
        <Tile value={data.total} label={t("objectsTotal")} accent="text-primary" />
        <Tile value={data.active} label={t("statusActive")} accent="text-emerald-600 dark:text-emerald-400" />
        <Tile value={data.deposit} label={t("statusDeposit")} accent="text-amber-600 dark:text-amber-400" />
        <Tile value={data.sold} label={t("statusSold")} accent="text-text" />
      </div>

      {/* За текущий месяц */}
      <div className="grid grid-cols-2 gap-2.5 mt-2.5">
        <Tile value={data.added_this_month} label={t("addedThisMonth")} accent="text-primary" />
        <Tile value={data.sold_this_month} label={t("soldThisMonth")} accent="text-emerald-600 dark:text-emerald-400" />
      </div>

      {/* Активность сотрудников */}
      <div className="text-[13px] font-extrabold uppercase tracking-wider text-muted mx-0.5 mt-5 mb-2">
        {t("agentsActivity")}
      </div>
      {data.agents.length === 0 ? (
        <Empty>{t("noAnalytics")}</Empty>
      ) : (
        data.agents.map((a, i) => (
          <Card key={i} className="mt-2 py-3">
            <div className="flex items-center justify-between gap-2">
              <span className="font-bold truncate">{a.name || t("notSet")}</span>
              <span className="text-[13px] text-muted shrink-0">
                {t("colAdded")}: <b className="text-text">{a.total}</b> · {t("colSold")}:{" "}
                <b className="text-emerald-600 dark:text-emerald-400">{a.sold}</b>
              </span>
            </div>
            <div className="mt-2 h-[6px] rounded-full bg-[var(--soft)] overflow-hidden">
              <div
                className="h-full rounded-full bg-gradient-to-r from-primary to-blue-400"
                style={{ width: `${Math.round((a.total / maxAgent) * 100)}%` }}
              />
            </div>
          </Card>
        ))
      )}
    </div>
  );
}
