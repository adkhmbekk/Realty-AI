import React, { useEffect, useState } from "react";
import {
  BarChart3,
  Building2,
  CheckCircle2,
  ChevronRight,
  Clock,
  Coins,
  Handshake,
  KeyRound,
  Layers,
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
import type { ApartmentAnalytics, DealStatusCounts, Timeseries } from "../types";

// Крупные суммы делаем читаемыми: 1 234 567. Дробную часть отбрасываем (комиссии
// удобнее видеть округлённо).
function fmtMoney(n: number): string {
  return Math.round(n || 0).toLocaleString("ru-RU");
}

// Мини-карточка «за месяц»: крупное число + иконка тренда.
function MonthStat({ value, label, tint }: { value: number; label: string; tint: string }) {
  return (
    <div className="flex-1 rounded-xl2 bg-card border border-line shadow-soft p-3.5">
      <div className="flex items-center justify-between">
        <span className={"w-9 h-9 rounded-[11px] flex items-center justify-center " + tint}>
          <TrendingUp size={18} />
        </span>
        <span className="text-[26px] font-extrabold leading-none">{value}</span>
      </div>
      <div className="text-[11.5px] font-semibold text-muted mt-2.5 leading-snug">{label}</div>
    </div>
  );
}

// Кликабельная плитка-счётчик: ведёт к списку соответствующих объектов.
function StatTile({
  value, label, accent, chip, icon, onClick,
}: {
  value: number; label: string; accent: string; chip: string;
  icon: React.ReactNode; onClick: () => void;
}) {
  return (
    <button
      onClick={() => { haptic(); onClick(); }}
      className="text-left rounded-xl2 bg-card border border-line shadow-soft p-3.5 cursor-pointer active:scale-[.98] transition-all duration-200 hover:shadow-lg2 hover:border-primary"
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

// Небольшая некликабельная плитка-счётчик (для CRM / общей базы).
function MiniStat({ value, label, icon, chip }: { value: number | string; label: string; icon: React.ReactNode; chip: string }) {
  return (
    <div className="rounded-xl2 bg-card border border-line shadow-soft p-3.5">
      <div className="flex items-center justify-between">
        <span className={"w-8 h-8 rounded-[10px] flex items-center justify-center " + chip}>{icon}</span>
        <div className="text-[22px] font-extrabold leading-none">{value}</div>
      </div>
      <div className="text-[12px] font-semibold text-muted mt-2">{label}</div>
    </div>
  );
}

// Столбчатый график (без сторонних библиотек).
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

type DealFilter = "all" | "sale" | "rent";
type Metric = "added" | "sold" | "rented";

export function AnalyticsScreen() {
  const { t } = useApp();
  const nav = useNav();
  const [data, setData] = useState<ApartmentAnalytics | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState(false);

  const [deal, setDeal] = useState<DealFilter>("all");
  const [period, setPeriod] = useState<"week" | "month" | "halfyear" | "year">("month");
  const [metric, setMetric] = useState<Metric>("added");
  const [series, setSeries] = useState<Timeseries | null>(null);

  useEffect(() => {
    api<ApartmentAnalytics>("/api/v1/apartments/analytics").then((r) => {
      setLoading(false);
      if (r.ok && r.data) setData(r.data);
      else setLoadError(true);
    });
  }, []);

  useEffect(() => {
    api<Timeseries>("/api/v1/apartments/timeseries?period=" + period).then((r) => {
      if (r.ok && r.data) setSeries(r.data);
    });
  }, [period]);

  if (loading) return <Spinner />;
  if (loadError) return <Empty icon={<BarChart3 size={24} />}>{t("loadFailed")}</Empty>;
  if (!data) return <Empty icon={<BarChart3 size={24} />}>{t("noAnalytics")}</Empty>;

  // Текущие счётчики с учётом фильтра «Все / Продажа / Аренда».
  const cur: DealStatusCounts =
    deal === "sale" ? data.by_deal.sale
    : deal === "rent" ? data.by_deal.rent
    : { active: data.active, deposit: data.deposit, sold: data.sold, rented: data.rented, total: data.total };

  const closed = deal === "sale" ? cur.sold : deal === "rent" ? cur.rented : cur.sold + cur.rented;
  const conversion = cur.total > 0 ? Math.round((closed / cur.total) * 100) : 0;

  const maxAgent = Math.max(1, ...data.agents.map((a) => a.total));
  const openList = (status: string, titleKey: string) =>
    nav.push({ name: "objectList", params: { status }, titleKey });

  const chartData = (series?.buckets || []).map((b) => ({
    label: b.label,
    value: metric === "added" ? b.added : metric === "sold" ? b.sold : b.rented,
  }));
  const chartColor = metric === "added" ? "#4f46e5" : metric === "sold" ? "#10b981" : "#0ea5e9";

  // Источники: показываем известные типы в фиксированном порядке.
  const srcOrder: { key: string; label: string }[] = [
    { key: "manual", label: t("srcManual") },
    { key: "link", label: t("srcLink") },
    { key: "bulk", label: t("srcChannel") },
    { key: "other", label: t("srcOther") },
  ];
  const srcRows = srcOrder.map((s) => ({ ...s, value: data.sources[s.key] || 0 })).filter((s) => s.value > 0);
  const srcMax = Math.max(1, ...srcRows.map((s) => s.value));

  return (
    <div>
      {/* Фильтр по типу сделки — пересчитывает обзор/конверсию */}
      <Segmented<DealFilter>
        value={deal}
        onChange={setDeal}
        options={[
          { value: "all", label: t("dealAll") },
          { value: "sale", label: t("dealSale") },
          { value: "rent", label: t("dealRent") },
        ]}
      />

      {/* «За месяц» */}
      <div className="flex gap-2.5 mt-3">
        <MonthStat value={data.added_this_month} label={`${t("colAdded")} · ${t("thisMonth")}`} tint="text-primary bg-primary-soft" />
        <MonthStat value={data.sold_this_month} label={`${t("colSold")} · ${t("thisMonth")}`} tint="text-emerald-600 dark:text-emerald-400 bg-emerald-500/12" />
        <MonthStat value={data.rented_this_month} label={`${t("colRented")} · ${t("thisMonth")}`} tint="text-sky-600 dark:text-sky-400 bg-sky-500/12" />
      </div>

      {/* Обзор по статусам */}
      <SectionTitle>{t("overview")}</SectionTitle>
      <div className="grid grid-cols-2 gap-2.5">
        <StatTile value={cur.total} label={t("objectsTotal")} accent="text-primary" chip="bg-primary-soft text-primary" icon={<Building2 size={16} />} onClick={() => openList("all", "objectsTotal")} />
        <StatTile value={cur.active} label={t("statusActive")} accent="text-emerald-600 dark:text-emerald-400" chip="bg-emerald-500/12 text-emerald-600 dark:text-emerald-400" icon={<CheckCircle2 size={16} />} onClick={() => openList("active", "statusActive")} />
        <StatTile value={cur.deposit} label={t("statusDeposit")} accent="text-amber-600 dark:text-amber-400" chip="bg-amber-500/12 text-amber-600 dark:text-amber-400" icon={<Clock size={16} />} onClick={() => openList("deposit", "statusDeposit")} />
        {deal !== "rent" && (
          <StatTile value={cur.sold} label={t("statusSold")} accent="text-text" chip="bg-slate-500/12 text-slate-600 dark:text-slate-300" icon={<Tag size={16} />} onClick={() => openList("sold", "statusSold")} />
        )}
        {deal !== "sale" && (
          <StatTile value={cur.rented} label={t("statusRented")} accent="text-sky-600 dark:text-sky-400" chip="bg-sky-500/12 text-sky-600 dark:text-sky-400" icon={<KeyRound size={16} />} onClick={() => openList("rented", "statusRented")} />
        )}
      </div>

      {/* Конверсия: закрыто / всего */}
      <Card className="mt-2.5">
        <div className="flex items-center justify-between">
          <span className="text-[13px] font-bold text-muted">{t("conversion")}</span>
          <span className="text-[20px] font-extrabold text-emerald-600 dark:text-emerald-400">{conversion}%</span>
        </div>
        <div className="mt-2 h-[8px] rounded-full bg-[var(--soft)] overflow-hidden">
          <div className="h-full rounded-full bg-gradient-to-r from-emerald-500 to-emerald-400 transition-all duration-500" style={{ width: `${conversion}%` }} />
        </div>
        <div className="text-[11.5px] text-muted mt-1.5">{closed} / {cur.total} · {t("closedDeals")}</div>
      </Card>

      {/* Деньги по сделкам (по валютам) */}
      {(data.revenue.length > 0 || data.crm.deals_won > 0) && (
        <>
          <SectionTitle>{t("moneyTitle")}</SectionTitle>
          <Card>
            {data.revenue.length === 0 ? (
              <div className="text-[13px] text-muted">{t("noAnalytics")}</div>
            ) : (
              <div className="space-y-2">
                {data.revenue.map((r) => (
                  <div key={r.currency} className="flex items-center justify-between gap-2">
                    <span className="inline-flex items-center gap-2 min-w-0">
                      <span className="w-8 h-8 rounded-[10px] bg-amber-500/12 text-amber-600 dark:text-amber-400 flex items-center justify-center shrink-0"><Coins size={16} /></span>
                      <span className="min-w-0">
                        <span className="block text-[14px] font-extrabold">{fmtMoney(r.commission)} {r.currency}</span>
                        <span className="block text-[11.5px] text-muted">{t("commission")} · {r.count} {t("closedDeals").toLowerCase()}</span>
                      </span>
                    </span>
                    <span className="text-[12px] text-muted shrink-0">{t("dealVolume")}: {fmtMoney(r.amount)}</span>
                  </div>
                ))}
              </div>
            )}
          </Card>
        </>
      )}

      {/* Источники объектов */}
      {srcRows.length > 0 && (
        <>
          <SectionTitle>{t("sourcesTitle")}</SectionTitle>
          <Card>
            <div className="space-y-2.5">
              {srcRows.map((s) => (
                <div key={s.key}>
                  <div className="flex items-center justify-between text-[12.5px] mb-1">
                    <span className="font-bold">{s.label}</span>
                    <span className="text-muted"><b className="text-text">{s.value}</b></span>
                  </div>
                  <div className="h-[6px] rounded-full bg-[var(--soft)] overflow-hidden">
                    <div className="h-full rounded-full transition-all duration-500" style={{ width: `${Math.round((s.value / srcMax) * 100)}%`, background: "var(--grad)" }} />
                  </div>
                </div>
              ))}
            </div>
          </Card>
        </>
      )}

      {/* Общая база + CRM */}
      <SectionTitle>{t("crmTitle")}</SectionTitle>
      <div className="grid grid-cols-2 gap-2.5">
        <MiniStat value={data.crm.clients} label={t("crmClients")} icon={<Users size={16} />} chip="bg-primary-soft text-primary" />
        <MiniStat value={data.crm.in_search} label={t("crmInSearch")} icon={<BarChart3 size={16} />} chip="bg-indigo-500/12 text-indigo-600 dark:text-indigo-400" />
        <MiniStat value={data.crm.deals_active} label={t("dealsActive")} icon={<Handshake size={16} />} chip="bg-amber-500/12 text-amber-600 dark:text-amber-400" />
        <MiniStat value={data.crm.deals_won} label={t("dealsWon")} icon={<Trophy size={16} />} chip="bg-emerald-500/12 text-emerald-600 dark:text-emerald-400" />
        <MiniStat value={data.shared_mls} label={t("mlsSharedTitle")} icon={<Layers size={16} />} chip="bg-sky-500/12 text-sky-600 dark:text-sky-400" />
      </div>

      {/* График динамики */}
      <SectionTitle>{t("dynamics")}</SectionTitle>
      <Card>
        <Segmented<Metric>
          value={metric}
          onChange={setMetric}
          options={[
            { value: "added", label: t("colAdded") },
            { value: "sold", label: t("colSold") },
            { value: "rented", label: t("colRented") },
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
          {chartData.length === 0 ? <Empty>{t("noAnalytics")}</Empty> : <BarChart data={chartData} color={chartColor} />}
        </div>
      </Card>

      {/* Активность сотрудников */}
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
              onClick={() => { if (a.user_id == null) return; haptic(); nav.push({ name: "agentDetail", userId: a.user_id, agentName: name }); }}
              className="w-full text-left mt-2 rounded-xl2 bg-card border border-line shadow-soft p-3.5 cursor-pointer active:scale-[.99] transition-all duration-200 hover:shadow-lg2 hover:border-primary"
            >
              <div className="flex items-center gap-3">
                <span
                  className={"relative w-9 h-9 shrink-0 rounded-xl flex items-center justify-center text-[13px] font-extrabold " + (top ? "text-white" : "bg-primary-soft text-primary")}
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
                    <span className="text-[12.5px] text-muted shrink-0 flex items-center gap-1">
                      {t("colAdded")}: <b className="text-text">{a.total}</b> · {t("colSold")}: <b className="text-emerald-600 dark:text-emerald-400">{a.sold}</b> · {t("colRented")}: <b className="text-sky-600 dark:text-sky-400">{a.rented}</b>
                      <ChevronRight size={15} className="opacity-50" />
                    </span>
                  </div>
                  <div className="mt-2 h-[6px] rounded-full bg-[var(--soft)] overflow-hidden">
                    <div className="h-full rounded-full transition-all duration-500" style={{ width: `${Math.round((a.total / maxAgent) * 100)}%`, background: "var(--grad)" }} />
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
