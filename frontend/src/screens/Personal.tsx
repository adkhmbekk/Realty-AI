// Личное пространство (юзер-центричная модель, 2026-07).
//
// Онбординг (язык → имя/фамилия → номер) + личный хаб с нижней панелью
// (Главная / Настройки / Профиль). Дизайн — по прототипу, на дизайн-системе
// приложения. Встройка в App.tsx: фаза "personal" рендерит <PersonalApp/>.
//
// Онбординг показываем ОДИН РАЗ (флаг в localStorage) — existing-юзеры (у кого
// имя уже заполнено бэкфиллом) тоже проходят его при первом входе в новую версию.
import React, { useCallback, useEffect, useState } from "react";
import { Home as HomeIcon, Settings as SettingsIcon, User as UserIcon, Plus, KeyRound, ChevronRight, Building2 } from "lucide-react";
import { useApp } from "../store";
import { api, errText } from "../api";
import { getInitData, requestContact, haptic } from "../telegram";
import { Button, Card, Field, Input, Spinner } from "../components/ui";
import type { AuthResponse, Membership, UserProfile } from "../types";
import type { Lang } from "../i18n";

// ── Локальные строки (перенести в i18n.ts при чистовой доводке) ──────────────
const STR: Record<string, Record<string, string>> = {
  ru: {
    chooseLang: "Выберите язык", next: "Далее",
    getAcquainted: "Давайте познакомимся",
    profileSub: "Это ваша личная карточка — она с вами во всех агентствах.",
    firstName: "Имя", lastName: "Фамилия", phone: "Номер телефона",
    sharePhone: "Поделиться номером из Telegram",
    phoneHint: "Номер можно оставить на потом — он обязателен только когда создаёте агентство.",
    change: "Изменить", continueBtn: "Продолжить",
    greeting: "С возвращением", noPhone: "номер не задан",
    home: "Главная", settings: "Настройки", profile: "Профиль",
    myAgencies: "Мои агентства", add: "Добавить",
    noAgenciesTitle: "Пока вы сами по себе",
    noAgenciesSub: "Создайте своё агентство или вступите в существующее по коду-приглашению.",
    createAgency: "Создать агентство", joinByCode: "Вступить по коду",
    role_admin: "главный админ", role_agent: "агент",
    agencyNamePrompt: "Название агентства:", codePrompt: "Код приглашения:",
    joined: "Вы вступили в агентство.", entering: "Входим…",
    phoneNeeded: "Сначала добавьте номер телефона в профиле.",
    saved: "Сохранено.", theme: "Тема", themeLight: "Светлая", themeDark: "Тёмная",
    language: "Язык", save: "Сохранить", myProfile: "Мой профиль",
    editProfile: "Личные данные", agenciesActions: "Агентства",
  },
  uz: {
    chooseLang: "Tilni tanlang", next: "Keyingi",
    getAcquainted: "Keling, tanishamiz",
    profileSub: "Bu sizning shaxsiy kartangiz — barcha agentliklarda siz bilan.",
    firstName: "Ism", lastName: "Familiya", phone: "Telefon raqami",
    sharePhone: "Telegramdan raqamni ulashish",
    phoneHint: "Raqamni keyinroq qoldirsangiz boʻladi — u faqat agentlik ochganda kerak.",
    change: "Oʻzgartirish", continueBtn: "Davom etish",
    greeting: "Xush kelibsiz", noPhone: "raqam kiritilmagan",
    home: "Asosiy", settings: "Sozlamalar", profile: "Profil",
    myAgencies: "Mening agentliklarim", add: "Qoʻshish",
    noAgenciesTitle: "Hozircha yakkasiz",
    noAgenciesSub: "Oʻz agentligingizni oching yoki taklif kodi bilan qoʻshiling.",
    createAgency: "Agentlik ochish", joinByCode: "Kod bilan qoʻshilish",
    role_admin: "bosh admin", role_agent: "agent",
    agencyNamePrompt: "Agentlik nomi:", codePrompt: "Taklif kodi:",
    joined: "Agentlikka qoʻshildingiz.", entering: "Kirilmoqda…",
    phoneNeeded: "Avval profilga telefon raqamini qoʻshing.",
    saved: "Saqlandi.", theme: "Mavzu", themeLight: "Yorugʻ", themeDark: "Tungi",
    language: "Til", save: "Saqlash", myProfile: "Mening profilim",
    editProfile: "Shaxsiy maʼlumotlar", agenciesActions: "Agentliklar",
  },
  en: {
    chooseLang: "Choose language", next: "Next",
    getAcquainted: "Let’s get acquainted",
    profileSub: "This is your personal card — it stays with you across agencies.",
    firstName: "First name", lastName: "Last name", phone: "Phone number",
    sharePhone: "Share number from Telegram",
    phoneHint: "You can add the number later — it’s only required when creating an agency.",
    change: "Change", continueBtn: "Continue",
    greeting: "Welcome back", noPhone: "no number set",
    home: "Home", settings: "Settings", profile: "Profile",
    myAgencies: "My agencies", add: "Add",
    noAgenciesTitle: "You’re on your own for now",
    noAgenciesSub: "Create your own agency or join an existing one with an invite code.",
    createAgency: "Create agency", joinByCode: "Join by code",
    role_admin: "main admin", role_agent: "agent",
    agencyNamePrompt: "Agency name:", codePrompt: "Invite code:",
    joined: "You joined the agency.", entering: "Entering…",
    phoneNeeded: "Add a phone number in your profile first.",
    saved: "Saved.", theme: "Theme", themeLight: "Light", themeDark: "Dark",
    language: "Language", save: "Save", myProfile: "My profile",
    editProfile: "Personal details", agenciesActions: "Agencies",
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
function onboardKey(u?: UserProfile | null): string {
  return "pa_onboarded_" + (u?.telegram_id ?? "x");
}

// ── Верхнеуровневый вход ──────────────────────────────────────────────────────
export function PersonalApp({ onEnterAgency }: { onEnterAgency: (data: AuthResponse) => void }) {
  const { user } = useApp();
  const [onboarded, setOnboarded] = useState(() => !!localStorage.getItem(onboardKey(user)));

  if (!onboarded) {
    return (
      <Onboarding
        onDone={() => {
          localStorage.setItem(onboardKey(user), "1");
          setOnboarded(true);
        }}
      />
    );
  }
  return <Hub onEnterAgency={onEnterAgency} />;
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

  const langOpt = (code: Lang, flag: string, label: string) => (
    <button
      key={code}
      onClick={() => { haptic("light"); setLang(code); }}
      className={
        "w-full flex items-center gap-3.5 p-4 rounded-2xl border-2 text-left transition active:scale-[.99] " +
        (lang === code ? "border-primary shadow-[0_0_0_4px_var(--ring)] bg-primary-soft" : "border-line bg-card")
      }
    >
      <span className="text-2xl">{flag}</span>
      <span className="font-extrabold flex-1">{label}</span>
      {lang === code && <span className="text-primary font-extrabold">✓</span>}
    </button>
  );

  async function shareContact() {
    const p = await requestContact();
    if (p) setPhone(p);
  }

  async function finish() {
    if (!first.trim() || busy) return;
    setBusy(true);
    const r = await api<UserProfile>("/api/v1/auth/me", {
      method: "PATCH",
      body: { first_name: first.trim(), last_name: last.trim(), language: lang },
    });
    if (!r.ok || !r.data) { setBusy(false); toast(errText(r.data, r.status), "err"); return; }
    let updated = r.data;
    const cleanPhone = phone.trim();
    if (cleanPhone && cleanPhone !== (user?.phone || "")) {
      const rp = await api<UserProfile>("/api/v1/auth/me/phone", { method: "POST", body: { phone: cleanPhone } });
      if (rp.ok && rp.data) updated = rp.data;
      else toast(errText(rp.data, rp.status), "err");
    }
    setUser(updated);
    setBusy(false);
    onDone();
  }

  if (step === "lang") {
    return (
      <div className="fixed left-0 right-0 bottom-0 flex flex-col" style={{ top: "var(--tg-top-inset, 0px)" }}>
        <div className="flex-1 min-h-0 overflow-y-auto px-4 pt-10 w-full max-w-[560px] mx-auto animate-fade-up">
          <div className="text-center mb-6">
            <div className="mx-auto mb-4 w-16 h-16 rounded-2xl flex items-center justify-center text-white shadow-glow" style={{ background: "var(--grad)" }}>
              <Building2 size={30} />
            </div>
            <h1 className="text-[26px] font-extrabold tracking-tight">Realty <span className="text-primary">AI</span></h1>
            <p className="text-muted text-sm mt-1.5">{s.chooseLang}</p>
          </div>
          <div className="space-y-2.5">
            {langOpt("ru", "🇷🇺", "Русский")}
            {langOpt("uz", "🇺🇿", "Oʻzbekcha")}
            {langOpt("en", "🇬🇧", "English")}
          </div>
        </div>
        <div className="shrink-0 w-full max-w-[560px] mx-auto px-4 pt-2 pb-[calc(16px+env(safe-area-inset-bottom,0px))]">
          <Button full onClick={() => setStep("profile")}>{s.next}</Button>
        </div>
      </div>
    );
  }

  const shared = !!phone;
  return (
    <div className="fixed left-0 right-0 bottom-0 flex flex-col" style={{ top: "var(--tg-top-inset, 0px)" }}>
      <div className="flex-1 min-h-0 overflow-y-auto px-4 pt-8 w-full max-w-[560px] mx-auto animate-fade-up">
        <h1 className="text-[24px] font-extrabold tracking-tight">{s.getAcquainted}</h1>
        <p className="text-muted text-sm mt-1.5">{s.profileSub}</p>
        <Field label={s.firstName}><Input value={first} onChange={(e) => setFirst(e.target.value)} placeholder="Азиз" /></Field>
        <Field label={s.lastName}><Input value={last} onChange={(e) => setLast(e.target.value)} placeholder="Каримов" /></Field>
        <Field label={s.phone}>
          {shared ? (
            <div className="flex items-center gap-2.5">
              <Input value={phone} onChange={(e) => setPhone(e.target.value)} inputMode="tel" />
              <Button variant="soft" size="sm" onClick={shareContact}>{s.change}</Button>
            </div>
          ) : (
            <Button variant="ghost" full onClick={shareContact}>📲 {s.sharePhone}</Button>
          )}
        </Field>
        <p className="text-muted text-[13px] mt-2 leading-relaxed">{s.phoneHint}</p>
      </div>
      <div className="shrink-0 w-full max-w-[560px] mx-auto px-4 pt-2 pb-[calc(16px+env(safe-area-inset-bottom,0px))]">
        <Button full disabled={!first.trim() || busy} onClick={finish}>{busy ? "…" : s.continueBtn}</Button>
      </div>
    </div>
  );
}

// ── Хаб с нижней панелью (Главная / Настройки / Профиль) ──────────────────────
function Hub({ onEnterAgency }: { onEnterAgency: (data: AuthResponse) => void }) {
  const s = useStr();
  const [tab, setTab] = useState<"home" | "settings" | "profile">("home");
  const [memberships, setMemberships] = useState<Membership[] | null>(null);
  const [entering, setEntering] = useState(false);
  const { user, toast } = useApp();

  const load = useCallback(async () => {
    const r = await api<Membership[]>("/api/v1/auth/memberships");
    setMemberships(r.ok && r.data ? r.data : []);
  }, []);
  useEffect(() => { void load(); }, [load]);

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
    if (!user?.phone) { toast(s.phoneNeeded, "warn"); setTab("profile"); return; }
    const has = (memberships?.length || 0) > 0;
    const fullName = [user.first_name, user.last_name].filter(Boolean).join(" ") || user.full_name || "";
    const r = has
      ? await api<AuthResponse>("/api/v1/agencies/open", { method: "POST", body: { name, phone: user.phone } })
      : await api<AuthResponse>("/api/v1/agencies/register", { method: "POST", body: { init_data: getInitData(), name, owner_name: fullName, phone: user.phone } });
    if (r.ok && r.data) onEnterAgency(r.data);
    else toast(errText(r.data, r.status), "err");
  }

  async function joinByCode() {
    const code = window.prompt(s.codePrompt, "")?.trim();
    if (!code) return;
    const r = await api<AuthResponse>("/api/v1/invites/redeem", { method: "POST", body: { init_data: getInitData(), code } });
    if (r.ok && r.data) { toast(s.joined, "ok"); void load(); }
    else toast(errText(r.data, r.status), "err");
  }

  const tabBtn = (id: "home" | "settings" | "profile", icon: React.ReactNode, label: string) => (
    <button
      onClick={() => { if (tab !== id) haptic(); setTab(id); }}
      className={"flex flex-col items-center gap-1 px-2 py-1 min-w-[64px] cursor-pointer transition-colors active:scale-95 " + (tab === id ? "text-primary" : "text-muted")}
    >
      <span className={"flex items-center justify-center w-11 h-7 rounded-full transition-colors " + (tab === id ? "bg-primary-soft" : "")}>{icon}</span>
      <span className="text-[10.5px] font-bold leading-none">{label}</span>
    </button>
  );

  return (
    <div className="fixed left-0 right-0 bottom-0 flex flex-col" style={{ top: "var(--tg-top-inset, 0px)" }}>
      {entering && (
        <div className="fixed inset-0 z-50 flex flex-col items-center justify-center gap-3" style={{ background: "color-mix(in srgb, var(--bg) 82%, transparent)" }}>
          <Spinner /><div className="text-muted text-sm">{s.entering}</div>
        </div>
      )}
      <div className="flex-1 min-h-0 overflow-y-auto overflow-x-hidden">
        {tab === "home" && <HomeTab s={s} user={user} memberships={memberships} onEnter={enter} onCreate={createAgency} onJoin={joinByCode} />}
        {tab === "settings" && <SettingsTab s={s} onCreate={createAgency} onJoin={joinByCode} />}
        {tab === "profile" && <ProfileTab s={s} />}
      </div>
      <nav className="shrink-0 z-40 glass border-t border-line px-3 pt-2 pb-[calc(8px+env(safe-area-inset-bottom,0px))]">
        <div className="max-w-[560px] mx-auto flex items-end justify-around">
          {tabBtn("home", <HomeIcon size={22} />, s.home)}
          {tabBtn("settings", <SettingsIcon size={22} />, s.settings)}
          {tabBtn("profile", <UserIcon size={22} />, s.profile)}
        </div>
      </nav>
    </div>
  );
}

// ── Вкладка «Главная» ─────────────────────────────────────────────────────────
function HomeTab({ s, user, memberships, onEnter, onCreate, onJoin }: {
  s: Record<string, string>; user: UserProfile | null; memberships: Membership[] | null;
  onEnter: (id: number) => void; onCreate: () => void; onJoin: () => void;
}) {
  const heroName = [user?.first_name, user?.last_name].filter(Boolean).join(" ") || user?.full_name || "—";
  const has = (memberships?.length || 0) > 0;
  return (
    <div className="max-w-[560px] mx-auto px-3.5 pt-3.5 pb-4 animate-fade-up">
      <div className="rounded-xl3 px-5 py-5 text-white overflow-hidden" style={{ background: "var(--grad-hero)", boxShadow: "0 16px 40px rgba(52,31,163,.30)" }}>
        <div className="flex items-center gap-3.5">
          <div className="w-14 h-14 shrink-0 rounded-2xl bg-white/20 border border-white/40 backdrop-blur flex items-center justify-center text-xl font-extrabold">
            {initials(user?.first_name || user?.full_name, user?.last_name)}
          </div>
          <div className="min-w-0">
            <div className="text-[13px] opacity-85">{s.greeting} 👋</div>
            <div className="text-[20px] font-extrabold leading-tight truncate">{heroName}</div>
            <div className="text-[13px] opacity-85">{user?.phone || s.noPhone}</div>
          </div>
        </div>
      </div>
      <div className="pt-4">
        {memberships === null ? (
          <Spinner />
        ) : has ? (
          <>
            <div className="flex items-center justify-between mt-1 mx-0.5 mb-2.5">
              <span className="text-[14px] font-extrabold">{s.myAgencies}</span>
              <Button variant="soft" size="sm" onClick={onCreate}><Plus size={15} /> {s.add}</Button>
            </div>
            <div className="space-y-2.5">
              {memberships!.map((m) => {
                const admin = m.is_owner || m.role === "agency_admin";
                return (
                  <button key={m.agency_id} onClick={() => onEnter(m.agency_id)}
                    className="w-full flex items-center gap-3 p-3.5 rounded-xl2 bg-card border border-line shadow-soft text-left active:scale-[.985] transition">
                    <span className="w-11 h-11 rounded-xl bg-primary-soft text-primary flex items-center justify-center font-extrabold shrink-0">{agShort(m.agency_name)}</span>
                    <span className="min-w-0">
                      <span className="block font-extrabold truncate">{m.project_name || m.agency_name}</span>
                      <span className={"inline-block mt-1 px-2.5 py-0.5 rounded-full text-[11px] font-extrabold " + (admin ? "bg-blue-500/15 text-blue-600 dark:text-blue-400" : "bg-slate-500/15 text-slate-600 dark:text-slate-300")}>
                        {admin ? s.role_admin : s.role_agent}
                      </span>
                    </span>
                    <ChevronRight size={18} className="ml-auto text-muted shrink-0" />
                  </button>
                );
              })}
            </div>
          </>
        ) : (
          <Card className="text-center py-8 px-4">
            <div className="mx-auto mb-3 w-16 h-16 rounded-2xl bg-primary-soft text-primary flex items-center justify-center text-3xl">🏢</div>
            <div className="text-[16px] font-extrabold">{s.noAgenciesTitle}</div>
            <p className="text-[13px] text-muted mt-1.5 leading-relaxed max-w-[300px] mx-auto">{s.noAgenciesSub}</p>
            <div className="space-y-2.5 mt-5">
              <Button full onClick={onCreate}><Plus size={16} /> {s.createAgency}</Button>
              <Button variant="ghost" full onClick={onJoin}><KeyRound size={16} /> {s.joinByCode}</Button>
            </div>
          </Card>
        )}
      </div>
    </div>
  );
}

// ── Вкладка «Настройки» ───────────────────────────────────────────────────────
function SettingsTab({ s, onCreate, onJoin }: { s: Record<string, string>; onCreate: () => void; onJoin: () => void }) {
  const { lang, setLang, theme, setTheme } = useApp();
  const langBtn = (c: Lang, label: string) => (
    <Button variant={lang === c ? "primary" : "ghost"} size="sm" onClick={() => setLang(c)}>{label}</Button>
  );
  return (
    <div className="max-w-[560px] mx-auto px-3.5 py-5 animate-fade-up">
      <h1 className="text-[22px] font-extrabold tracking-tight mx-0.5 mb-4">{s.settings}</h1>
      <Card>
        <div className="text-[12px] font-bold text-muted mb-2">{s.language}</div>
        <div className="flex gap-2">{langBtn("ru", "RU")}{langBtn("uz", "UZ")}{langBtn("en", "EN")}</div>
        <div className="text-[12px] font-bold text-muted mt-4 mb-2">{s.theme}</div>
        <Button variant="ghost" size="sm" onClick={() => setTheme(theme === "light" ? "dark" : "light")}>
          {theme === "light" ? "🌙 " + s.themeDark : "☀️ " + s.themeLight}
        </Button>
      </Card>
      <Card className="mt-3">
        <div className="text-[12px] font-bold text-muted mb-2">{s.agenciesActions}</div>
        <div className="space-y-2.5">
          <Button full size="sm" onClick={onCreate}><Plus size={15} /> {s.createAgency}</Button>
          <Button variant="ghost" full size="sm" onClick={onJoin}><KeyRound size={15} /> {s.joinByCode}</Button>
        </div>
      </Card>
    </div>
  );
}

// ── Вкладка «Профиль» ─────────────────────────────────────────────────────────
function ProfileTab({ s }: { s: Record<string, string> }) {
  const { user, setUser, toast } = useApp();
  const [first, setFirst] = useState(user?.first_name || "");
  const [last, setLast] = useState(user?.last_name || "");
  const [phone, setPhone] = useState(user?.phone || "");
  const [busy, setBusy] = useState(false);

  async function shareContact() {
    const p = await requestContact();
    if (p) setPhone(p);
  }
  async function save() {
    if (busy) return;
    setBusy(true);
    const r = await api<UserProfile>("/api/v1/auth/me", { method: "PATCH", body: { first_name: first.trim(), last_name: last.trim() } });
    let updated = r.ok && r.data ? r.data : null;
    if (!updated) { setBusy(false); toast(errText(r.data, r.status), "err"); return; }
    const cleanPhone = phone.trim();
    if (cleanPhone && cleanPhone !== (user?.phone || "")) {
      const rp = await api<UserProfile>("/api/v1/auth/me/phone", { method: "POST", body: { phone: cleanPhone } });
      if (rp.ok && rp.data) updated = rp.data;
      else { toast(errText(rp.data, rp.status), "err"); }
    }
    setUser(updated);
    setBusy(false);
    toast(s.saved, "ok");
  }

  return (
    <div className="max-w-[560px] mx-auto px-3.5 pt-3.5 pb-4 animate-fade-up">
      <div className="rounded-xl3 px-5 py-5 text-white overflow-hidden" style={{ background: "var(--grad-hero)", boxShadow: "0 16px 40px rgba(52,31,163,.30)" }}>
        <div className="flex items-center gap-3.5">
          <div className="w-16 h-16 shrink-0 rounded-2xl bg-white/20 border border-white/40 backdrop-blur flex items-center justify-center text-2xl font-extrabold">
            {initials(user?.first_name || user?.full_name, user?.last_name)}
          </div>
          <div className="min-w-0">
            <div className="text-[20px] font-extrabold leading-tight truncate">{[user?.first_name, user?.last_name].filter(Boolean).join(" ") || user?.full_name || "—"}</div>
            <div className="text-[13px] opacity-85">{s.myProfile}</div>
          </div>
        </div>
      </div>
      <div className="pt-4">
        <Card>
          <div className="text-[12px] font-bold text-muted mb-2">{s.editProfile}</div>
          <Field label={s.firstName}><Input value={first} onChange={(e) => setFirst(e.target.value)} /></Field>
          <Field label={s.lastName}><Input value={last} onChange={(e) => setLast(e.target.value)} /></Field>
          <Field label={s.phone}>
            <div className="flex items-center gap-2.5">
              <Input value={phone} onChange={(e) => setPhone(e.target.value)} inputMode="tel" placeholder={s.noPhone} />
              <Button variant="soft" size="sm" onClick={shareContact}>📲</Button>
            </div>
          </Field>
          <Button full className="mt-4" disabled={busy} onClick={save}>{busy ? "…" : s.save}</Button>
        </Card>
      </div>
    </div>
  );
}
