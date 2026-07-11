import { useEffect, useState } from "react";
import { createPortal } from "react-dom";
import { User, LifeBuoy, Building2, Pencil, ChevronRight, ChevronDown, Check } from "lucide-react";
import { useApp } from "../store";
import { useActing } from "../acting";
import { useNav } from "../nav";
import { api, errText } from "../api";
import { Card, Row, Hint, Button, Field, Input, Spinner } from "../components/ui";
import { openTelegramLink, haptic } from "../telegram";
import { initials } from "../utils";
import type { Membership, AgencySettings, AgencyOut } from "../types";

// Нормализованный элемент свитчера (общий для участника и суперадмина).
type SwitchItem = { agency_id: number; name: string; roleLabel: string | null; is_current: boolean };

function agShort(name: string): string {
  return (name || "").trim().split(/\s+/).slice(0, 2).map((w) => w[0] || "").join("").toUpperCase() || "—";
}

// Нижний лист переключения агентств (всплывает по стрелке в карточке агентства).
// Список: у участника — из членств (/auth/memberships); у суперадмина (acting) —
// из /agencies/mine (Realty AI + личные). Тап входит в агентство.
function SwitchSheet({ onClose }: { onClose: () => void }) {
  const { t, L, user } = useApp();
  const { enterAgency } = useActing();
  const nav = useNav();
  const [items, setItems] = useState<SwitchItem[] | null>(null);
  const [switching, setSwitching] = useState(false);
  const isSuper = user?.real_role === "superadmin";

  useEffect(() => {
    if (isSuper) {
      api<AgencyOut[]>("/api/v1/agencies/mine").then((r) => {
        const arr = r.ok && Array.isArray(r.data) ? r.data : [];
        setItems(arr.map((a) => ({
          agency_id: a.id,
          name: a.project_name || a.name,
          roleLabel: a.is_shared ? t("sharedAgencyBadge") : null,
          is_current: a.id === user?.acting_as_agency_id,
        })));
      });
    } else {
      api<Membership[]>("/api/v1/auth/memberships").then((r) => {
        const arr = r.ok && Array.isArray(r.data) ? r.data : [];
        setItems(arr.map((m) => ({
          agency_id: m.agency_id,
          name: m.project_name || m.agency_name,
          roleLabel: L.roleLabel(m.role, m.is_owner),
          is_current: m.is_current,
        })));
      });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Портал в body: иначе fixed-лист привязывается к трансформированному
  // контейнеру агентства (Shell) и «висит» обрезанным внизу, а не всплывает
  // поверх всего экрана.
  return createPortal(
    <div
      className="fixed inset-0 z-[100] flex items-end justify-center"
      style={{ background: "color-mix(in srgb, var(--bg) 68%, transparent)" }}
      onClick={onClose}
    >
      <div
        className="w-full max-w-[560px] bg-card border-t border-line rounded-t-xl3 px-4 pt-3 pb-[calc(18px+env(safe-area-inset-bottom,0px))] animate-fade-up"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="w-10 h-1 rounded-full bg-line mx-auto mb-3.5" />
        <div className="text-[15px] font-extrabold text-center mb-3">{t("switchAgency")}</div>
        <div className="space-y-2 max-h-[52vh] overflow-y-auto">
          {items === null ? (
            <div className="py-6 flex justify-center"><Spinner /></div>
          ) : (
            items.map((m) => {
              const cur = m.is_current;
              return (
                <button
                  key={m.agency_id}
                  disabled={cur || switching}
                  onClick={async () => {
                    // Реальное переключение: входим в агентство и приземляемся на
                    // его ГЛАВНУЮ (как при входе из хаба). Без resetTo мы оставались
                    // на экране профиля — и переключение выглядело как «ничего не
                    // произошло / вернуло в кабинет».
                    setSwitching(true);
                    const ok = await enterAgency(m.agency_id);
                    onClose();
                    if (ok) nav.resetTo({ name: "home" });
                    else setSwitching(false);
                  }}
                  className={
                    "w-full flex items-center gap-3 p-3 rounded-xl border text-left transition " +
                    (cur ? "bg-primary-soft border-primary/40" : "bg-card border-line active:scale-[.99]")
                  }
                >
                  <span className="w-9 h-9 rounded-lg bg-[var(--soft)] text-primary flex items-center justify-center font-extrabold shrink-0">
                    {agShort(m.name)}
                  </span>
                  <span className="min-w-0 flex-1">
                    <span className="block font-bold truncate">{m.name}</span>
                    {m.roleLabel && <span className="block text-[12px] text-muted">{m.roleLabel}</span>}
                  </span>
                  {cur ? <Check size={18} className="text-primary shrink-0" /> : <ChevronRight size={16} className="text-muted shrink-0" />}
                </button>
              );
            })
          )}
        </div>
      </div>
    </div>,
    document.body,
  );
}

// Карточка агентства в профиле: название, контактный телефон, имя владельца.
// Владелец может отредактировать (карандаш справа сверху) — название/телефон/владелец.
function AgencyCard() {
  const { t, user, settings, setSettings, toast } = useApp();
  const [editing, setEditing] = useState(false);
  const [name, setName] = useState("");
  const [phone, setPhone] = useState("");
  const [saving, setSaving] = useState(false);
  if (!settings) return null;
  const canEdit = !!user?.is_owner;
  const agencyName = settings.project_name || settings.name || "—";

  function open() {
    setName(settings!.name || "");
    setPhone(settings!.contact_phone || "");
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
      body: { name: name.trim(), contact_phone: phone.trim() },
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
          <div className="grid grid-cols-2 gap-2 mt-4">
            <Button variant="ghost" disabled={saving} onClick={() => setEditing(false)}>{t("cancel")}</Button>
            <Button disabled={saving} onClick={save}>{t("saveChanges")}</Button>
          </div>
        </>
      ) : (
        <div className="flex items-center gap-3">
          <span className="w-11 h-11 shrink-0 rounded-xl bg-primary-soft text-primary flex items-center justify-center font-extrabold">
            {agShort(agencyName)}
          </span>
          <div className="min-w-0 flex-1">
            <div className="text-[11px] text-muted">{t("agencyLbl")}</div>
            <div className="text-[15px] font-extrabold truncate">{agencyName}</div>
            <div className="text-[12.5px] text-muted truncate">
              {settings.contact_phone || t("notSet")}
            </div>
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
  const { exitToPersonal, exitToPlatform } = useActing();
  const nav = useNav();
  if (!user) return null;
  const displayName = user.full_name || (user.username ? "@" + user.username : t("notSet"));
  const supportUrl = settings?.support_url || null;
  const isSuper = user.real_role === "superadmin";
  // «В личный кабинет» и свитчер показываем внутри агентства (обычный участник
  // или суперадмин в acting). У «чистого» суперадмина (в его хабе) — не нужно.
  const inAgency = user.role !== "superadmin";
  const [switchOpen, setSwitchOpen] = useState(false);
  return (
    <div>
      {/* Личная шапка с аватаром-инициалами + стрелка переключения агентства */}
      <div
        className="flex items-center gap-3.5 rounded-xl3 p-4 mb-3 text-white overflow-hidden"
        style={{ background: "var(--grad-hero)", boxShadow: "0 16px 40px rgba(52,31,163,.36)" }}
      >
        <div className="w-14 h-14 shrink-0 rounded-2xl bg-white/20 border border-white/40 flex items-center justify-center text-xl font-extrabold backdrop-blur">
          {initials(user.full_name || user.username) || <User size={24} />}
        </div>
        <div className="min-w-0 flex-1">
          <div className="text-[20px] font-extrabold leading-tight truncate">{displayName}</div>
          <div className="text-[13px] opacity-90 mt-0.5">{L.roleLabel(user.role, user.is_owner)}</div>
        </div>
        {inAgency && (
          <button
            onClick={() => { haptic(); setSwitchOpen(true); }}
            title={t("switchAgency")}
            className="w-10 h-10 shrink-0 rounded-xl bg-white/20 border border-white/30 flex items-center justify-center active:scale-90"
          >
            <ChevronDown size={20} />
          </button>
        )}
      </div>
      {switchOpen && <SwitchSheet onClose={() => setSwitchOpen(false)} />}
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
      {/* В личный кабинет: возврат из агентства (участник — в личное пространство,
          суперадмин — в его хаб). */}
      {inAgency && (
        <Button
          variant="ghost"
          full
          className="mt-3"
          onClick={async () => {
            haptic();
            if (isSuper) {
              // Суперадмин: выходим на платформу и попадаем на ГЛАВНУЮ хаба.
              await exitToPlatform();
              nav.resetTo({ name: "myAgencies" });
            } else {
              // Участник: в личное пространство (хаб открывается на «Главной»).
              exitToPersonal();
            }
          }}
        >
          🏠 {t("toPersonalCabinet")}
        </Button>
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
