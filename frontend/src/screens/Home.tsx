import React, { useEffect, useState } from "react";
import { BarChart3, Mail, Plus, Search, Settings as SettingsIcon, User, Users } from "lucide-react";
import { useApp } from "../store";
import { useNav, Route } from "../nav";
import { api } from "../api";
import { Card } from "../components/ui";
import type { ApartmentStats } from "../types";
import { initials } from "../utils";
import { haptic } from "../telegram";

function Hero() {
  const { t, L, user, settings } = useApp();
  const nav = useNav();
  const role = user?.role;
  let bigName = user?.full_name || (user?.username ? "@" + user.username : t("notSet"));
  let sub = L.roleLabel(role, user?.is_owner);
  if (role === "agency_admin" && settings?.project_name) {
    sub = user?.full_name ? `${L.roleLabel(role, user?.is_owner)} · ${user.full_name}` : L.roleLabel(role, user?.is_owner);
    bigName = settings.project_name;
  }
  return (
    <button
      onClick={() => {
        haptic();
        nav.push({ name: "profile" });
      }}
      className="relative w-full text-left overflow-hidden rounded-xl3 p-5 mb-4 text-white active:scale-[.99] transition"
      style={{
        background: "var(--grad-hero)",
        boxShadow: "inset 0 1px 0 rgba(255,255,255,.16), 0 20px 46px rgba(52,31,163,.4)",
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
    </button>
  );
}

function Stats() {
  const { t } = useApp();
  const nav = useNav();
  const [s, setS] = useState<ApartmentStats | null>(null);
  useEffect(() => {
    api<ApartmentStats>("/api/v1/apartments/stats").then((r) => {
      if (r.ok && r.data) setS(r.data);
    });
  }, []);
  if (!s) return null;
  // Первое впечатление нового пользователя: база пуста → дружелюбный
  // онбординг с призывом добавить первый объект (вместо нулевой статистики).
  if (s.total === 0) {
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
  const max = Math.max(1, s.active, s.deposit, s.sold);
  const tiles: { status: string; labelKey: string; count: number; bar: string; num: string }[] = [
    { status: "active", labelKey: "statusActive", count: s.active, bar: "from-emerald-500 to-emerald-400", num: "text-emerald-600 dark:text-emerald-400" },
    { status: "deposit", labelKey: "statusDeposit", count: s.deposit, bar: "from-amber-500 to-amber-400", num: "text-amber-600 dark:text-amber-400" },
    { status: "sold", labelKey: "statusSold", count: s.sold, bar: "from-slate-400 to-slate-300", num: "text-text" },
  ];
  return (
    <div className="mb-4">
      <div className="flex items-center justify-between mt-1 mx-0.5 mb-2.5">
        <span className="text-[14px] font-extrabold tracking-tight">{t("stats")}</span>
        <button className="text-[13px] font-bold text-primary" onClick={() => nav.push({ name: "database" })}>
          {t("myDatabase")} ›
        </button>
      </div>
      <div className="grid grid-cols-3 gap-2.5">
        {tiles.map((tl) => (
          <button
            key={tl.status}
            onClick={() => {
              haptic();
              nav.push({ name: "objectList", params: { status: tl.status }, titleKey: tl.labelKey });
            }}
            className="text-left rounded-xl2 bg-card border border-line shadow-soft p-3.5 transition active:scale-95 hover:shadow-lg2"
          >
            <div className={"text-[26px] font-extrabold leading-none " + tl.num}>{tl.count}</div>
            <div className="text-[12px] font-semibold text-muted mt-1">{t(tl.labelKey)}</div>
            <div className="mt-2 h-[5px] rounded-full bg-[var(--soft)] overflow-hidden">
              <div className={"h-full rounded-full bg-gradient-to-r " + tl.bar} style={{ width: `${Math.round((tl.count / max) * 100)}%` }} />
            </div>
          </button>
        ))}
      </div>
    </div>
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
      <Stats />
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
