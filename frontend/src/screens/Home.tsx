import React, { useEffect, useState } from "react";
import { BarChart3, ChevronRight, Database, Layers, Mail, Plus, Search, Settings as SettingsIcon, User, Users } from "lucide-react";
import { useApp } from "../store";
import { useNav, Route } from "../nav";
import { api } from "../api";
import { Card } from "../components/ui";
import type { ApartmentStats, ClientStats } from "../types";
import { initials } from "../utils";
import { haptic } from "../telegram";

function Hero() {
  const { t, L, user, settings } = useApp();
  const role = user?.role;
  let bigName = user?.full_name || (user?.username ? "@" + user.username : t("notSet"));
  let sub = L.roleLabel(role, user?.is_owner);
  if (role === "agency_admin" && settings?.project_name) {
    sub = user?.full_name ? `${L.roleLabel(role, user?.is_owner)} · ${user.full_name}` : L.roleLabel(role, user?.is_owner);
    bigName = settings.project_name;
  }
  return (
    <div
      className="relative w-full overflow-hidden rounded-xl3 p-5 mb-4 text-white"
      style={{
        background: "var(--grad-hero)",
        boxShadow: "0 20px 46px rgba(52,31,163,.4)",
      }}
    >
      <div className="absolute -right-12 -top-16 w-52 h-52 rounded-full" style={{ background: "radial-gradient(circle, rgba(255,255,255,.2), transparent 65%)" }} />
      <div className="absolute -left-8 -bottom-20 w-52 h-52 rounded-full" style={{ background: "radial-gradient(circle, rgba(165,180,252,.26), transparent 66%)" }} />
      <div className="relative flex items-center gap-4">
        <div className="w-14 h-14 shrink-0 rounded-2xl bg-white/20 border border-white/40 flex items-center justify-center text-xl font-extrabold backdrop-blur">
          {initials(user?.full_name || settings?.project_name) || <User size={24} />}
        </div>
        <div className="min-w-0">
          <div className="text-[12px] opacity-90">{t("greeting")}</div>
          <div className="text-[22px] font-extrabold leading-tight truncate">{bigName}</div>
          <div className="text-[12.5px] opacity-90 mt-0.5">{sub}</div>
        </div>
      </div>
    </div>
  );
}

// Одна «база» на главной: заголовок + активные (крупно, в приоритете), в задатке
// и проданные. Клик по карточке открывает соответствующую базу.
function BaseCard({
  title,
  icon,
  stats,
  onOpen,
}: {
  title: string;
  icon: React.ReactNode;
  stats: ApartmentStats;
  onOpen: () => void;
}) {
  const { t } = useApp();
  return (
    <button
      onClick={() => {
        haptic();
        onOpen();
      }}
      className="w-full text-left rounded-xl2 bg-card border border-line shadow-soft p-3 transition active:scale-[.98] hover:shadow-lg2 flex flex-col"
    >
      <div className="flex items-center gap-2 mb-2.5">
        <span className="w-8 h-8 rounded-lg bg-primary-soft text-primary flex items-center justify-center shrink-0">{icon}</span>
        <span className="text-[12.5px] font-extrabold leading-tight flex-1 min-w-0">{title}</span>
      </div>
      {/* «Активные» крупно и в приоритете; депозит и продано — компактными плитками
          ниже, чтобы обе карточки («Своя база» и «Общая база MLS») влезли в ряд. */}
      <div className="rounded-xl p-2.5 bg-emerald-50 dark:bg-emerald-500/10 mb-1.5">
        <div className="text-[26px] font-extrabold leading-none text-emerald-600 dark:text-emerald-400">{stats.active}</div>
        <div className="text-[11px] font-bold text-muted mt-1">{t("statusActive")}</div>
      </div>
      <div className="flex gap-1.5">
        <div className="flex-1 rounded-xl p-2 bg-[var(--soft)]">
          <div className="text-[16px] font-extrabold leading-none text-amber-600 dark:text-amber-400">{stats.deposit}</div>
          <div className="text-[10.5px] font-semibold text-muted mt-0.5 leading-tight">{t("statusDeposit")}</div>
        </div>
        <div className="flex-1 rounded-xl p-2 bg-[var(--soft)]">
          <div className="text-[16px] font-extrabold leading-none text-text">{stats.sold}</div>
          <div className="text-[10.5px] font-semibold text-muted mt-0.5 leading-tight">{t("statusSold")}</div>
        </div>
      </div>
    </button>
  );
}

// Две базы на главной вместо голой статистики: своя база агентства и общая база
// MLS (открыта всем агентствам). Активные — в приоритете, крупнее.
function Bases() {
  const { t } = useApp();
  const nav = useNav();
  const [own, setOwn] = useState<ApartmentStats | null>(null);
  const [mls, setMls] = useState<ApartmentStats | null>(null);
  useEffect(() => {
    api<ApartmentStats>("/api/v1/apartments/stats").then((r) => {
      if (r.ok && r.data) setOwn(r.data);
    });
    api<ApartmentStats>("/api/v1/mls/stats").then((r) => {
      if (r.ok && r.data) setMls(r.data);
    });
  }, []);
  if (!own) return null;
  // Своя база и общая пусты → дружелюбный онбординг «добавьте первый объект».
  if (own.total === 0 && (!mls || mls.total === 0)) {
    return (
      <button
        onClick={() => {
          haptic();
          nav.push({ name: "addObject" });
        }}
        className="w-full text-left rounded-xl2 bg-card border border-line shadow-soft p-5 mb-4 transition active:scale-[.99] hover:shadow-lg2 animate-fade-up"
      >
        <div className="flex items-center gap-3.5">
          <span className="w-12 h-12 shrink-0 rounded-2xl flex items-center justify-center text-white shadow-glow" style={{ background: "var(--grad)" }}>
            <Plus size={24} />
          </span>
          <div className="min-w-0">
            <div className="text-[16px] font-extrabold">{t("emptyDbTitle")}</div>
            <div className="text-[13px] text-muted mt-0.5 leading-relaxed">{t("emptyDbText")}</div>
          </div>
        </div>
      </button>
    );
  }
  return (
    <div className="mb-4 grid grid-cols-2 gap-2.5 items-stretch">
      <BaseCard title={t("ownBaseTitle")} icon={<Database size={18} />} stats={own} onOpen={() => nav.push({ name: "database" })} />
      <BaseCard
        title={t("mlsBaseTitle")}
        icon={<Layers size={18} />}
        stats={mls || { active: 0, deposit: 0, sold: 0, total: 0 }}
        onOpen={() => nav.push({ name: "mlsBrowse" })}
      />
    </div>
  );
}

// Единый блок «Клиенты»: заголовок‑кнопка (переход к клиентам) + сводка ВНУТРИ
// (клиенты · в поиске · сделки · продано) + значок новых совпадений. Всё в одной
// кнопке: кликнув по ней, попадаешь в клиентскую базу.
function ClientsCard() {
  const { t } = useApp();
  const nav = useNav();
  const [s, setS] = useState<ClientStats | null>(null);
  const [newCount, setNewCount] = useState(0);
  useEffect(() => {
    api<ClientStats>("/api/v1/clients/stats").then((r) => {
      if (r.ok && r.data) setS(r.data);
    });
    api<{ new_count: number }>("/api/v1/clients/matches/summary").then((r) => {
      if (r.ok && r.data) setNewCount(r.data.new_count);
    });
  }, []);
  const hot = newCount > 0;
  const hasStats = !!s && (s.clients > 0 || s.deals_active > 0 || s.deals_won > 0);
  const tiles = s
    ? [
        { key: "clients", labelKey: "cstat_clients", count: s.clients },
        { key: "in_search", labelKey: "cstat_in_search", count: s.in_search },
        { key: "deals_active", labelKey: "cstat_deals_active", count: s.deals_active },
        { key: "deals_won", labelKey: "cstat_deals_won", count: s.deals_won },
      ]
    : [];
  return (
    <button
      onClick={() => {
        haptic();
        nav.push({ name: "clients" });
      }}
      className={
        "w-full text-left rounded-xl2 border p-4 mb-4 transition active:scale-[.99] " +
        (hot ? "text-white shadow-glow border-transparent" : "bg-card border-line shadow-soft hover:shadow-lg2")
      }
      style={hot ? { background: "var(--grad)" } : undefined}
    >
      <div className="flex items-center gap-3">
        <span className={"w-12 h-12 rounded-2xl flex items-center justify-center shrink-0 " + (hot ? "bg-white/20" : "bg-primary-soft text-primary")}>
          <Users size={24} />
        </span>
        <div className="min-w-0 flex-1">
          <div className="text-[16px] font-extrabold">{t("clientsTitle")}</div>
          <div className={"text-[13px] mt-0.5 " + (hot ? "opacity-90" : "text-muted")}>
            {hot ? t("newMatchesN").replace("{n}", String(newCount)) : t("clientsHomeSub")}
          </div>
        </div>
        {hot ? (
          <span className="shrink-0 min-w-[26px] h-[26px] px-1.5 rounded-full bg-white/25 text-white text-[13px] font-extrabold flex items-center justify-center">
            {newCount}
          </span>
        ) : (
          <ChevronRight size={18} className="text-muted shrink-0" />
        )}
      </div>
      {hasStats && (
        <div className={"grid grid-cols-4 gap-2 mt-3 pt-3 border-t " + (hot ? "border-white/25" : "border-line")}>
          {tiles.map((tl) => (
            <div key={tl.key} className="text-center">
              <div className={"text-[20px] font-extrabold leading-none " + (hot ? "text-white" : "text-text")}>{tl.count}</div>
              <div className={"text-[10px] font-semibold mt-1 leading-tight " + (hot ? "opacity-90" : "text-muted")}>{t(tl.labelKey)}</div>
            </div>
          ))}
        </div>
      )}
    </button>
  );
}

function QuickAction({ icon, label, onClick }: { icon: React.ReactNode; label: string; onClick: () => void }) {
  return (
    <button
      onClick={() => {
        haptic();
        onClick();
      }}
      className="flex flex-col items-center gap-2 rounded-2xl bg-card border border-line shadow-soft py-3.5 px-1.5 transition active:scale-95 hover:shadow-lg2"
    >
      <span className="w-11 h-11 rounded-[13px] bg-primary-soft text-primary flex items-center justify-center">{icon}</span>
      <span className="text-[11.5px] font-bold text-muted text-center leading-tight">{label}</span>
    </button>
  );
}

export function HomeScreen() {
  const { t, user } = useApp();
  const nav = useNav();
  const role = user?.role;
  const go = (r: Route) => nav.push(r);

  const add = { icon: <Plus size={21} />, label: t("addObject"), route: { name: "addObject" } as Route };
  const search = { icon: <Search size={21} />, label: t("findObject"), route: { name: "search" } as Route };
  const team = { icon: <Users size={21} />, label: t("team"), route: { name: "team" } as Route };
  const invites = { icon: <Mail size={21} />, label: t("invites"), route: { name: "invites" } as Route };
  const settings = { icon: <SettingsIcon size={21} />, label: t("settings"), route: { name: "settings" } as Route };
  const analytics = { icon: <BarChart3 size={21} />, label: t("analytics"), route: { name: "analytics" } as Route };

  // Быстрые действия НЕ дублируют нижнюю панель (там уже есть «Добавить» и «Найти»).
  // Главный админ: аналитика, команда, приглашения, настройки (4).
  // Обычный админ: аналитика, команда, приглашения, настройки (4) — может звать агентов.
  // Агент: добавить, найти, настройки (3).
  let actions: { icon: React.ReactNode; label: string; route: Route }[];
  if (role === "agency_admin") {
    actions = [analytics, team, invites, settings];
  } else {
    actions = [add, search, settings];
  }

  return (
    <div>
      <Hero />
      <Bases />
      <ClientsCard />
      <div className="flex items-center justify-between mt-1 mx-0.5 mb-2.5">
        <span className="text-[14px] font-extrabold tracking-tight">{t("quickActions")}</span>
      </div>
      <div className={"grid gap-2.5 " + (actions.length === 3 ? "grid-cols-3" : "grid-cols-4")}>
        {actions.map((a, i) => (
          <QuickAction key={i} icon={a.icon} label={a.label} onClick={() => go(a.route)} />
        ))}
      </div>
    </div>
  );
}
