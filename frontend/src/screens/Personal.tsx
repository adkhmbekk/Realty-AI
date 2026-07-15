// Личное пространство (юзер-центричная модель, 2026-07).
//
// Онбординг (язык → имя/фамилия → номер) + личный хаб с нижней панелью
// (Главная / Настройки / Профиль). Дизайн — по прототипу, на дизайн-системе
// приложения. Встройка в App.tsx: фаза "personal" рендерит <PersonalApp/>.
//
// Онбординг показываем ОДИН РАЗ (флаг в localStorage) — existing-юзеры (у кого
// имя уже заполнено бэкфиллом) тоже проходят его при первом входе в новую версию.
import React, { useCallback, useEffect, useState } from "react";
import { Home as HomeIcon, Settings as SettingsIcon, User as UserIcon, Plus, KeyRound, ChevronRight, Building2, Languages, Moon } from "lucide-react";
import { useApp } from "../store";
import { useNav } from "../nav";
import { api, errText } from "../api";
import { getInitData, requestContact, haptic, isNativeApp } from "../telegram";
import { Button, Card, Field, Input, Spinner, Segmented, Switch } from "../components/ui";
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
    phoneHint: "Имя, фамилия и номер обязательны для первого входа.",
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
    addAgencyTitle: "Добавить агентство",
    fillAllRequired: "Заполните имя, фамилию и номер телефона.",
    edit: "Редактировать", cancel: "Отмена", notFilled: "не заполнено",
  },
  uz: {
    chooseLang: "Tilni tanlang", next: "Keyingi",
    getAcquainted: "Keling, tanishamiz",
    profileSub: "Bu sizning shaxsiy kartangiz — barcha agentliklarda siz bilan.",
    firstName: "Ism", lastName: "Familiya", phone: "Telefon raqami",
    sharePhone: "Telegramdan raqamni ulashish",
    phoneHint: "Ism, familiya va raqam birinchi kirishda majburiy.",
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
    addAgencyTitle: "Agentlik qoʻshish",
    fillAllRequired: "Ism, familiya va telefon raqamini toʻldiring.",
    edit: "Tahrirlash", cancel: "Bekor qilish", notFilled: "toʻldirilmagan",
  },
  en: {
    chooseLang: "Choose language", next: "Next",
    getAcquainted: "Let’s get acquainted",
    profileSub: "This is your personal card — it stays with you across agencies.",
    firstName: "First name", lastName: "Last name", phone: "Phone number",
    sharePhone: "Share number from Telegram",
    phoneHint: "Name, surname and phone are required to get started.",
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
    addAgencyTitle: "Add agency",
    fillAllRequired: "Fill in name, surname and phone number.",
    edit: "Edit", cancel: "Cancel", notFilled: "not filled",
  },
};

function useStr() {
  const { lang } = useApp();
  return STR[lang] || STR.ru;
}

// Открыта ли клавиатура (прячем нижнюю панель, чтобы не «всплывала» на клавиатуру).
function useKeyboardOpen() {
  const [open, setOpen] = useState(false);
  useEffect(() => {
    const vv = window.visualViewport;
    if (!vv) return;
    const onResize = () => setOpen(window.innerHeight - vv.height > 160);
    vv.addEventListener("resize", onResize);
    onResize();
    return () => vv.removeEventListener("resize", onResize);
  }, []);
  return open;
}

function initials(a?: string | null, b?: string | null): string {
  // Берём по одной букве; indexing пустой строки даёт undefined (в квадратике
  // вылезало «undefined», когда фамилия пуста) — поэтому падаем на "".
  const first = (a || "").trim()[0] || "";
  const second = (b || "").trim()[0] || "";
  return (first + second).toUpperCase() || "?";
}
function agShort(name: string): string {
  return name.trim().split(/\s+/).slice(0, 2).map((w) => w[0] || "").join("").toUpperCase();
}
function onboardKey(u?: UserProfile | null): string {
  // Привязка к id АККАУНТА (а не telegram_id): после удаления/архивации юзера его
  // Telegram освобождается и при следующем входе заводится НОВЫЙ аккаунт с ДРУГИМ
  // id, но тем же telegram_id. Если ключ по telegram_id — флаг «уже онбординил»
  // от старого аккаунта подхватывался, онбординг пропускался и новый профиль
  // оставался пустым. По id аккаунта такого нет — человек проходит онбординг заново.
  return "pa_onboarded_" + (u?.id ?? "x");
}

// ── Верхнеуровневый вход ──────────────────────────────────────────────────────
export function PersonalApp({ onEnterAgency }: { onEnterAgency: (data: AuthResponse) => void }) {
  const { user } = useApp();
  // «Онбординг пройден», если есть флаг ДЛЯ ЭТОГО аккаунта ИЛИ профиль реально
  // заполнен (имя + телефон). Опора на реальные данные — подстраховка: новый
  // (после архивации) аккаунт с пустым профилем не проскочит онбординг, даже если
  // в браузере остался чужой флаг.
  const profileFilled = !!(user?.first_name?.trim() && user?.phone?.trim());
  const [onboarded, setOnboarded] = useState(
    () => !!localStorage.getItem(onboardKey(user)) || profileFilled
  );

  // Онбординг — только у НОВЫХ юзеров (role='user' = личный аккаунт, ещё не в
  // агентстве). Существующие (agency_admin/agent) сразу видят личный кабинет.
  // localStorage-флаг лишь подстраховка, чтобы не переспрашивать нового юзера.
  const needsOnboarding = user?.role === "user" && !onboarded;
  if (needsOnboarding) {
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
          {isNativeApp() ? (
            // Нативное приложение: обычный ввод номера (Telegram-контакта тут нет).
            // Подтверждение SMS — отдельным этапом.
            <Input value={phone} onChange={(e) => setPhone(e.target.value)} inputMode="tel" placeholder="+998 90 123 45 67" />
          ) : shared ? (
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
        <Button full disabled={!first.trim() || !last.trim() || !phone.trim() || busy} onClick={finish}>{busy ? "…" : s.continueBtn}</Button>
      </div>
    </div>
  );
}

// Панель вкладки внутри хаба-шаблона. Ключевое: НЕ размонтируем неактивные
// вкладки (display:none вместо удаления из дерева) — так сохраняется и введённый
// текст, и позиция прокрутки. Каждая панель листается сама по себе (absolute
// inset-0 + overflow-y-auto), поэтому длинный список агентств доступен целиком.
function TabPane({ active, children }: { active: boolean; children: React.ReactNode }) {
  return (
    <div
      className={"absolute inset-0 overflow-y-auto overflow-x-hidden " + (active ? "" : "hidden")}
      aria-hidden={!active}
    >
      {children}
    </div>
  );
}

// ── Хаб с нижней панелью (Главная / Настройки / Профиль) ──────────────────────
function Hub({ onEnterAgency }: { onEnterAgency: (data: AuthResponse) => void }) {
  const s = useStr();
  const kb = useKeyboardOpen();
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
      {/* Брендовая шапка — как в интерфейсе агентства (App.tsx Shell), чтобы личный
          кабинет не выглядел «неполноценным». Логотип + «Realty AI», фиксирована. */}
      <div className="shrink-0 w-full max-w-[560px] mx-auto px-3.5 pt-3.5">
        <header className="flex items-center gap-3 min-h-[40px] mb-2">
          <div className="flex items-center gap-2.5">
            <span className="w-8 h-8 rounded-[10px] flex items-center justify-center text-white shadow-glow" style={{ background: "var(--grad)" }}>
              <Building2 size={18} />
            </span>
            <span className="text-[18px] font-extrabold tracking-tight">
              Realty <span className="text-primary">AI</span>
            </span>
          </div>
        </header>
      </div>
      <div className="flex-1 min-h-0 relative">
        <TabPane active={tab === "home"}>
          <HomeTab s={s} user={user} memberships={memberships} onEnter={enter} onCreate={createAgency} onJoin={joinByCode} />
        </TabPane>
        <TabPane active={tab === "settings"}>
          <SettingsTab s={s} onCreate={createAgency} onJoin={joinByCode} />
        </TabPane>
        <TabPane active={tab === "profile"}>
          <ProfileTab s={s} />
        </TabPane>
      </div>
      {!kb && (
        <nav className="shrink-0 z-40 glass border-t border-line px-3 pt-2 pb-[calc(8px+env(safe-area-inset-bottom,0px))]">
          <div className="max-w-[560px] mx-auto flex items-end justify-around">
            {tabBtn("home", <HomeIcon size={22} />, s.home)}
            {tabBtn("settings", <SettingsIcon size={22} />, s.settings)}
            {tabBtn("profile", <UserIcon size={22} />, s.profile)}
          </div>
        </nav>
      )}
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
  // Выбор действия по кнопке «Добавить»: создать агентство ИЛИ вступить по коду.
  const [showChoice, setShowChoice] = useState(false);
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
              <Button variant="soft" size="sm" onClick={() => { haptic(); setShowChoice(true); }}><Plus size={15} /> {s.add}</Button>
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

      {/* Выбор действия по «Добавить»: создать агентство или вступить по коду.
          Нижняя «шторка» — тап по затемнению закрывает. */}
      {showChoice && (
        <div
          className="fixed inset-0 z-50 flex items-end justify-center"
          style={{ background: "color-mix(in srgb, var(--bg) 68%, transparent)" }}
          onClick={() => setShowChoice(false)}
        >
          <div
            className="w-full max-w-[560px] bg-card border-t border-line rounded-t-xl3 px-4 pt-3 pb-[calc(18px+env(safe-area-inset-bottom,0px))] animate-fade-up"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="w-10 h-1 rounded-full bg-line mx-auto mb-3.5" />
            <div className="text-[15px] font-extrabold text-center mb-3.5">{s.addAgencyTitle}</div>
            <div className="space-y-2.5">
              <Button full onClick={() => { setShowChoice(false); onCreate(); }}>
                <Plus size={16} /> {s.createAgency}
              </Button>
              <Button variant="ghost" full onClick={() => { setShowChoice(false); onJoin(); }}>
                <KeyRound size={16} /> {s.joinByCode}
              </Button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

// ── Вкладка «Настройки» ───────────────────────────────────────────────────────
function SettingsTab({ s, onCreate, onJoin }: { s: Record<string, string>; onCreate: () => void; onJoin: () => void }) {
  const { lang, setLang, theme, setTheme } = useApp();
  return (
    <div className="max-w-[560px] mx-auto px-3.5 py-5 animate-fade-up">
      <h1 className="text-[24px] font-extrabold tracking-tight mx-0.5 mb-4">{s.settings}</h1>

      <Card>
        <div className="flex items-center gap-2.5 mb-3">
          <span className="w-8 h-8 rounded-[10px] bg-primary-soft text-primary flex items-center justify-center"><Languages size={17} /></span>
          <span className="font-extrabold">{s.language}</span>
        </div>
        <Segmented<Lang>
          value={lang}
          onChange={setLang}
          options={[{ value: "ru", label: "Русский" }, { value: "uz", label: "Oʻzbek" }, { value: "en", label: "English" }]}
        />
      </Card>

      <Card className="mt-3">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2.5">
            <span className="w-8 h-8 rounded-[10px] bg-primary-soft text-primary flex items-center justify-center"><Moon size={17} /></span>
            <div>
              <div className="font-extrabold">{s.theme}</div>
              <div className="text-[12px] text-muted">{theme === "dark" ? s.themeDark : s.themeLight}</div>
            </div>
          </div>
          <Switch checked={theme === "dark"} onChange={(v) => setTheme(v ? "dark" : "light")} label={s.theme} />
        </div>
      </Card>

      <Card className="mt-3">
        <div className="flex items-center gap-2.5 mb-3">
          <span className="w-8 h-8 rounded-[10px] bg-primary-soft text-primary flex items-center justify-center"><Building2 size={17} /></span>
          <span className="font-extrabold">{s.agenciesActions}</span>
        </div>
        <div className="space-y-2.5">
          <Button full onClick={onCreate}><Plus size={16} /> {s.createAgency}</Button>
          <Button variant="ghost" full onClick={onJoin}><KeyRound size={16} /> {s.joinByCode}</Button>
        </div>
      </Card>
    </div>
  );
}

// ── Вкладка «Профиль» ─────────────────────────────────────────────────────────
// Показ данных (только чтение) + кнопка «Редактировать». Форма ввода открывается
// по кнопке — так поля не выглядят «пустыми полями ввода», а именно данными.
// Если профиль неполный (нет имени/фамилии/номера) — сразу открываем форму.
function ProfileTab({ s }: { s: Record<string, string> }) {
  const { user, setUser, toast } = useApp();
  const filledOk = !!(user?.first_name?.trim() && user?.last_name?.trim() && user?.phone?.trim());
  const [editing, setEditing] = useState(!filledOk);
  const [first, setFirst] = useState(user?.first_name || "");
  const [last, setLast] = useState(user?.last_name || "");
  const [phone, setPhone] = useState(user?.phone || "");
  const [busy, setBusy] = useState(false);

  // Когда меняется user (после сохранения / возврата из агентства) и мы НЕ в
  // режиме правки — подтягиваем актуальные значения в поля.
  useEffect(() => {
    if (!editing) {
      setFirst(user?.first_name || "");
      setLast(user?.last_name || "");
      setPhone(user?.phone || "");
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [user?.first_name, user?.last_name, user?.phone]);

  // Все поля обязательны: имя, фамилия и номер. Нельзя сохранить профиль,
  // стерев уже введённые данные (симметрично обязательному онбордингу).
  const complete = !!(first.trim() && last.trim() && phone.trim());
  const fullName = [user?.first_name, user?.last_name].filter(Boolean).join(" ") || user?.full_name || "—";

  async function shareContact() {
    const p = await requestContact();
    if (p) setPhone(p);
  }
  function startEdit() {
    setFirst(user?.first_name || "");
    setLast(user?.last_name || "");
    setPhone(user?.phone || "");
    setEditing(true);
  }
  function cancelEdit() {
    setFirst(user?.first_name || "");
    setLast(user?.last_name || "");
    setPhone(user?.phone || "");
    setEditing(false);
  }
  async function save() {
    if (busy) return;
    if (!complete) { toast(s.fillAllRequired, "err"); return; }
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
    setEditing(false);
    toast(s.saved, "ok");
  }

  const DataRow = ({ label, value }: { label: string; value?: string | null }) => (
    <div className="flex items-center justify-between gap-3 py-2.5 border-b border-line last:border-0">
      <span className="text-[13px] text-muted shrink-0">{label}</span>
      <span className={"text-[14px] font-bold text-right truncate " + (value ? "" : "text-muted font-normal italic")}>
        {value || s.notFilled}
      </span>
    </div>
  );

  return (
    <div className="max-w-[560px] mx-auto px-3.5 pt-3.5 pb-4 animate-fade-up">
      <div className="rounded-xl3 px-5 py-5 text-white overflow-hidden" style={{ background: "var(--grad-hero)", boxShadow: "0 16px 40px rgba(52,31,163,.30)" }}>
        <div className="flex items-center gap-3.5">
          <div className="w-16 h-16 shrink-0 rounded-2xl bg-white/20 border border-white/40 backdrop-blur flex items-center justify-center text-2xl font-extrabold">
            {initials(user?.first_name || user?.full_name, user?.last_name)}
          </div>
          <div className="min-w-0">
            <div className="text-[20px] font-extrabold leading-tight truncate">{fullName}</div>
            <div className="text-[13px] opacity-85">{s.myProfile}</div>
          </div>
        </div>
      </div>
      <div className="pt-4">
        <Card>
          <div className="text-[12px] font-bold text-muted mb-2">{s.editProfile}</div>
          {editing ? (
            <>
              <Field label={s.firstName}><Input value={first} onChange={(e) => setFirst(e.target.value)} /></Field>
              <Field label={s.lastName}><Input value={last} onChange={(e) => setLast(e.target.value)} /></Field>
              <Field label={s.phone}>
                <div className="flex items-center gap-2.5">
                  <Input value={phone} onChange={(e) => setPhone(e.target.value)} inputMode="tel" placeholder={s.noPhone} />
                  {!isNativeApp() && <Button variant="soft" size="sm" onClick={shareContact}>📲</Button>}
                </div>
              </Field>
              {!complete && (
                <p className="text-[12px] text-muted mt-1">{s.fillAllRequired}</p>
              )}
              <div className={"grid gap-2 mt-4 " + (filledOk ? "grid-cols-2" : "grid-cols-1")}>
                {filledOk && <Button variant="ghost" disabled={busy} onClick={cancelEdit}>{s.cancel}</Button>}
                <Button disabled={busy || !complete} onClick={save}>{busy ? "…" : s.save}</Button>
              </div>
            </>
          ) : (
            <>
              <DataRow label={s.firstName} value={user?.first_name} />
              <DataRow label={s.lastName} value={user?.last_name} />
              <DataRow label={s.phone} value={user?.phone} />
              <Button variant="soft" full className="mt-4" onClick={startEdit}>{s.edit}</Button>
            </>
          )}
        </Card>
      </div>
    </div>
  );
}

// ── Обёртки для суперадмина (его хаб внутри Shell) ────────────────────────────
// Суперадмин — тоже юзер: его Настройки и Профиль ИДЕНТИЧНЫ пользовательским.
// Переиспользуем те же SettingsTab/ProfileTab, чтобы интерфейс совпадал 1-в-1.
export function PersonalSettingsScreen() {
  const s = useStr();
  const nav = useNav();
  // Действия с агентствами в настройках ведут на страницу «Мои агентства».
  const go = () => nav.push({ name: "personalAgencies" });
  return <SettingsTab s={s} onCreate={go} onJoin={go} />;
}

export function PersonalProfileScreen() {
  const s = useStr();
  return <ProfileTab s={s} />;
}
