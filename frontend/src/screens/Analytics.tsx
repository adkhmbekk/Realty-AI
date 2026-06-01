import React, { useEffect, useState } from "react";
import { ChevronRight } from "lucide-react";
import { useApp } from "../store";
import { useNav } from "../nav";
import { api } from "../api";
import { Card, Empty, Segmented, Spinner } from "../components/ui";
import { haptic } from "../telegram";
import type { ApartmentAnalytics, Timeseries } from "../types";

// Кликабельная плитка-счётчик: ведёт к списку соответствующих объектов.
function StatTile({
  value,
  label,
  accent,
  onClick,
}: {
  value: number;
  label: string;
  accent: string;
  onClick: () => void;
}) {
  return (
    <button
      onClick={() => {
        haptic();
        onClick();
      }}
      className="text-left rounded-xl2 bg-card border border-line shadow-soft p-3.5 active:scale-[.98] transition hover:shadow-lg2"
    >
      <div className={"text-[26px] font-extrabold leading-none " + accent}>{value}</div>
      <div className="text-[12px] font-semibold text-muted mt-1 flex items-center gap-0.5">
        {label} <ChevronRight size={13} className="opacity-60" />
      </div>
    </button>
  );
}

// Столбчатый график (без сторонних библиотек). Каждый период — отдельный
// столбец со своей подписью. Когда столбцов немного (неделя, полгода, год) —
// они растягиваются на всю ширину. Когда много (месяц = 30 дней) — график
// прокручивается по горизонтали, чтобы виден был каждый день.
function BarChart({ data, color }: { data: { label: string; value: number }[]; color: string }) {
  const max = Math.max(1, ...data.map((d) => d.value));
  const scroll = data.length > 14;
  return (
    <div className={scroll ? "overflow-x-auto -mx-1 px-1 pb-1" : ""}>
      <div className="flex items-end gap-1.5" style={scroll ? { minWidth: data.length * 30 } : undefined}>
        {data.map((d, i) => (
          <div
            key={i}
            className={"flex flex-col items-center " + (scroll ? "shrink-0" : "flex-1 min-w-0")}
            style={scroll ? { width: 26 } : undefined}
          >
            <div className="text-[9px] text-muted mb-0.5 h-3 leading-none">{d.value || ""}</div>
            <div className="w-full h-32 flex items-end">
              <div
                className="w-full rounded-t-md transition-all"
                style={{
                  height: `${(d.value / max) * 100}%`,
                  background: color,
                  minHeight: d.value > 0 ? 4 : 0,
                }}
                title={`${d.label}: ${d.value}`}
              />
            </div>
            <div className="text-[9px] text-muted mt-1 whitespace-nowrap overflow-hidden text-ellipsis max-w-full">
              {d.label}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

export function AnalyticsScreen() {
  const { t } = useApp();
  const nav = useNav();
  const [data, setData] = useState<ApartmentAnalytics | null>(null);
  const [loading, setLoading] = useState(true);

  const [period, setPeriod] = useState<"week" | "month" | "halfyear" | "year">("month");
  const [metric, setMetric] = useState<"added" | "sold">("added");
  const [series, setSeries] = useState<Timeseries | null>(null);

  useEffect(() => {
    api<ApartmentAnalytics>("/api/v1/apartments/analytics").then((r) => {
      setLoading(false);
      if (r.ok && r.data) setData(r.data);
    });
  }, []);

  useEffect(() => {
    api<Timeseries>("/api/v1/apartments/timeseries?period=" + period).then((r) => {
      if (r.ok && r.data) setSeries(r.data);
    });
  }, [period]);

  if (loading) return <Spinner />;
  if (!data) return <Empty>{t("noAnalytics")}</Empty>;

  const maxAgent = Math.max(1, ...data.agents.map((a) => a.total));
  const openList = (status: string, titleKey: string) =>
    nav.push({ name: "objectList", params: { status }, titleKey });

  const chartData = (series?.buckets || []).map((b) => ({
    label: b.label,
    value: metric === "added" ? b.added : b.sold,
  }));

  return (
    <div>
      {/* Кликабельные счётчики → списки объектов */}
      <div className="grid grid-cols-2 gap-2.5">
        <StatTile value={data.total} label={t("objectsTotal")} accent="text-primary" onClick={() => openList("all", "objectsTotal")} />
        <StatTile value={data.active} label={t("statusActive")} accent="text-emerald-600 dark:text-emerald-400" onClick={() => openList("active", "statusActive")} />
        <StatTile value={data.deposit} label={t("statusDeposit")} accent="text-amber-600 dark:text-amber-400" onClick={() => openList("deposit", "statusDeposit")} />
        <StatTile value={data.sold} label={t("statusSold")} accent="text-text" onClick={() => openList("sold", "statusSold")} />
      </div>

      {/* График добавлено/продано с выбором периода */}
      <div className="text-[13px] font-extrabold uppercase tracking-wider text-muted mx-0.5 mt-5 mb-2">
        {t("dynamics")}
      </div>
      <Card>
        <Segmented
          value={metric}
          onChange={(v) => setMetric(v)}
          options={[
            { value: "added", label: t("colAdded") },
            { value: "sold", label: t("colSold") },
          ]}
        />
        <div className="mt-2.5">
          <Segmented
            value={period}
            onChange={(v) => setPeriod(v)}
            options={[
              { value: "week", label: t("perWeek") },
              { value: "month", label: t("perMonth") },
              { value: "halfyear", label: t("perHalfYear") },
              { value: "year", label: t("perYear") },
            ]}
          />
        </div>
        <div className="mt-4">
          {chartData.length === 0 ? (
            <Empty>{t("noAnalytics")}</Empty>
          ) : (
            <BarChart data={chartData} color={metric === "added" ? "#2563eb" : "#10b981"} />
          )}
        </div>
      </Card>

      {/* Активность сотрудников (тап → детальный экран) */}
      <div className="text-[13px] font-extrabold uppercase tracking-wider text-muted mx-0.5 mt-5 mb-2">
        {t("agentsActivity")}
      </div>
      {data.agents.length === 0 ? (
        <Empty>{t("noAnalytics")}</Empty>
      ) : (
        data.agents.map((a, i) => (
          <button
            key={i}
            onClick={() => {
              if (a.user_id == null) return;
              haptic();
              nav.push({ name: "agentDetail", userId: a.user_id, agentName: a.name || t("notSet") });
            }}
            className="w-full text-left mt-2 rounded-xl2 bg-card border border-line shadow-soft p-3.5 active:scale-[.99] transition hover:shadow-lg2"
          >
            <div className="flex items-center justify-between gap-2">
              <span className="font-bold truncate">{a.name || t("notSet")}</span>
              <span className="text-[13px] text-muted shrink-0 flex items-center gap-1">
                {t("colAdded")}: <b className="text-text">{a.total}</b> · {t("colSold")}:{" "}
                <b className="text-emerald-600 dark:text-emerald-400">{a.sold}</b>
                <ChevronRight size={15} className="opacity-60" />
              </span>
            </div>
            <div className="mt-2 h-[6px] rounded-full bg-[var(--soft)] overflow-hidden">
              <div
                className="h-full rounded-full bg-gradient-to-r from-primary to-blue-400"
                style={{ width: `${Math.round((a.total / maxAgent) * 100)}%` }}
              />
            </div>
          </button>
        ))
      )}
    </div>
  );
}
