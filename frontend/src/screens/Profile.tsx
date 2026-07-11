import { useEffect, useState } from "react";
import { User, LifeBuoy, Building2, Pencil, ChevronRight, ChevronDown, Check } from "lucide-react";
import { useApp } from "../store";
import { useActing } from "../acting";
import { api, errText } from "../api";
import { Card, Row, Hint, Button, Field, Input, Spinner } from "../components/ui";
import { openTelegramLink, haptic } from "../telegram";
import { initials } from "../utils";
import type { Membership, AgencySettings } from "../types";

function agShort(name: string): string {
  return (name || "").trim().split(/\s+/).slice(0, 2).map((w) => w[0] || "").join("").toUpperCase() || "—";
}

// Свитчер агентств (по идее из симуляции): сверху — текущее агентство + ▾,
// тап открывает нижний лист со списком «мои агентства» (галочка на текущем) и
// кнопкой возврата в личное пространство. Заменяет карточку «Мои агентства».
function AgencySwitcher() {
  const { t, L, user, settings } = useApp();
  const { enterAgency, exitToPersonal } = useActing();
  const [open, setOpen] = useState(false);
  const [items, setItems] = useState<Membership[] | null>(null);

  useEffect(() => {
    if (open && items === null) {
      api<Membership[]>("/api/v1/auth/memberships").then((r) =>
        setItems(r.ok && Array.isArray(r.data) ? r.data : [])
      );
    }
  }, [open, items]);

  const currentName = settings?.project_name || settings?.name || user?.full_name || "—";

  return (
    <>
      <button
        onClick={() => { haptic(); setOpen(true); }}
        className="w-full flex items-center gap-3 rounded-xl2 bg-card border border-line shadow-soft p-3 mb-3 active:scale-[.99] transition"
      >
        <span className="w-10 h-10 rounded-xl bg-primary-soft text-primary flex items-center justify-center font-extrabold shrink-0">
          {agShort(currentName)}
        </span>
        <span className="min-w-0 flex-1 text-left font-extrabold truncate">{currentName}</span>
        <ChevronDown size={20} className="text-muted shrink-0" />
      </button>

      {open && (
        <div
          className="fixed inset-0 z-50 flex items-end justify-center"
          style={{ background: "color-mix(in srgb, var(--bg) 68%, transparent)" }}
          onClick={() => setOpen(false)}
        >
          <div
            className="w-full max-w-[560px] bg-card border-t border-line rounded-t-xl3 px-4 pt-3 pb-[calc(18px+env(safe-area-inset-bottom,0px))] animate-fade-up"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="w-10 h-1 rounded-full bg-line mx-auto mb-3.5" />
            <div className="text-[15px] font-extrabold text-center mb-3">{t("switchAgency")}</div>
            <div className="space-y-2 max-h-[46vh] overflow-y-auto">
              {items === null ? (
                <div className="py-6 flex justify-center"><Spinner /></div>
              ) : (
                items.map((m) => {
                  const cur = m.is_current;
                  return (
                    <button
                      key={m.agency_id}
                      disabled={cur}
                      onClick={() => { setOpen(false); enterAgency(m.agency_id); }}
                      className={
                        "w-full flex items-center gap-3 p-3 rounded-xl border text-left transition " +
                        (cur ? "bg-primary-soft border-primary/40" : "bg-card border-line active:scale-[.99]")
                      }
                    >
                      <span className="w-9 h-9 rounded-lg bg-[var(--soft)] text-primary flex items-center justify-center font-extrabold shrink-0">
                        {agShort(m.project_name || m.agency_name)}
                      </span>
                      <span className="min-w-0 flex-1">
                        <span className="block font-bold truncate">{m.project_name || m.agency_name}</span>
                        <span className="block text-[12px] text-muted">{L.roleLabel(m.role, m.is_owner)}</span>
                      </span>
                      {cur ? <Check size={18} className="text-primary shrink-0" /> : <ChevronRight size={16} className="text-muted shrink-0" />}
                    </button>
                  );
                })
              )}
            </div>
            <Button variant="ghost" full className="mt-3.5" onClick={() => { setOpen(false); haptic(); exitToPersonal(); }}>
              🏠 {t("exitToPersonalHub")}
            </Button>
          </div>
        </div>
      )}
    </>
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
  const { t, L, user, settings } = useApp();
  if (!user) return null;
  const displayName = user.full_name || (user.username ? "@" + user.username : t("notSet"));
  const supportUrl = settings?.support_url || null;
  return (
    <div>
      {/* Свитчер агентств (сверху): переключиться на другое агентство или выйти в
          личное пространство. Заменяет карточку «Мои агентства». Внутри агентства
          суперадмин работает как agency_admin (acting) — свитчер ему тоже нужен;
          прячем только «чистого» суперадмина (его хаб — отдельный экран). */}
      {user.role !== "superadmin" && <AgencySwitcher />}
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
      <AgencyCard />
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
