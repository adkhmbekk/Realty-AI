import React, {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import { Lang, makeT, labelHelpers } from "./i18n";
import { setTokenGetter } from "./api";
import { colorScheme, setChromeColors } from "./telegram";
import type { AgencySettings, UserProfile } from "./types";

type Theme = "light" | "dark";
type ToastKind = "info" | "ok" | "warn" | "err";

interface Toast {
  id: number;
  text: string;
  kind: ToastKind;
}

interface AppCtx {
  token: string | null;
  user: UserProfile | null;
  subscriptionActive: boolean | null;
  lang: Lang;
  theme: Theme;
  settings: AgencySettings | null;
  toasts: Toast[];
  t: (k: string) => string;
  L: ReturnType<typeof labelHelpers>;
  setAuth: (token: string, user: UserProfile, subscriptionActive: boolean | null) => void;
  clearAuth: () => void;
  setUser: (u: UserProfile) => void;
  setLang: (l: Lang) => void;
  setTheme: (th: Theme) => void;
  setSettings: (s: AgencySettings | null) => void;
  toast: (text: string, kind?: ToastKind) => void;
}

const Ctx = createContext<AppCtx | null>(null);

export function useApp(): AppCtx {
  const v = useContext(Ctx);
  if (!v) throw new Error("useApp must be used within AppProvider");
  return v;
}

function initialLang(): Lang {
  const s = localStorage.getItem("pa_lang");
  return s === "uz" || s === "en" ? s : "ru";
}

function initialTheme(): Theme {
  const s = localStorage.getItem("pa_theme");
  if (s === "light" || s === "dark") return s;
  return colorScheme() === "dark" ? "dark" : "light";
}

export function AppProvider({ children }: { children: React.ReactNode }) {
  const [token, setToken] = useState<string | null>(null);
  const [user, setUserState] = useState<UserProfile | null>(null);
  const [subscriptionActive, setSubActive] = useState<boolean | null>(null);
  const [lang, setLangState] = useState<Lang>(initialLang);
  const [theme, setThemeState] = useState<Theme>(initialTheme);
  const [settings, setSettings] = useState<AgencySettings | null>(null);
  const [toasts, setToasts] = useState<Toast[]>([]);
  const toastId = useRef(1);

  // Токен для api-клиента.
  const tokenRef = useRef<string | null>(null);
  tokenRef.current = token;
  useEffect(() => {
    setTokenGetter(() => tokenRef.current);
  }, []);

  // Применяем тему к <html> и красим интерфейс Telegram.
  useEffect(() => {
    document.documentElement.classList.toggle("dark", theme === "dark");
    document.documentElement.setAttribute("lang", lang);
    setChromeColors(theme === "dark" ? "#060b16" : "#f4f7fc");
  }, [theme, lang]);

  const t = useMemo(() => makeT(lang), [lang]);
  const L = useMemo(() => labelHelpers(lang, t), [lang, t]);

  const setAuth = useCallback(
    (tk: string, u: UserProfile, sub: boolean | null) => {
      setToken(tk);
      setUserState(u);
      setSubActive(sub);
    },
    []
  );
  const clearAuth = useCallback(() => {
    setToken(null);
    setUserState(null);
    setSubActive(null);
    setSettings(null);
  }, []);
  const setUser = useCallback((u: UserProfile) => setUserState(u), []);

  const setLang = useCallback((l: Lang) => {
    localStorage.setItem("pa_lang", l);
    setLangState(l);
  }, []);
  const setTheme = useCallback((th: Theme) => {
    localStorage.setItem("pa_theme", th);
    setThemeState(th);
  }, []);

  const toast = useCallback((text: string, kind: ToastKind = "info") => {
    const id = toastId.current++;
    setToasts((prev) => [...prev, { id, text, kind }]);
    window.setTimeout(() => {
      setToasts((prev) => prev.filter((x) => x.id !== id));
    }, 2600);
  }, []);

  const value: AppCtx = {
    token,
    user,
    subscriptionActive,
    lang,
    theme,
    settings,
    toasts,
    t,
    L,
    setAuth,
    clearAuth,
    setUser,
    setLang,
    setTheme,
    setSettings,
    toast,
  };

  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}
