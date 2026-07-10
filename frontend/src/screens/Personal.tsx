// Личное пространство (юзер-центричная модель, 2026-07).
//
// Самодостаточные экраны нового флоу: онбординг (язык → профиль + номер) и личный
// хаб (список агентств с ролью, создать/вступить/переключиться). Встройка в машину
// фаз App.tsx делается ОТДЕЛЬНО (со сборкой на pc1): App должен рендерить
// <PersonalApp/> в личном контексте (role==='user' или пока не «вошёл» в агентство),
// и <Shell/> — когда пользователь внутри агентства (agency_id/acting выставлен).
//
// ВНИМАНИЕ: строки временно локальны (STR). При интеграции перенести их в i18n.ts.
import React, { useCallback, useEffect, useState } from "react";
import { useApp } from "../store";
import { api, errText } from "../api";
import { getInitData, requestContact, haptic } from "../telegram";
import { Button, Card, Field, Input, Spinner } from "../components/ui";
import type { AuthResponse, Membership, UserProfile } from "../types";

// ── Локальные строки (перенести в i18n.ts при интеграции) ────────────────────
const STR: Record<string, Record<string, string>> = {
  ru: {
    chooseLang: "Выберите язык",
    next: "Далее",
    getAcquainted: "Давайте познакомимся",
    profileSub: "Это ваша личная карточка — она с вами во всех агентствах.",
    firstName: "Имя",
    lastName: "Фамилия",
    phone: "Номер телефона",
    sharePhone: "Поделиться номером из Telegram",
    phoneHint: "Номер можно оставить на потом — он обязателен только когда создаёте агентство.",
    change: "Изменить",
    continueBtn: "Продолжить",
    greeting: "С возвращением",
    noPhone: "номер не задан",
    myAgencies: "Мои агентства",
    add: "Добавить",
    noAgenciesTitle: "Пока вы сами по себе",
    noAgenciesSub: "Создайте своё агентство или вступите в существующее по коду-приглашению.",
    createAgency: "Создать агентство",
    joinByCode: "Вступить по коду",
    role_admin: "главный админ",
    role_agent: "агент",
    agencyNamePrompt: "Название агентства:",
    codePrompt: "Код приглашения:",
    joined: "Вы вступили в агентство.",
    entering: "Входим…",
    phoneNeeded: "Сначала добавьте номер телефона в профиле.",
    saved: "Сохранено.",
  },
  uz: {
    chooseLang: "Tilni tanlang",
    next: "Keyingi",
    getAcquainted: "Keling, tanishamiz",
    profileSub: "Bu sizning shaxsiy kartangiz — barcha agentliklarda siz bilan.",
    firstName: "Ism",
    lastName: "Familiya",
    phone: "Telefon raqami",
    sharePhone: "Telegramdan raqamni ulashish",
    phoneHint: "Raqamni keyinroq qoldirsangiz boʻladi — u faqat agentlik ochganda kerak.",
    change: "Oʻzgartirish",
    continueBtn: "Davom etish",
    greeting: "Xush kelibsiz",
    noPhone: "raqam kiritilmagan",
    myAgencies: "Mening agentliklarim",
    add: "Qoʻshish",
    noAgenciesTitle: "Hozircha yakkasiz",
    noAgenciesSub: "Oʻz agentligingizni oching yoki taklif kodi bilan qoʻshiling.",
    createAgency: "Agentlik ochish",
    joinByCode: "Kod bilan qoʻshilish",
    role_admin: "bosh admin",
    role_agent: "agent",
    agencyNamePrompt: "Agentlik nomi:",
    codePrompt: "Taklif kodi:",
    joined: "Agentlikka qoʻshildingiz.",
    entering: "Kirilmoqda…",
    phoneNeeded: "Avval profilga telefon raqamini qoʻshing.",
    saved: "Saqlandi.",
  },
  en: {
    chooseLang: "Choose language",
    next: "Next",
    getAcquainted: "Let’s get acquainted",
    profileSub: "This is your personal card — it stays with you across agencies.",
    firstName: "First name",
    lastName: "Last name",
    phone: "Phone number",
    sharePhone: "Share number from Telegram",
    phoneHint: "You can add the number later — it’s only required when creating an agency.",
    change: "Change",
    continueBtn: "Continue",
    greeting: "Welcome back",
    noPhone: "no number set",
    myAgencies: "My agencies",
    add: "Add",
    noAgenciesTitle: "You’re on your own for now",
    noAgenciesSub: "Create your own agency or join an existing one with an invite code.",
    createAgency: "Create agency",
    joinByCode: "Join by code",
    role_admin: "main admin",
    role_agent: "agent",
    agencyNamePrompt: "Agency name:",
    codePrompt: "Invite code:",
    joined: "You joined the agency.",
    entering: "Entering…",
    phoneNeeded: "Add a phone number in your profile first.",
    saved: "Saved.",
  },
};

function useStr() {
  const { lang } = useApp();
  return STR[lang] || STR.ru;
}

function initials(a?: string | null, b?: string | null): string {
  return ((a || "?")[0] + (b || "")[0]).toUpperCase();
}

function agShort(name: string): string {
  return name.trim().split(/\s+/).slice(0, 2).map((w) => w[0] || "").join("").toUpperCase();
}

// ── Верхнеуровневый вход в личное пространство ────────────────────────────────
export function PersonalApp({ onEnterAgency }: { onEnterAgency: (data: AuthResponse) => void }) {
  const { user } = useApp();
  const [onboarded, setOnboarded] = useState(false);
  // Онбординг показываем, пока не заполнено имя (первый вход).
  const needsOnboarding = !!user && !user.first_name && !onboarded;
  if (needsOnboarding) return <Onboarding onDone={() => setOnboarded(true)} />;
  return <PersonalHub onEnterAgency={onEnterAgency} />;
}

// ── Онбординг: язык → профиль + номер ─────────────────────────────────────────
function Onboarding({ onDone }: { onDone: () => void }) {
  const { lang, setLang, user, setUser, toast } = useApp();
  const s = useStr();
  const [step, setStep] = useState<"lang" | "profile">("lang");
  const [first, setFirst] = useState(user?.first_name || user?.full_name || "");
  const [last, setLast] = useState(user?.last_name || "");
  const [phone, setPhone] = useState(user?.phone || "");
  const [busy, setBusy] = useState(false);

  const langOpt = (code: "ru" | "uz" | "en", flag: string, label: string) => (
    <button
      key={code}
      onClick={() => {
        haptic("light");
        setLang(code);
      }}
      className={
        "w-full flex items-center gap-3.5 p-4 rounded-2xl border-2 text-left transition " +
        (lang === code ? "border-primary shadow-[0_0_0_4px_var(--ring)]" : "border-line bg-card")
      }
    >
      <span className="text-2xl">{flag}</span>
      <span className="font-extrabold">{label}</span>
    </button>
  );

  async function shareContact() {
    const p = await requestContact();
    if (p) setPhone(p);
  }

  async function finish() {
    if (!first.trim() || busy) return;
    setBusy(true);
    // 1. Имя/фамилия/язык.
    const r = await api<UserProfile>("/api/v1/auth/me", {
      method: "PATCH",
      body: { first_name: first.trim(), last_name: last.trim(), language: lang },
    });
    if (!r.ok || !r.data) {
      setBusy(false);
      toast(errText(r.data, r.status), "err");
      return;
    }
    let updated = r.data;
    // 2. Номер (если задан и изменился) — из Telegram-контакта, подтверждён.
    const cleanPhone = phone.trim();
    if (cleanPhone && cleanPhone !== (user?.phone || "")) {
      const rp = await api<UserProfile>("/api/v1/auth/me/phone", {
        method: "POST",
        body: { phone: cleanPhone },
      });
      if (rp.ok && rp.data) updated = rp.data;
      else toast(errText(rp.data, rp.status), "err");
    }
    setUser(updated);
    setBusy(false);
    onDone();
  }

  if (step === "lang") {
    return (
      <div className="min-h-[100dvh] flex flex-col px-4 pt-8 pb-6 animate-fade-up">
        <div className="text-center mb-5">
          <div
            className="mx-auto mb-4 w-16 h-16 rounded-2xl flex items-center justify-center text-white text-2xl font-extrabold"
            style={{ background: "var(--grad)" }}
          >
            R
          </div>
          <h1 className="text-2xl font-extrabold tracking-tight">Realty AI</h1>
          <p className="text-muted text-sm mt-1.5">{s.chooseLang}</p>
        </div>
        <div className="space-y-2.5 mt-2">
          {langOpt("ru", "🇷🇺", "Русский")}
          {langOpt("uz", "🇺🇿", "Oʻzbekcha")}
          {langOpt("en", "🇬🇧", "English")}
        </div>
        <div className="flex-1" />
        <Button full onClick={() => setStep("profile")}>
          {s.next} →
        </Button>
      </div>
    );
  }

  const shared = !!phone;
  return (
    <div className="min-h-[100dvh] flex flex-col px-4 pt-8 pb-6 animate-fade-up">
      <h1 className="text-2xl font-extrabold tracking-tight">{s.getAcquainted}</h1>
      <p className="text-muted text-sm mt-1.5">{s.profileSub}</p>
      <Field label={s.firstName}>
        <Input value={first} onChange={(e) => setFirst(e.target.value)} placeholder="Азиз" />
      </Field>
      <Field label={s.lastName}>
        <Input value={last} onChange={(e) => setLast(e.target.value)} placeholder="Каримов" />
      </Field>
      <Field label={s.phone}>
        {shared ? (
          <div className="flex items-center gap-3">
            <Input value={phone} onChange={(e) => setPhone(e.target.value)} inputMode="tel" />
            <Button variant="soft" size="sm" onClick={shareContact}>
              {s.change}
            </Button>
          </div>
        ) : (
          <Button variant="ghost" full onClick={shareContact}>
            📲 {s.sharePhone}
          </Button>
        )}
      </Field>
      <p className="text-muted text-[13px] mt-2 leading-relaxed">{s.phoneHint}</p>
      <div className="flex-1 min-h-[16px]" />
      <Button full disabled={!first.trim() || busy} onClick={finish}>
        {busy ? "…" : s.continueBtn + " →"}
      </Button>
    </div>
  );
}

// ── Личный хаб ────────────────────────────────────────────────────────────────
function PersonalHub({ onEnterAgency }: { onEnterAgency: (data: AuthResponse) => void }) {
  const { user, toast } = useApp();
  const s = useStr();
  const [memberships, setMemberships] = useState<Membership[] | null>(null);
  const [entering, setEntering] = useState(false);

  const load = useCallback(async () => {
    const r = await api<Membership[]>("/api/v1/auth/memberships");
    setMemberships(r.ok && r.data ? r.data : []);
  }, []);
  useEffect(() => {
    void load();
  }, [load]);

  async function enter(agencyId: number) {
    if (entering) return;
    setEntering(true);
    const r = await api<AuthResponse>(`/api/v1/agencies/${agencyId}/enter`, { method: "POST" });
    setEntering(false);
    if (r.ok && r.data) onEnterAgency(r.data);
    else toast(errText(r.data, r.status), "err");
  }

  async function createAgency() {
    const name = window.prompt(s.agencyNamePrompt, "")?.trim();
    if (!name) return;
    if (!user?.phone) {
      toast(s.phoneNeeded, "warn");
      return;
    }
    const has = (memberships?.length || 0) > 0;
    const fullName = [user.first_name, user.last_name].filter(Boolean).join(" ") || user.full_name || "";
    const r = has
      ? await api<AuthResponse>("/api/v1/agencies/open", { method: "POST", body: { name, phone: user.phone } })
      : await api<AuthResponse>("/api/v1/agencies/register", {
          method: "POST",
          body: { init_data: getInitData(), name, owner_name: fullName, phone: user.phone },
        });
    if (r.ok && r.data) onEnterAgency(r.data);
    else toast(errText(r.data, r.status), "err");
  }

  async function joinByCode() {
    const code = window.prompt(s.codePrompt, "")?.trim();
    if (!code) return;
    const r = await api<AuthResponse>("/api/v1/invites/redeem", {
      method: "POST",
      body: { init_data: getInitData(), code },
    });
    if (r.ok && r.data) {
      toast(s.joined, "ok");
      void load();
    } else {
      toast(errText(r.data, r.status), "err");
    }
  }

  const heroName = [user?.first_name, user?.last_name].filter(Boolean).join(" ") || user?.full_name || "—";
  const has = (memberships?.length || 0) > 0;

  return (
    <div className="min-h-[100dvh]">
      {entering && (
        <div
          className="fixed inset-0 z-50 flex flex-col items-center justify-center gap-3"
          style={{ background: "color-mix(in srgb, var(--bg) 82%, transparent)" }}
        >
          <Spinner />
          <div className="text-muted text-sm">{s.entering}</div>
        </div>
      )}
      {/* Шапка-герой */}
      <div className="px-5 pt-7 pb-6 text-white" style={{ background: "var(--grad-hero)" }}>
        <div className="text-[13px] opacity-85">{s.greeting} 👋</div>
        <div className="text-xl font-extrabold mt-0.5">{heroName}</div>
        <div className="text-[13px] opacity-85 mt-0.5">{user?.phone || s.noPhone}</div>
      </div>

      <div className="max-w-[560px] mx-auto px-3.5 py-4">
        {memberships === null ? (
          <Spinner />
        ) : has ? (
          <>
            <div className="flex items-center justify-between mt-1 mx-0.5 mb-2.5">
              <span className="text-[14px] font-extrabold">{s.myAgencies}</span>
              <Button variant="soft" size="sm" onClick={() => void createAgency()}>
                ＋ {s.add}
              </Button>
            </div>
            <div className="space-y-2.5">
              {memberships.map((m) => (
                <button
                  key={m.agency_id}
                  onClick={() => void enter(m.agency_id)}
                  className="w-full flex items-center gap-3 p-3.5 rounded-2xl bg-card border border-line shadow-soft text-left active:scale-[.985] transition"
                >
                  <span className="w-11 h-11 rounded-xl bg-primary-soft text-primary flex items-center justify-center font-extrabold">
                    {agShort(m.agency_name)}
                  </span>
                  <span className="min-w-0">
                    <span className="block font-extrabold truncate">{m.agency_name}</span>
                    <span
                      className={
                        "inline-block mt-1 px-2.5 py-0.5 rounded-full text-[11px] font-extrabold " +
                        (m.is_owner || m.role === "agency_admin"
                          ? "bg-blue-500/15 text-blue-600 dark:text-blue-400"
                          : "bg-slate-500/15 text-slate-600 dark:text-slate-300")
                      }
                    >
                      {m.is_owner || m.role === "agency_admin" ? s.role_admin : s.role_agent}
                    </span>
                  </span>
                  <span className="ml-auto text-muted text-xl">›</span>
                </button>
              ))}
            </div>
          </>
        ) : (
          <Card className="text-center py-7 px-4">
            <div className="mx-auto mb-3 w-14 h-14 rounded-2xl bg-primary-soft text-primary flex items-center justify-center text-2xl">
              🏢
            </div>
            <div className="text-[15px] font-extrabold">{s.noAgenciesTitle}</div>
            <p className="text-[13px] text-muted mt-1.5 leading-relaxed max-w-[300px] mx-auto">
              {s.noAgenciesSub}
            </p>
            <div className="space-y-2.5 mt-5">
              <Button full onClick={() => void createAgency()}>
                ＋ {s.createAgency}
              </Button>
              <Button variant="ghost" full onClick={() => void joinByCode()}>
                🔑 {s.joinByCode}
              </Button>
            </div>
          </Card>
        )}
      </div>
    </div>
  );
}
