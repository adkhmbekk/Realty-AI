import { useEffect, useState } from "react";
import { User, LifeBuoy, Building2, Plus, ChevronRight } from "lucide-react";
import { useApp } from "../store";
import { useActing } from "../acting";
import { api } from "../api";
import { Card, Row, Hint, Button, Field, Input } from "../components/ui";
import { openTelegramLink, haptic } from "../telegram";
import { fmtDate, daysLeft, initials } from "../utils";
import type { Membership } from "../types";

// «Мои агентства»: переключатель между агентствами/должностями человека +
// возможность открыть ещё одно своё агентство. Пусто (не показывается) для
// суперадмина и для тех, у кого одно домашнее агентство без доп. членств.
function MyAgenciesCard() {
  const { t, L, toast } = useApp();
  const { enterAgency, openAgency } = useActing();
  const [items, setItems] = useState<Membership[] | null>(null);
  const [opening, setOpening] = useState(false);
  const [name, setName] = useState("");
  const [phone, setPhone] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    api<Membership[]>("/api/v1/auth/memberships").then((r) =>
      setItems(r.ok && Array.isArray(r.data) ? r.data : [])
    );
  }, []);

  async function create() {
    if (!name.trim()) { toast(t("regNameRequired"), "err"); return; }
    setBusy(true);
    await openAgency(name.trim(), phone.trim());
    setBusy(false);
    // При успехе приложение уже переключилось в новое агентство (applyAuth).
  }

  // Показываем, только если человек — участник (у суперадмина членств нет).
  if (!items || items.length === 0) return null;

  return (
    <Card className="mt-3">
      <div className="flex items-center gap-2.5 mb-2.5">
        <Building2 size={18} className="text-primary" />
        <span className="font-extrabold">{t("myAgenciesTitle")}</span>
      </div>
      <div className="space-y-2">
        {items.map((m) => (
          <button
            key={m.agency_id}
            disabled={m.is_current}
            onClick={() => { haptic(); enterAgency(m.agency_id); }}
            className={
              "w-full text-left rounded-xl p-3 border transition flex items-center gap-3 " +
              (m.is_current ? "bg-primary-soft border-primary/40" : "bg-card border-line active:scale-[.99]")
            }
          >
            <span className="w-9 h-9 rounded-lg bg-[var(--soft)] text-primary flex items-center justify-center shrink-0">
              <Building2 size={16} />
            </span>
            <div className="min-w-0 flex-1">
              <div className="font-bold truncate">{m.project_name || m.agency_name}</div>
              <div className="text-[12px] text-muted">{L.roleLabel(m.role, m.is_owner)}</div>
            </div>
            {m.is_current ? (
              <span className="text-[11px] font-extrabold text-primary shrink-0">{t("currentAgency")}</span>
            ) : (
              <ChevronRight size={16} className="text-muted shrink-0" />
            )}
          </button>
        ))}
      </div>
      {opening ? (
        <div className="mt-3">
          <Field label={t("regName")}>
            <Input value={name} onChange={(e) => setName(e.target.value)} placeholder={t("regNamePh")} />
          </Field>
          <Field label={t("regPhone")}>
            <Input inputMode="tel" value={phone} onChange={(e) => setPhone(e.target.value)} placeholder={t("regPhonePh")} />
          </Field>
          <div className="grid grid-cols-2 gap-2 mt-3">
            <Button variant="ghost" onClick={() => setOpening(false)}>{t("cancel")}</Button>
            <Button disabled={busy} onClick={create}>{t("regSubmit")}</Button>
          </div>
        </div>
      ) : (
        <button
          onClick={() => setOpening(true)}
          className="w-full mt-3 text-[13px] font-bold text-primary inline-flex items-center justify-center gap-1 active:scale-95"
        >
          <Plus size={15} /> {t("openAnotherAgency")}
        </button>
      )}
    </Card>
  );
}

export function ProfileScreen() {
  const { t, L, lang, user, settings } = useApp();
  if (!user) return null;
  const displayName = user.full_name || (user.username ? "@" + user.username : t("notSet"));
  const supportUrl = settings?.support_url || null;
  return (
    <div>
      {/* Личная шапка с аватаром-инициалами */}
      <div
        className="flex items-center gap-3.5 rounded-xl3 p-4 mb-3 text-white overflow-hidden"
        style={{ background: "var(--grad-hero)", boxShadow: "0 16px 40px rgba(52,31,163,.36)" }}
      >
        <div className="w-14 h-14 shrink-0 rounded-2xl bg-white/20 border border-white/40 flex items-center justify-center text-xl font-extrabold backdrop-blur">
          {initials(user.full_name || user.username) || <User size={24} />}
        </div>
        <div className="min-w-0">
          <div className="text-[20px] font-extrabold leading-tight truncate">{displayName}</div>
          <div className="text-[13px] opacity-90 mt-0.5">{L.roleLabel(user.role, user.is_owner)}</div>
        </div>
      </div>
      <Card>
        <Row label={t("username")} value={user.username ? "@" + user.username : t("notSet")} />
        <Row label={t("tgId")} value={user.telegram_id} />
      </Card>
      <MyAgenciesCard />
      {settings?.project_name && (
        <Hint>
          {t("projectName")}: {settings.project_name}
        </Hint>
      )}
      {user.is_owner && settings?.subscription_expires_at && (
        <Card className="mt-3">
          <Row label={t("subUntil")} value={fmtDate(settings.subscription_expires_at, lang, settings.timezone)} />
          <Row label={t("daysLeft")} value={daysLeft(settings.subscription_expires_at)} />
        </Card>
      )}
      {/* Поддержка: связаться с нами (открывает чат в Telegram). */}
      {supportUrl && (
        <Card className="mt-3">
          <div className="flex items-center gap-2.5 mb-1.5">
            <LifeBuoy size={18} className="text-primary" />
            <span className="font-extrabold">{t("support")}</span>
          </div>
          <p className="text-[13px] text-muted mb-3">{t("supportText")}</p>
          <Button full size="sm" onClick={() => openTelegramLink(supportUrl)}>
            {t("contactSupport")}
          </Button>
        </Card>
      )}
      {/* Версия сборки — чтобы было видно, что приложение обновилось до свежей. */}
      <div className="text-center text-[11px] text-muted mt-5">
        {t("buildVersion")}: {__BUILD_ID__}
      </div>
    </div>
  );
}

export function SuspendedScreen() {
  const { t, L, user } = useApp();
  return (
    <div>
      {user && (
        <Card>
          <Row label={t("name")} value={user.full_name || t("notSet")} />
          <Row label={t("roleLbl")} value={L.roleLabel(user.role, user.is_owner)} />
        </Card>
      )}
      <div className="mt-3 rounded-[14px] px-3.5 py-3 text-sm leading-relaxed bg-rose-500/10 text-rose-600 dark:text-rose-300 border border-rose-500/30">
        {t("suspendedMsg")}
      </div>
    </div>
  );
}
