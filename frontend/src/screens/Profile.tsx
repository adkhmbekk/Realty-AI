import { useEffect, useState } from "react";
import { User, LifeBuoy, Building2, Pencil, Plus, ChevronRight, Trash2 } from "lucide-react";
import { useApp } from "../store";
import { useActing } from "../acting";
import { api, errText } from "../api";
import { Card, Row, Hint, Button, Field, Input } from "../components/ui";
import { openTelegramLink, haptic, confirmDialog } from "../telegram";
import { fmtDate, daysLeft, initials } from "../utils";
import type { Membership, AgencySettings } from "../types";

// «Мои агентства»: переключатель между агентствами/должностями человека +
// возможность открыть ещё одно своё агентство. Пусто (не показывается) для
// суперадмина и для тех, у кого одно домашнее агентство без доп. членств.
function MyAgenciesCard() {
  const { t, L, toast } = useApp();
  const { enterAgency, openAgency, deleteAgency } = useActing();
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
    if (!phone.trim()) { toast(t("regPhoneRequired"), "err"); return; }
    setBusy(true);
    await openAgency(name.trim(), phone.trim());
    setBusy(false);
    // При успехе приложение уже переключилось в новое агентство (applyAuth).
  }

  async function remove(id: number) {
    if (await confirmDialog(t("delAgencyQ"))) deleteAgency(id);
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
          <div
            key={m.agency_id}
            className={
              "rounded-xl border flex items-center " +
              (m.is_current ? "bg-primary-soft border-primary/40" : "bg-card border-line")
            }
          >
            <button
              disabled={m.is_current}
              onClick={() => { haptic(); enterAgency(m.agency_id); }}
              className="flex-1 min-w-0 text-left p-3 flex items-center gap-3 transition active:scale-[.99] disabled:active:scale-100"
            >
              <span className="w-9 h-9 rounded-lg bg-[var(--soft)] text-primary flex items-center justify-center shrink-0">
                <Building2 size={16} />
              </span>
              <div className="min-w-0 flex-1">
                <div className="font-bold truncate">{m.project_name || m.agency_name}</div>
                <div className="text-[12px] text-muted truncate">
                  {L.roleLabel(m.role, m.is_owner)}{m.is_current ? " · " + t("currentAgency") : ""}
                </div>
              </div>
              {!m.is_current && <ChevronRight size={16} className="text-muted shrink-0" />}
            </button>
            {m.is_owner && items.length > 1 && (
              <button
                onClick={() => remove(m.agency_id)}
                className="w-11 h-11 shrink-0 flex items-center justify-center text-rose-500 active:scale-90"
                aria-label={t("delAgency")}
              >
                <Trash2 size={16} />
              </button>
            )}
          </div>
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

// Карточка агентства в профиле: название, контактный телефон, имя владельца.
// Владелец может отредактировать (карандаш справа сверху) — название/телефон/владелец.
function AgencyCard() {
  const { t, user, settings, setSettings, toast } = useApp();
  const [editing, setEditing] = useState(false);
  const [name, setName] = useState("");
  const [phone, setPhone] = useState("");
  const [ownerName, setOwnerName] = useState("");
  const [saving, setSaving] = useState(false);
  if (!settings) return null;
  const canEdit = !!user?.is_owner;

  function open() {
    setName(settings!.name || "");
    setPhone(settings!.contact_phone || "");
    setOwnerName(settings!.owner_name || "");
    setEditing(true);
  }
  async function save() {
    if (!name.trim()) {
      toast(t("agencyNameEmpty"), "err");
      return;
    }
    setSaving(true);
    const r = await api<AgencySettings>("/api/v1/agency/settings", {
      method: "PATCH",
      body: { name: name.trim(), contact_phone: phone.trim(), owner_name: ownerName.trim() },
    });
    setSaving(false);
    if (r.ok && r.data) {
      setSettings(r.data);
      setEditing(false);
      toast(t("saved"), "ok");
    } else toast(errText(r.data, r.status), "err");
  }

  return (
    <Card className="mt-3">
      {editing ? (
        <>
          <Field label={t("agencyNameLbl")}>
            <Input value={name} onChange={(e) => setName(e.target.value)} />
          </Field>
          <Field label={t("contactPhone")}>
            <Input inputMode="tel" value={phone} onChange={(e) => setPhone(e.target.value)} />
          </Field>
          <Hint>{t("contactPhoneHint")}</Hint>
          <Field label={t("ownerNameLbl")}>
            <Input value={ownerName} onChange={(e) => setOwnerName(e.target.value)} />
          </Field>
          {settings.contact_username && <Hint>{t("ownerTgLbl")}: {settings.contact_username}</Hint>}
          <div className="grid grid-cols-2 gap-2 mt-4">
            <Button variant="ghost" disabled={saving} onClick={() => setEditing(false)}>{t("cancel")}</Button>
            <Button disabled={saving} onClick={save}>{t("saveChanges")}</Button>
          </div>
        </>
      ) : (
        <div className="flex items-start justify-between gap-2">
          <div className="min-w-0">
            <div className="flex items-center gap-2 mb-1.5">
              <Building2 size={16} className="text-primary" />
              <span className="font-extrabold">{t("agencyLbl")}</span>
            </div>
            <div className="text-[15px] font-extrabold truncate">{settings.name || "—"}</div>
            <div className="text-[12.5px] text-muted mt-0.5">{settings.contact_phone || t("notSet")}</div>
            {settings.owner_name && (
              <div className="text-[12.5px] text-muted mt-0.5">{t("ownerNameLbl")}: {settings.owner_name}</div>
            )}
          </div>
          {canEdit && (
            <button
              onClick={open}
              title={t("editAgency")}
              className="w-9 h-9 shrink-0 rounded-xl bg-primary-soft text-primary flex items-center justify-center active:scale-90"
            >
              <Pencil size={16} />
            </button>
          )}
        </div>
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
      <AgencyCard />
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
