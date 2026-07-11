// Витрина «юзеры прошки» для владельца платформы (Фаза 5, 2026-07).
//
// Самодостаточный экран: список юзеров → карточка (агентства/роли + ЕГО объекты).
// Клиентскую базу НЕ показываем (приватность — так отдаёт и бэкенд). Встройка в
// Superadmin.tsx / нижние вкладки суперадмина делается ОТДЕЛЬНО (со сборкой на pc1).
//
// ВНИМАНИЕ: строки временно локальны (STR) — перенести в i18n.ts при интеграции.
import React, { useCallback, useEffect, useState } from "react";
import { ChevronRight } from "lucide-react";
import { useApp } from "../store";
import { useNav } from "../nav";
import { api } from "../api";
import { Card, Input, Spinner } from "../components/ui";
import { fmtDate } from "../utils";
import type { Apartment } from "../types";

interface PUser {
  id: number;
  telegram_id: number;
  username?: string | null;
  full_name?: string | null;
  first_name?: string | null;
  last_name?: string | null;
  phone?: string | null;
  is_active: boolean;
  last_seen_at?: string | null;
  created_at?: string | null;
  agencies_count: number;
}
interface PUserList {
  items: PUser[];
  total: number;
  limit: number;
  offset: number;
}
interface PUserAgency {
  agency_id: number;
  agency_name: string;
  role: string;
  is_owner: boolean;
}
interface PUserDetail {
  user: PUser;
  agencies: PUserAgency[];
  objects: Apartment[];
  objects_total: number;
}

const STR: Record<string, Record<string, string>> = {
  ru: {
    users: "Юзеры",
    search: "Поиск по имени / номеру",
    empty: "Юзеры не найдены.",
    agencies: "Агентства",
    objects: "Объекты",
    noObjects: "Объектов пока нет.",
    role_admin: "главный админ",
    role_agent: "агент",
    inAgencies: "агентств",
    back: "Назад",
    activity: "Активность",
    online: "В сети",
    lastSeen: "Был(а)",
    memberSince: "В приложении с",
    noAgencies: "Пока не состоит в агентствах.",
  },
  uz: {
    users: "Foydalanuvchilar",
    search: "Ism / raqam boʻyicha qidirish",
    empty: "Foydalanuvchilar topilmadi.",
    agencies: "Agentliklar",
    objects: "Obyektlar",
    noObjects: "Hozircha obyekt yoʻq.",
    role_admin: "bosh admin",
    role_agent: "agent",
    inAgencies: "ta agentlik",
    back: "Orqaga",
    activity: "Faollik",
    online: "Onlayn",
    lastSeen: "Oxirgi faollik",
    memberSince: "Ilovada",
    noAgencies: "Hozircha agentlikda emas.",
  },
  en: {
    users: "Users",
    search: "Search by name / phone",
    empty: "No users found.",
    agencies: "Agencies",
    objects: "Objects",
    noObjects: "No objects yet.",
    role_admin: "main admin",
    role_agent: "agent",
    inAgencies: "agencies",
    back: "Back",
    activity: "Activity",
    online: "Online",
    lastSeen: "Last seen",
    memberSince: "Member since",
    noAgencies: "Not in any agency yet.",
  },
};

function useStr() {
  const { lang } = useApp();
  return STR[lang] || STR.ru;
}

function displayName(u: PUser): string {
  return (
    [u.first_name, u.last_name].filter(Boolean).join(" ") ||
    u.full_name ||
    (u.username ? "@" + u.username : "#" + u.telegram_id)
  );
}

function roleBadge(role: string, isOwner: boolean, s: Record<string, string>) {
  const admin = isOwner || role === "agency_admin";
  return (
    <span
      className={
        "inline-block px-2.5 py-0.5 rounded-full text-[11px] font-extrabold " +
        (admin
          ? "bg-blue-500/15 text-blue-600 dark:text-blue-400"
          : "bg-slate-500/15 text-slate-600 dark:text-slate-300")
      }
    >
      {admin ? s.role_admin : s.role_agent}
    </span>
  );
}

// Онлайн, если «был(а)» менее 5 минут назад (совпадает с heartbeat-логикой).
function isOnline(lastSeen?: string | null): boolean {
  if (!lastSeen) return false;
  const ts = new Date(lastSeen).getTime();
  return !Number.isNaN(ts) && Date.now() - ts < 5 * 60 * 1000;
}

export function PlatformUsersScreen() {
  const s = useStr();
  const { lang } = useApp();
  const nav = useNav();
  const [q, setQ] = useState("");
  const [list, setList] = useState<PUser[] | null>(null);
  const [detail, setDetail] = useState<PUserDetail | null>(null);
  const [loadingDetail, setLoadingDetail] = useState(false);

  const load = useCallback(async (query: string) => {
    setList(null);
    const qs = query.trim() ? "?q=" + encodeURIComponent(query.trim()) : "";
    const r = await api<PUserList>("/api/v1/superadmin/users" + qs);
    setList(r.ok && r.data ? r.data.items : []);
  }, []);

  useEffect(() => {
    void load("");
  }, [load]);

  async function openUser(id: number) {
    setLoadingDetail(true);
    const r = await api<PUserDetail>(`/api/v1/superadmin/users/${id}`);
    setLoadingDetail(false);
    if (r.ok && r.data) setDetail(r.data);
  }

  // ── Карточка юзера ──────────────────────────────────────────────────────
  if (detail) {
    const u = detail.user;
    const online = isOnline(u.last_seen_at);
    return (
      <div className="space-y-3.5">
        <button
          onClick={() => setDetail(null)}
          className="text-primary font-bold text-sm flex items-center gap-1"
        >
          ‹ {s.back}
        </button>
        <Card>
          <div className="flex items-center gap-2">
            <div className="text-lg font-extrabold">{displayName(u)}</div>
            {online && (
              <span className="inline-flex items-center gap-1 text-[12px] font-bold text-emerald-600 dark:text-emerald-400">
                <span className="w-2 h-2 rounded-full bg-emerald-500" /> {s.online}
              </span>
            )}
          </div>
          {u.phone && <div className="text-muted text-sm mt-0.5">{u.phone}</div>}
        </Card>

        {/* Активность юзера: онлайн/был(а), когда пришёл(шла), объекты, агентства. */}
        <Card>
          <div className="text-[12px] font-bold text-muted mb-1.5">{s.activity}</div>
          {!online && u.last_seen_at && (
            <div className="flex items-center justify-between py-1.5 border-b border-line">
              <span className="text-[13px] text-muted">{s.lastSeen}</span>
              <span className="text-[13px] font-bold">{fmtDate(u.last_seen_at, lang)}</span>
            </div>
          )}
          {u.created_at && (
            <div className="flex items-center justify-between py-1.5 border-b border-line">
              <span className="text-[13px] text-muted">{s.memberSince}</span>
              <span className="text-[13px] font-bold">{fmtDate(u.created_at, lang)}</span>
            </div>
          )}
          <div className="flex items-center justify-between py-1.5 border-b border-line">
            <span className="text-[13px] text-muted">{s.objects}</span>
            <span className="text-[13px] font-bold">{detail.objects_total}</span>
          </div>
          <div className="flex items-center justify-between py-1.5">
            <span className="text-[13px] text-muted">{s.agencies}</span>
            <span className="text-[13px] font-bold">{detail.agencies.length}</span>
          </div>
        </Card>

        {/* Агентства юзера — КЛИКАБЕЛЬНЫ: открывают агентство (активность + объекты
            без номеров собственников), как раньше открывались из «Финансов». */}
        <div className="text-[14px] font-extrabold mt-1 mx-0.5">{s.agencies}</div>
        {detail.agencies.length === 0 ? (
          <div className="text-muted text-sm text-center py-4">{s.noAgencies}</div>
        ) : (
          <div className="space-y-2">
            {detail.agencies.map((a) => (
              <button
                key={a.agency_id}
                onClick={() => nav.push({ name: "agencyManage", id: a.agency_id })}
                className="w-full flex items-center gap-2 p-3 rounded-xl2 bg-card border border-line shadow-soft text-left active:scale-[.99] transition"
              >
                <span className="font-bold truncate">{a.agency_name}</span>
                <span className="ml-auto shrink-0">{roleBadge(a.role, a.is_owner, s)}</span>
                <ChevronRight size={16} className="text-muted shrink-0" />
              </button>
            ))}
          </div>
        )}

        <div className="text-[14px] font-extrabold mt-2 mx-0.5">
          {s.objects} · {detail.objects_total}
        </div>
        {detail.objects.length === 0 ? (
          <div className="text-muted text-sm text-center py-6">{s.noObjects}</div>
        ) : (
          <div className="space-y-2">
            {detail.objects.map((o) => (
              <div
                key={o.id}
                className="flex items-center gap-3 p-3 rounded-xl2 bg-card border border-line shadow-soft"
              >
                <span className="w-10 h-10 rounded-lg bg-primary-soft text-primary flex items-center justify-center font-extrabold shrink-0">
                  🏠
                </span>
                <span className="min-w-0">
                  <span className="block font-bold truncate">
                    №{o.display_id} {o.district ? "· " + o.district : ""}
                  </span>
                  <span className="block text-muted text-[13px]">
                    {o.price ? `${o.price} ${o.currency}` : o.status}
                  </span>
                </span>
              </div>
            ))}
          </div>
        )}
      </div>
    );
  }

  // ── Список юзеров ───────────────────────────────────────────────────────
  return (
    <div className="space-y-3">
      {loadingDetail && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center"
          style={{ background: "color-mix(in srgb, var(--bg) 82%, transparent)" }}
        >
          <Spinner />
        </div>
      )}
      <div className="text-xl font-extrabold tracking-tight mx-0.5">{s.users}</div>
      <Input
        value={q}
        onChange={(e) => setQ(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === "Enter") void load(q);
        }}
        placeholder={s.search}
      />
      {list === null ? (
        <Spinner />
      ) : list.length === 0 ? (
        <div className="text-muted text-sm text-center py-8">{s.empty}</div>
      ) : (
        <div className="space-y-2">
          {list.map((u) => (
            <button
              key={u.id}
              onClick={() => void openUser(u.id)}
              className="w-full flex items-center gap-3 p-3.5 rounded-xl2 bg-card border border-line shadow-soft text-left active:scale-[.985] transition"
            >
              <span className="w-11 h-11 rounded-xl bg-primary-soft text-primary flex items-center justify-center font-extrabold shrink-0">
                {(displayName(u)[0] || "?").toUpperCase()}
              </span>
              <span className="min-w-0">
                <span className="block font-extrabold truncate">{displayName(u)}</span>
                <span className="block text-muted text-[13px]">
                  {[u.phone, `${u.agencies_count} ${s.inAgencies}`].filter(Boolean).join(" · ")}
                </span>
              </span>
              <span className="ml-auto text-muted text-xl">›</span>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
