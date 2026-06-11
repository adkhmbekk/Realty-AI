import React, { useEffect, useState } from "react";
import {
  BarChart3,
  Building2,
  CheckCircle2,
  ChevronRight,
  Clock,
  Tag,
  Trophy,
  TrendingUp,
  Users,
} from "lucide-react";
import { useApp } from "../store";
import { useNav } from "../nav";
import { api } from "../api";
import { Card, Empty, Segmented, Spinner } from "../components/ui";
import { haptic } from "../telegram";
import { initials } from "../utils";
import type { ApartmentAnalytics, Timeseries } from "../types";

// Мини-карточка «за месяц»: крупное число + иконка тренда. Surface'ит данные
// added_this_month / sold_this_month, которые раньше нигде не показывались.
function MonthStat({
  value,
  label,
  tint,
}: {
  value: number;
  label: string;
  tint: "primary" | "emerald";
}) {
  const styles =
    tint === "primary"
      ? "text-primary bg-primary-soft"
      : "text-emerald-600 dark:text-emerald-400 bg-emerald-500/12";
  return (
    <div className="flex-1 rounded-xl2 bg-card border border-line shadow-soft p-3.5">
      <div className="flex items-center justify-between">
        <span className={"w-9 h-9 rounded-[11px] flex items-center justify-center " + styles}>
          <TrendingUp size={18} />
        </span>
        <span className="text-[28px] font-extrabold leading-none">{value}</span>
      </div>
      <div className="text-[12px] font-semibold text-muted mt-2.5">{label}</div>
    </div>
  );
}

// Кликабельная плитка-счётчик: ведёт к списку соответствующих объектов.
function StatTile({
  value,
  label,
  accent,
  chip,
  icon,
  onClick,
}: {
  value: number;
  label: string;
  accent: string;
  chip: string;
  icon: React.ReactNode;
  onClick: () => void;
}) {
  return (
    <button
      onClick={() => {
        haptic();
        onClick();
      }}
      className="text-left rounded-xl2 bg-card border border-line shadow-soft p-3.5 cursor-pointer active:scale-[.98] transition-all duration-200 hover:shadow-lg2 hover:border-primary/30"
    >
      <div className="flex items-center justify-between">
        <span className={"w-8 h-8 rounded-[10px] flex items-center justify-center " + chip}>{icon}</span>
        <div className={"text-[26px] font-extrabold leading-none " + accent}>{value}</div>
      </div>
      <div className="text-[12px] font-semibold text-muted mt-2 flex items-center gap-0.5">
        {label} <ChevronRight size={13} className="opacity-50" />
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
        {data.map((d, i) => {
          const peak = d.value === max && d.value > 0;
          return (
            <div
              key={i}
              className={"flex flex-col items-center " + (scroll ? "shrink-0" : "flex-1 min-w-0")}
              style={scroll ? { width: 26 } : undefined}
            >
              <div className={"text-[9px] mb-0.5 h-3 leading-none font-bold " + (peak ? "text-text" : "text-muted")}>
                {d.value || ""}
              </div>
              {/* Полупрозрачная «дорожка» позади столбца — видно полную высоту. */}
              <div className="w-full h-32 flex items-end rounded-md bg-[var(--soft)]/60 overflow-hidden">
                <div
                  className="w-full rounded-t-md transition-all duration-300"
                  style={{
                    height: `${(d.value / max) * 100}%`,
                    background: `linear-gradient(180deg, ${color}, ${color}b3)`,
                    minHeight: d.value > 0 ? 4 : 0,
                    opacity: peak ? 1 : 0.82,
                  }}
                  title={`${d.label}: ${d.value}`}
                />
              </div>
              <div className="text-[9px] text-muted mt-1 whitespace-nowrap overflow-hidden text-ellipsis max-w-full">
                {d.label}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

function SectionTitle({ children }: { children: React.ReactNode }) {
  return (
    <div className="text-[13px] font-extrabold uppercase tracking-wider text-muted mx-0.5 mt-5 mb-2">
      {children}
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
  if (!data) return <Empty icon={<BarChart3 size={24} />}>{t("noAnalytics")}</Empty>;

  const maxAgent = Math.max(1, ...data.agents.map((a) => a.total));
  const conversion = data.total > 0 ? Math.round((data.sold / data.total) * 100) : 0;
  const openList = (status: string, titleKey: string) =>
    nav.push({ name: "objectList", params: { status }, titleKey });

  const chartData = (series?.buckets || []).map((b) => ({
    label: b.label,
    value: metric === "added" ? b.added : b.sold,
  }));

  return (
    <div>
      {/* «За месяц» — прежде скрытые данные added_this_month / sold_this_month */}
      <div className="flex gap-2.5">
        <MonthStat value={data.added_this_month} label={`${t("colAdded")} · ${t("thisMonth")}`} tint="primary" />
        <MonthStat value={data.sold_this_month} label={`${t("colSold")} · ${t("thisMonth")}`} tint="emerald" />
      </div>

      {/* Обзор: кликабельные счётчики → списки объектов */}
      <SectionTitle>{t("overview")}</SectionTitle>
      <div className="grid grid-cols-2 gap-2.5">
        <StatTile
          value={data.total}
          label={t("objectsTotal")}
          accent="text-primary"
          chip="bg-primary-soft text-primary"
          icon={<Building2 size={16} />}
          onClick={() => openList("all", "objectsTotal")}
        />
        <StatTile
          value={data.active}
          label={t("statusActive")}
          accent="text-emerald-600 dark:text-emerald-400"
          chip="bg-emerald-500/12 text-emerald-600 dark:text-emerald-400"
          icon={<CheckCircle2 size={16} />}
          onClick={() => openList("active", "statusActive")}
        />
        <StatTile
          value={data.deposit}
          label={t("statusDeposit")}
          accent="text-amber-600 dark:text-amber-400"
          chip="bg-amber-500/12 text-amber-600 dark:text-amber-400"
          icon={<Clock size={16} />}
          onClick={() => openList("deposit", "statusDeposit")}
        />
        <StatTile
          value={data.sold}
          label={t("statusSold")}
          accent="text-text"
          chip="bg-slate-500/12 text-slate-600 dark:text-slate-300"
          icon={<Tag size={16} />}
          onClick={() => openList("sold", "statusSold")}
        />
      </div>

      {/* Конверсия: доля проданных от общего */}
      <Card className="mt-2.5">
        <div className="flex items-center justify-between">
          <span className="text-[13px] font-bold text-muted">{t("conversion")}</span>
          <span className="text-[20px] font-extrabold text-emerald-600 dark:text-emerald-400">{conversion}%</span>
        </div>
        <div className="mt-2 h-[8px] rounded-full bg-[var(--soft)] overflow-hidden">
          <div
            className="h-full rounded-full bg-gradient-to-r from-emerald-500 to-emerald-400 transition-all duration-500"
            style={{ width: `${conversion}%` }}
          />
        </div>
        <div className="text-[11.5px] text-muted mt-1.5">
          {data.sold} / {data.total} · {t("statusSold")}
        </div>
      </Card>

      {/* График добавлено/продано с выбором периода */}
      <SectionTitle>{t("dynamics")}</SectionTitle>
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
            <BarChart data={chartData} color={metric === "added" ? "#4f46e5" : "#10b981"} />
          )}
        </div>
      </Card>

      {/* Активность сотрудников (тап → детальный экран) */}
      <SectionTitle>{t("agentsActivity")}</SectionTitle>
      {data.agents.length === 0 ? (
        <Empty icon={<Users size={24} />}>{t("noAnalytics")}</Empty>
      ) : (
        data.agents.map((a, i) => {
          const name = a.name || t("notSet");
          const top = i === 0 && a.total > 0;
          return (
            <button
              key={i}
              onClick={() => {
                if (a.user_id == null) return;
                haptic();
                nav.push({ name: "agentDetail", userId: a.user_id, agentName: name });
              }}
              className="w-full text-left mt-2 rounded-xl2 bg-card border border-line shadow-soft p-3.5 cursor-pointer active:scale-[.99] transition-all duration-200 hover:shadow-lg2 hover:border-primary/30"
            >
              <div className="flex items-center gap-3">
                {/* Аватар с инициалами; #1 получает рамку-акцент. */}
                <span
                  className={
                    "relative w-9 h-9 shrink-0 rounded-xl flex items-center justify-center text-[13px] font-extrabold " +
                    (top
                      ? "text-white"
                      : "bg-primary-soft text-primary")
                  }
                  style={top ? { background: "var(--grad)" } : undefined}
                >
                  {initials(name) || "—"}
                  {top && (
                    <span className="absolute -right-1.5 -top-1.5 w-5 h-5 rounded-full bg-amber-400 text-white flex items-center justify-center shadow-soft">
                      <Trophy size={11} />
                    </span>
                  )}
                </span>
                <div className="min-w-0 flex-1">
                  <div className="flex items-center justify-between gap-2">
                    <span className="font-bold truncate">{name}</span>
                    <span className="text-[13px] text-muted shrink-0 flex items-center gap-1">
                      {t("colAdded")}: <b className="text-text">{a.total}</b> · {t("colSold")}:{" "}
                      <b className="text-emerald-600 dark:text-emerald-400">{a.sold}</b>
                      <ChevronRight size={15} className="opacity-50" />
                    </span>
                  </div>
                  <div className="mt-2 h-[6px] rounded-full bg-[var(--soft)] overflow-hidden">
                    <div
                      className="h-full rounded-full transition-all duration-500"
                      style={{ width: `${Math.round((a.total / maxAgent) * 100)}%`, background: "var(--grad)" }}
                    />
                  </div>
                </div>
              </div>
            </button>
          );
        })
      )}
    </div>
  );
}
