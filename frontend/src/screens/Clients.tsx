import React, { useEffect, useState } from "react";
import {
  Bell,
  BellOff,
  Check,
  CheckSquare,
  ChevronRight,
  Coins,
  FileText,
  Handshake,
  Home,
  MessageCircle,
  Pencil,
  Phone,
  Plus,
  RefreshCw,
  Search as SearchIcon,
  Sparkles,
  Trash2,
  UserPlus,
  Users,
  X,
  type LucideIcon,
} from "lucide-react";
import { useApp } from "../store";
import { useNav } from "../nav";
import { api, errText } from "../api";
import {
  Badge,
  Button,
  Card,
  Chips,
  Empty,
  Field,
  Hint,
  Input,
  Segmented,
  Select,
  Spinner,
  Textarea,
} from "../components/ui";
import { CURRENCIES, OBJ_TYPE_VALUES, hasLandArea } from "../i18n";
import type { Client, ClientActivity, ClientRequest, Deal, DictItem, HintItem, Match, SearchParams, Task } from "../types";
import { ApartmentCard } from "./Apartments";
import { fmtDate } from "../utils";
import { confirmDialog, haptic } from "../telegram";

// ── Справочник районов (локально) ───────────────────────────────────
function useDistricts(): DictItem[] {
  const [districts, setDistricts] = useState<DictItem[]>([]);
  useEffect(() => {
    let alive = true;
    api<DictItem[]>("/api/v1/dictionaries?category=district").then((r) => {
      if (alive && r.ok && Array.isArray(r.data)) setDistricts(r.data);
    });
    return () => {
      alive = false;
    };
  }, []);
  return districts;
}

// ── Критерии заявки (контролируемая форма) ──────────────────────────
export type Criteria = {
  deal_type: string;
  types: string[];
  districts: string[];
  rooms_min: string;
  rooms_max: string;
  floor_min: string;
  floor_max: string;
  land_area_min: string;
  land_area_max: string;
  area_min: string;
  area_max: string;
  price_min: string;
  price_max: string;
  currency: string;
  note: string;
};

export function emptyCriteria(): Criteria {
  return {
    deal_type: "sale",
    types: [],
    districts: [],
    rooms_min: "",
    rooms_max: "",
    floor_min: "",
    floor_max: "",
    land_area_min: "",
    land_area_max: "",
    area_min: "",
    area_max: "",
    price_min: "",
    price_max: "",
    currency: "",
    note: "",
  };
}

export function paramsToCriteria(p: SearchParams): Criteria {
  const s = (v: unknown) => (v != null && v !== "" ? String(v) : "");
  return {
    deal_type: (p.deal_type as string) || "sale",
    types: (p.types as string[]) || [],
    districts: (p.districts as string[]) || [],
    rooms_min: s(p.rooms_min),
    rooms_max: s(p.rooms_max),
    floor_min: s(p.floor_min),
    floor_max: s(p.floor_max),
    land_area_min: s(p.land_area_min),
    land_area_max: s(p.land_area_max),
    area_min: s(p.area_min),
    area_max: s(p.area_max),
    price_min: s(p.price_min),
    price_max: s(p.price_max),
    currency: (p.currency as string) || "",
    note: (p.q as string) || "",
  };
}

const numOrU = (v: string): number | undefined => {
  const s = v.trim();
  if (!s) return undefined;
  const n = Number(s.replace(",", "."));
  return Number.isNaN(n) ? undefined : n;
};
const intOrU = (v: string): number | undefined => {
  const s = v.trim();
  if (!s) return undefined;
  const n = parseInt(s, 10);
  return Number.isNaN(n) ? undefined : n;
};

export function criteriaNonEmpty(c: Criteria): boolean {
  return !!(
    c.types.length ||
    c.districts.length ||
    c.rooms_min ||
    c.rooms_max ||
    c.floor_min ||
    c.floor_max ||
    c.land_area_min ||
    c.land_area_max ||
    c.area_min ||
    c.area_max ||
    c.price_min ||
    c.price_max
  );
}

export function criteriaToBody(c: Criteria): Record<string, unknown> {
  const showLand = c.types.some(hasLandArea);
  const showFloor = c.types.length === 0 || c.types.some((t) => !hasLandArea(t));
  const body: Record<string, unknown> = {};
  // Тип сделки заявки всегда передаём (продажа по умолчанию).
  body.deal_type = c.deal_type || "sale";
  if (c.types.length) body.types = c.types;
  if (c.districts.length) body.districts = c.districts;
  if (intOrU(c.rooms_min) != null) body.rooms_min = intOrU(c.rooms_min);
  if (intOrU(c.rooms_max) != null) body.rooms_max = intOrU(c.rooms_max);
  if (showFloor) {
    if (intOrU(c.floor_min) != null) body.floor_min = intOrU(c.floor_min);
    if (intOrU(c.floor_max) != null) body.floor_max = intOrU(c.floor_max);
    // Площадь (квадратура, м²) — для квартир/домов, рядом с этажом.
    if (numOrU(c.area_min) != null) body.area_min = numOrU(c.area_min);
    if (numOrU(c.area_max) != null) body.area_max = numOrU(c.area_max);
  }
  if (showLand) {
    if (numOrU(c.land_area_min) != null) body.land_area_min = numOrU(c.land_area_min);
    if (numOrU(c.land_area_max) != null) body.land_area_max = numOrU(c.land_area_max);
  }
  if (numOrU(c.price_min) != null) body.price_min = numOrU(c.price_min);
  if (numOrU(c.price_max) != null) body.price_max = numOrU(c.price_max);
  if (c.currency) body.currency = c.currency;
  if (c.note.trim()) body.note = c.note.trim();
  return body;
}

// Человекочитаемая подпись заявки («Квартира · Юнусабад · 4–5 · до 120000 USD»).
export function requestLabel(r: ClientRequest, L: ReturnType<typeof useApp>["L"], t: (k: string) => string): string {
  const parts: string[] = [];
  // Тип сделки впереди (аренда/продажа), чтобы агент сразу видел, что ищет клиент.
  parts.push(r.deal_type === "rent" ? t("dealRent") : t("dealSale"));
  if (r.types && r.types.length) parts.push(r.types.map((x) => L.typeLabel(x)).join("/"));
  if (r.districts && r.districts.length) parts.push(r.districts.join(", "));
  const range = (lo?: number | null, hi?: number | null, suf = "") => {
    if (lo != null && hi != null) return (lo === hi ? `${lo}` : `${lo}–${hi}`) + suf;
    if (lo != null) return `${t("from")} ${lo}${suf}`;
    if (hi != null) return `${t("to")} ${hi}${suf}`;
    return null;
  };
  const rooms = range(r.rooms_min, r.rooms_max);
  if (rooms) parts.push(rooms + " " + t("f_rooms").toLowerCase());
  const price = range(r.price_min, r.price_max, r.currency ? " " + r.currency : "");
  if (price) parts.push(price);
  return parts.join(" · ") || t("anyCriteria");
}

export function CriteriaEditor({ value, onChange }: { value: Criteria; onChange: (c: Criteria) => void }) {
  const { t, L } = useApp();
  const districts = useDistricts();
  const set = (k: keyof Criteria, v: string | string[]) => onChange({ ...value, [k]: v });
  const toggle = (k: "types" | "districts", v: string) => {
    const arr = value[k];
    set(k, arr.includes(v) ? arr.filter((x) => x !== v) : [...arr, v]);
  };
  const showLand = value.types.some(hasLandArea);
  const showFloor = value.types.length === 0 || value.types.some((tp) => !hasLandArea(tp));

  return (
    <div>
      {/* Тип сделки заявки: ищет купить или снять. */}
      <div className="mt-2">
        <div className="text-[12px] font-bold text-muted mb-1.5">{t("dealType")}</div>
        <Segmented
          value={(value.deal_type || "sale") as "sale" | "rent"}
          onChange={(v) => set("deal_type", v)}
          options={[
            { value: "sale", label: t("dealSale") },
            { value: "rent", label: t("dealRent") },
          ]}
        />
      </div>
      <div className="mt-3">
        <div className="text-[12px] font-bold text-muted mb-1.5">{t("f_type")}</div>
        <Chips
          options={OBJ_TYPE_VALUES.map((v) => ({ value: v, label: L.typeLabel(v) }))}
          selected={value.types}
          onToggle={(v) => toggle("types", v)}
        />
      </div>
      {districts.length > 0 && (
        <div className="mt-3">
          <div className="text-[12px] font-bold text-muted mb-1.5">{t("f_district")}</div>
          <Chips
            options={districts.map((d) => ({ value: d.value, label: d.value }))}
            selected={value.districts}
            onToggle={(v) => toggle("districts", v)}
          />
        </div>
      )}
      <div className="flex gap-2">
        <div className="flex-1">
          <Field label={t("roomsFrom")}>
            <Input inputMode="numeric" value={value.rooms_min} onChange={(e) => set("rooms_min", e.target.value)} />
          </Field>
        </div>
        <div className="flex-1">
          <Field label={t("to")}>
            <Input inputMode="numeric" value={value.rooms_max} onChange={(e) => set("rooms_max", e.target.value)} />
          </Field>
        </div>
      </div>
      {showFloor && (
        <div className="flex gap-2">
          <div className="flex-1 min-w-0">
            <Field label={t("floorFrom")}>
              <Input inputMode="numeric" value={value.floor_min} onChange={(e) => set("floor_min", e.target.value)} />
            </Field>
          </div>
          <div className="flex-1 min-w-0">
            <Field label={t("to")}>
              <Input inputMode="numeric" value={value.floor_max} onChange={(e) => set("floor_max", e.target.value)} />
            </Field>
          </div>
        </div>
      )}
      {showFloor && (
        <div className="flex gap-2">
          <div className="flex-1 min-w-0">
            <Field label={t("areaFrom")}>
              <Input inputMode="decimal" value={value.area_min} onChange={(e) => set("area_min", e.target.value)} />
            </Field>
          </div>
          <div className="flex-1 min-w-0">
            <Field label={t("to")}>
              <Input inputMode="decimal" value={value.area_max} onChange={(e) => set("area_max", e.target.value)} />
            </Field>
          </div>
        </div>
      )}
      {showLand && (
        <div className="flex gap-2">
          <div className="flex-1 min-w-0">
            <Field label={t("landFrom")}>
              <Input inputMode="decimal" value={value.land_area_min} onChange={(e) => set("land_area_min", e.target.value)} />
            </Field>
          </div>
          <div className="flex-1 min-w-0">
            <Field label={t("to")}>
              <Input inputMode="decimal" value={value.land_area_max} onChange={(e) => set("land_area_max", e.target.value)} />
            </Field>
          </div>
        </div>
      )}
      <div className="flex gap-2">
        <div className="flex-1">
          <Field label={t("priceFrom")}>
            <Input inputMode="numeric" value={value.price_min} onChange={(e) => set("price_min", e.target.value)} />
          </Field>
        </div>
        <div className="flex-1">
          <Field label={t("to")}>
            <Input inputMode="numeric" value={value.price_max} onChange={(e) => set("price_max", e.target.value)} />
          </Field>
        </div>
      </div>
      <Field label={t("priceCurrency")}>
        <Select value={value.currency} onChange={(e) => set("currency", e.target.value)}>
          <option value="">{t("anyCurrency")}</option>
          {CURRENCIES.map((c) => (
            <option key={c} value={c}>
              {c}
            </option>
          ))}
        </Select>
      </Field>
      <Field label={t("reqNote")}>
        <Textarea rows={2} value={value.note} onChange={(e) => set("note", e.target.value)} placeholder={t("reqNotePh")} />
      </Field>
    </div>
  );
}

// ── Экран: список клиентов ──────────────────────────────────────────
export function ClientsScreen() {
  const { t, toast } = useApp();
  const nav = useNav();
  const [clients, setClients] = useState<Client[] | null>(null);
  const [q, setQ] = useState("");
  const [newCount, setNewCount] = useState(0);
  const [adding, setAdding] = useState(false);

  async function load() {
    const r = await api<Client[]>("/api/v1/clients" + (q.trim() ? "?q=" + encodeURIComponent(q.trim()) : ""));
    if (r.ok && Array.isArray(r.data)) setClients(r.data);
    else setClients([]);
  }
  async function loadCount() {
    const r = await api<{ new_count: number }>("/api/v1/clients/matches/summary");
    if (r.ok && r.data) setNewCount(r.data.new_count);
  }
  useEffect(() => {
    load();
    loadCount();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
  // Поиск с небольшой задержкой.
  useEffect(() => {
    const id = window.setTimeout(load, 300);
    return () => window.clearTimeout(id);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [q]);

  return (
    <div>
      <button
        onClick={() => {
          haptic();
          nav.push({ name: "matches" });
        }}
        className={
          "w-full flex items-center gap-3 rounded-xl2 border p-3.5 mb-3 transition active:scale-[.99] " +
          (newCount > 0 ? "text-white shadow-glow border-transparent" : "bg-card border-line")
        }
        style={newCount > 0 ? { background: "var(--grad)" } : undefined}
      >
        <span className={"w-10 h-10 rounded-xl flex items-center justify-center " + (newCount > 0 ? "bg-white/20" : "bg-primary-soft text-primary")}>
          <Bell size={20} />
        </span>
        <div className="min-w-0 flex-1 text-left">
          <div className="font-extrabold">{t("matchesTitle")}</div>
          <div className={"text-[12.5px] " + (newCount > 0 ? "opacity-90" : "text-muted")}>
            {newCount > 0 ? t("newMatchesN").replace("{n}", String(newCount)) : t("matchesSub")}
          </div>
        </div>
        {newCount > 0 && <Badge color="red">{newCount}</Badge>}
        <ChevronRight size={18} className={newCount > 0 ? "opacity-90" : "text-muted"} />
      </button>

      <div className="flex gap-2 mb-2">
        <div className="flex-1">
          <div className="relative">
            <SearchIcon size={16} className="absolute left-3 top-1/2 -translate-y-1/2 text-muted" />
            <Input className="pl-9" placeholder={t("clientSearch")} value={q} onChange={(e) => setQ(e.target.value)} />
          </div>
        </div>
        <Button size="sm" onClick={() => setAdding((v) => !v)}>
          {adding ? <X size={16} /> : <UserPlus size={16} />} {adding ? t("cancel") : t("addClient")}
        </Button>
      </div>

      {adding && <AddClientForm onDone={() => { setAdding(false); load(); loadCount(); }} />}

      {!clients ? (
        <Spinner />
      ) : !clients.length ? (
        <Empty icon={<Users size={24} />} sub={t("clientsEmptySub")}>
          {t("clientsEmpty")}
        </Empty>
      ) : (
        clients.map((c) => <ClientRow key={c.id} c={c} />)
      )}
    </div>
  );
}

function ClientRow({ c }: { c: Client }) {
  const { t } = useApp();
  const nav = useNav();
  const name = c.last_name ? `${c.name} ${c.last_name}` : c.name;
  return (
    <button
      onClick={() => {
        haptic();
        nav.push({ name: "clientDetail", id: c.id });
      }}
      className="w-full text-left mt-2.5 rounded-xl2 bg-card border border-line shadow-soft p-3.5 transition active:scale-[.99] hover:shadow-lg2"
    >
      <div className="flex items-center gap-3">
        <span className="w-10 h-10 shrink-0 rounded-xl bg-primary-soft text-primary flex items-center justify-center">
          <Users size={18} />
        </span>
        <div className="min-w-0 flex-1">
          <div className="flex items-center justify-between gap-2">
            <span className="font-extrabold inline-flex items-center gap-1.5 min-w-0">
              {c.priority && <span className={"w-2 h-2 rounded-full shrink-0 " + (PRIORITY_DOT[c.priority] || "")} />}
              <span className="truncate">{name}</span>
            </span>
            <span className="flex items-center gap-1 shrink-0">
              {!!c.open_tasks && (
                <span className="text-[11px] font-extrabold px-1.5 py-0.5 rounded-full bg-amber-100 text-amber-700 inline-flex items-center gap-0.5">
                  <CheckSquare size={11} /> {c.open_tasks}
                </span>
              )}
              {c.new_match_count > 0 && <Badge color="red">{t("matchN").replace("{n}", String(c.new_match_count))}</Badge>}
            </span>
          </div>
          {c.phone && <div className="text-[13px] text-muted truncate">{c.phone}</div>}
          <div className="text-[12.5px] text-muted">
            {t("activeRequestsN").replace("{n}", String(c.active_requests))}
            {c.created_by_name ? " · " + c.created_by_name : ""}
          </div>
        </div>
        <ChevronRight size={18} className="text-muted shrink-0" />
      </div>
    </button>
  );
}

// ── Приоритет клиента («светофор»: горячий/тёплый/холодный) ──────────
const PRIORITY_DOT: Record<string, string> = {
  hot: "bg-rose-500",
  warm: "bg-amber-500",
  cold: "bg-sky-500",
};

function PriorityPicker({ value, onChange }: { value: string; onChange: (v: string) => void }) {
  const { t } = useApp();
  return (
    <div className="flex gap-1.5">
      {(["hot", "warm", "cold"] as const).map((k) => (
        <button
          key={k}
          type="button"
          onClick={() => onChange(value === k ? "" : k)}
          className={
            "flex-1 inline-flex items-center justify-center gap-1.5 rounded-xl border px-2 py-2 text-[13px] font-bold transition active:scale-95 " +
            (value === k ? "border-primary bg-primary-soft text-primary" : "border-line text-muted")
          }
        >
          <span className={"w-2 h-2 rounded-full " + PRIORITY_DOT[k]} />
          {t("prio_" + k)}
        </button>
      ))}
    </div>
  );
}

// ── ИИ-подсказки по клиенту (Волна 6) ───────────────────────────────
function hintText(h: HintItem, t: (k: string) => string): string {
  if (h.kind === "silent") return t("hint_silent").replace("{n}", String(h.days ?? 0));
  if (h.kind === "new_matches") return t("hint_new_matches").replace("{n}", String(h.count ?? 0));
  if (h.kind === "total_matches") return t("hint_total_matches").replace("{n}", String(h.count ?? 0));
  if (h.kind === "no_request") return t("hint_no_request");
  return "";
}

function ClientHints({ clientId }: { clientId: number }) {
  const { t } = useApp();
  const [hints, setHints] = useState<HintItem[]>([]);
  useEffect(() => {
    api<HintItem[]>("/api/v1/clients/" + clientId + "/hints").then((r) => {
      if (r.ok && Array.isArray(r.data)) setHints(r.data);
    });
  }, [clientId]);
  if (!hints.length) return null;
  return (
    <div className="mt-2 space-y-1.5">
      {hints.map((h, i) => (
        <div key={i} className="flex items-start gap-2 rounded-xl bg-primary-soft text-primary p-2.5 text-[12.5px] font-bold">
          <Sparkles size={15} className="shrink-0 mt-0.5" />
          <span>{hintText(h, t)}</span>
        </div>
      ))}
    </div>
  );
}

// ── Сделки по клиенту (Волна 5) ─────────────────────────────────────
const DEAL_STAGES = ["new", "interested", "shown", "price_agreed", "deposit", "contract", "sold", "cancelled"];

function dealStageClass(s: string): string {
  if (s === "sold") return "bg-emerald-100 text-emerald-700";
  if (s === "cancelled") return "bg-slate-100 text-slate-500";
  if (s === "deposit" || s === "contract") return "bg-amber-100 text-amber-700";
  return "bg-indigo-100 text-indigo-700";
}

function fmtMoney(v?: number | null, cur?: string | null): string {
  if (v == null) return "";
  return new Intl.NumberFormat("ru-RU").format(v) + (cur ? " " + cur : "");
}

function ClientDeals({ clientId }: { clientId: number }) {
  const { t, toast } = useApp();
  const [deals, setDeals] = useState<Deal[] | null>(null);
  const [creating, setCreating] = useState(false);
  const [price, setPrice] = useState("");
  const [commission, setCommission] = useState("");
  const [currency, setCurrency] = useState("USD");

  async function load() {
    const r = await api<Deal[]>("/api/v1/clients/" + clientId + "/deals");
    setDeals(r.ok && Array.isArray(r.data) ? r.data : []);
  }
  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [clientId]);

  async function create() {
    const body: Record<string, unknown> = { stage: "new", currency };
    const p = Number(price.replace(",", "."));
    const cm = Number(commission.replace(",", "."));
    if (price.trim() && !Number.isNaN(p)) body.price = p;
    if (commission.trim() && !Number.isNaN(cm)) {
      body.commission = cm;
      body.commission_currency = currency;
    }
    const r = await api("/api/v1/clients/" + clientId + "/deals", { method: "POST", body });
    if (r.ok) {
      haptic();
      setPrice("");
      setCommission("");
      setCreating(false);
      load();
    } else toast(errText(r.data, r.status), "err");
  }

  async function setStage(d: Deal, stage: string) {
    const r = await api("/api/v1/clients/deals/" + d.id, { method: "PATCH", body: { stage } });
    if (r.ok) {
      haptic();
      load();
    } else toast(errText(r.data, r.status), "err");
  }

  return (
    <div className="mt-5">
      <div className="flex items-center justify-between mb-2 mx-0.5">
        <span className="text-[14px] font-extrabold tracking-tight">{t("dealsTitle")}</span>
        <button onClick={() => setCreating((v) => !v)} className="text-[13px] font-bold text-primary inline-flex items-center gap-1 active:scale-95">
          <Plus size={15} /> {t("createDeal")}
        </button>
      </div>
      {creating && (
        <Card className="mb-2">
          <div className="flex gap-2">
            <div className="flex-1">
              <Field label={t("dealPrice")}>
                <Input inputMode="numeric" value={price} onChange={(e) => setPrice(e.target.value)} />
              </Field>
            </div>
            <div className="w-24">
              <Field label={t("priceCurrency")}>
                <Select value={currency} onChange={(e) => setCurrency(e.target.value)}>
                  {CURRENCIES.map((c) => (
                    <option key={c} value={c}>{c}</option>
                  ))}
                </Select>
              </Field>
            </div>
          </div>
          <Field label={t("dealCommission")}>
            <Input inputMode="numeric" value={commission} onChange={(e) => setCommission(e.target.value)} />
          </Field>
          <Button full className="mt-3" onClick={create}>{t("createDeal")}</Button>
        </Card>
      )}
      {deals === null ? (
        <Spinner />
      ) : deals.length === 0 ? (
        <div className="text-[12.5px] text-muted mx-0.5">{t("noDeals")}</div>
      ) : (
        <div className="space-y-2">
          {deals.map((d) => (
            <Card key={d.id}>
              <div className="flex items-center justify-between gap-2 mb-1.5">
                <span className={"text-[11px] font-extrabold px-2 py-0.5 rounded-full " + dealStageClass(d.stage)}>
                  {t("dstage_" + d.stage)}
                </span>
                {d.apartment_label && <span className="text-[12px] text-muted truncate">{d.apartment_label}</span>}
              </div>
              {(d.price != null || d.commission != null) && (
                <div className="text-[12.5px] text-muted mb-2">
                  {d.price != null && <span>{t("dealPrice")}: {fmtMoney(d.price, d.currency)}</span>}
                  {d.commission != null && (
                    <span>{d.price != null ? " · " : ""}{t("dealCommission")}: {fmtMoney(d.commission, d.commission_currency)}</span>
                  )}
                </div>
              )}
              <Select value={d.stage} onChange={(e) => setStage(d, e.target.value)}>
                {DEAL_STAGES.map((s) => (
                  <option key={s} value={s}>{t("dstage_" + s)}</option>
                ))}
              </Select>
            </Card>
          ))}
        </div>
      )}
    </div>
  );
}

// ── Задачи по клиенту (Волна 4) ─────────────────────────────────────
function ClientTasks({ clientId }: { clientId: number }) {
  const { t, lang, toast } = useApp();
  const [tasks, setTasks] = useState<Task[] | null>(null);
  const [open, setOpen] = useState(false);
  const [title, setTitle] = useState("");
  const [deadline, setDeadline] = useState("");

  async function load() {
    const r = await api<Task[]>("/api/v1/clients/" + clientId + "/tasks");
    setTasks(r.ok && Array.isArray(r.data) ? r.data : []);
  }
  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [clientId]);

  async function add() {
    if (!title.trim()) return;
    const r = await api("/api/v1/clients/" + clientId + "/tasks", {
      method: "POST",
      body: { title: title.trim(), deadline: deadline || null },
    });
    if (r.ok) {
      haptic();
      setTitle("");
      setDeadline("");
      setOpen(false);
      load();
    } else toast(errText(r.data, r.status), "err");
  }

  async function toggle(tk: Task) {
    const r = await api("/api/v1/clients/tasks/" + tk.id, {
      method: "PATCH",
      body: { status: tk.status === "done" ? "open" : "done" },
    });
    if (r.ok) {
      haptic();
      load();
    }
  }

  return (
    <div className="mt-5">
      <div className="flex items-center justify-between mb-2 mx-0.5">
        <span className="text-[14px] font-extrabold tracking-tight">{t("tasksTitle")}</span>
        <button onClick={() => setOpen((v) => !v)} className="text-[13px] font-bold text-primary inline-flex items-center gap-1 active:scale-95">
          <Plus size={15} /> {t("addTask")}
        </button>
      </div>
      {open && (
        <Card className="mb-2">
          <Field label={t("taskTitle")}>
            <Input value={title} onChange={(e) => setTitle(e.target.value)} placeholder={t("taskTitlePh")} />
          </Field>
          <Field label={t("taskDeadline")}>
            <Input type="date" value={deadline} onChange={(e) => setDeadline(e.target.value)} />
          </Field>
          <Button full className="mt-3" disabled={!title.trim()} onClick={add}>
            {t("histAdd")}
          </Button>
        </Card>
      )}
      {tasks === null ? (
        <Spinner />
      ) : tasks.length === 0 ? (
        <div className="text-[12.5px] text-muted mx-0.5">{t("noTasks")}</div>
      ) : (
        <div className="space-y-1.5">
          {tasks.map((tk) => (
            <button
              key={tk.id}
              onClick={() => toggle(tk)}
              className="w-full text-left flex items-center gap-2.5 rounded-xl border border-line p-2.5 active:scale-[.99] transition"
            >
              <span className={"w-5 h-5 rounded-md border shrink-0 flex items-center justify-center " + (tk.status === "done" ? "bg-primary border-primary text-white" : "border-line")}>
                {tk.status === "done" && <Check size={13} />}
              </span>
              <span className="min-w-0 flex-1">
                <span className={"text-[13px] font-bold " + (tk.status === "done" ? "line-through text-muted" : "")}>{tk.title}</span>
                {(tk.deadline || tk.kind === "auto") && (
                  <span className="block text-[11px] text-muted">
                    {tk.deadline ? fmtDate(tk.deadline, lang) : ""}
                    {tk.kind === "auto" ? (tk.deadline ? " · " : "") + t("taskAuto") : ""}
                  </span>
                )}
              </span>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

// ── История действий по клиенту (Волна 3) ───────────────────────────
// Иконки типов действий — Lucide (а не эмодзи): единый стиль, темизация, чёткость (аудит UI).
const ACT_ICON: Record<string, LucideIcon> = {
  call: Phone, show: Home, meeting: Handshake, message: MessageCircle, note: FileText, price_change: Coins,
};
function ActIcon({ kind, size = 16 }: { kind: string; size?: number }) {
  const I = ACT_ICON[kind] ?? FileText;
  return <I size={size} />;
}

function ClientHistory({ clientId }: { clientId: number }) {
  const { t, lang, toast } = useApp();
  const [acts, setActs] = useState<ClientActivity[] | null>(null);
  const [noteOpen, setNoteOpen] = useState(false);
  const [note, setNote] = useState("");

  async function load() {
    const r = await api<ClientActivity[]>("/api/v1/clients/" + clientId + "/activities");
    setActs(r.ok && Array.isArray(r.data) ? r.data : []);
  }
  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [clientId]);

  async function log(kind: string, noteText?: string) {
    const r = await api("/api/v1/clients/" + clientId + "/activities", {
      method: "POST",
      body: { kind, note: noteText || null },
    });
    if (r.ok) {
      haptic();
      toast(t("logged"), "ok");
      load();
    } else toast(errText(r.data, r.status), "err");
  }

  return (
    <div className="mt-5">
      <div className="text-[14px] font-extrabold tracking-tight mb-2 mx-0.5">{t("historyTitle")}</div>
      <div className="grid grid-cols-4 gap-2 mb-2">
        {(["call", "message", "show", "meeting"] as const).map((k) => (
          <button
            key={k}
            onClick={() => log(k)}
            className="rounded-xl border border-line py-2 flex flex-col items-center gap-1 text-[11px] font-bold text-muted active:scale-95 transition"
          >
            <ActIcon kind={k} size={20} />
            {t("act_" + k)}
          </button>
        ))}
      </div>
      <button
        onClick={() => setNoteOpen((v) => !v)}
        className="text-[13px] font-bold text-primary inline-flex items-center gap-1.5 active:scale-95 mb-2"
      >
        <Plus size={15} /> {t("addNoteBtn")}
      </button>
      {noteOpen && (
        <div className="flex gap-2 mb-2">
          <Input value={note} onChange={(e) => setNote(e.target.value)} placeholder={t("notePlaceholder")} />
          <Button
            size="sm"
            disabled={!note.trim()}
            onClick={async () => {
              await log("note", note.trim());
              setNote("");
              setNoteOpen(false);
            }}
          >
            {t("histAdd")}
          </Button>
        </div>
      )}
      {acts === null ? (
        <Spinner />
      ) : acts.length === 0 ? (
        <div className="text-[12.5px] text-muted mx-0.5">{t("noHistory")}</div>
      ) : (
        <div className="space-y-1.5">
          {acts.map((a) => (
            <div key={a.id} className="flex items-start gap-2 text-[13px]">
              <span className="shrink-0 text-muted mt-0.5"><ActIcon kind={a.kind} size={15} /></span>
              <div className="min-w-0 flex-1">
                <span className="font-bold">{t("act_" + a.kind)}</span>
                {a.note && <span className="text-muted"> — {a.note}</span>}
                <div className="text-[11px] text-muted">
                  {fmtDate(a.created_at, lang)}
                  {a.created_by_name ? " · " + a.created_by_name : ""}
                </div>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function AddClientForm({ onDone }: { onDone: () => void }) {
  const { t, toast } = useApp();
  const [name, setName] = useState("");
  const [lastName, setLastName] = useState("");
  const [phone, setPhone] = useState("");
  const [priority, setPriority] = useState("");
  const [source, setSource] = useState("");
  const [showReq, setShowReq] = useState(false);
  const [crit, setCrit] = useState<Criteria>(emptyCriteria());
  const [saving, setSaving] = useState(false);

  async function save() {
    if (!name.trim()) {
      toast(t("clientNameReq"), "err");
      return;
    }
    setSaving(true);
    const body: Record<string, unknown> = {
      name: name.trim(),
      last_name: lastName.trim() || null,
      phone: phone.trim() || null,
      priority: priority || null,
      source: source.trim() || null,
    };
    if (showReq && criteriaNonEmpty(crit)) body.request = criteriaToBody(crit);
    const r = await api<{ client: Client; found: number }>("/api/v1/clients", { method: "POST", body });
    setSaving(false);
    if (r.ok && r.data) {
      const found = r.data.found || 0;
      toast(found > 0 ? t("clientSavedFound").replace("{n}", String(found)) : t("clientSaved"), "ok");
      onDone();
    } else toast(errText(r.data, r.status), "err");
  }

  return (
    <Card className="mb-1">
      <Field label={t("clientName")}>
        <Input value={name} onChange={(e) => setName(e.target.value)} />
      </Field>
      <Field label={t("clientLastName")}>
        <Input value={lastName} onChange={(e) => setLastName(e.target.value)} />
      </Field>
      <Field label={t("clientPhone")}>
        <Input inputMode="tel" value={phone} onChange={(e) => setPhone(e.target.value)} />
      </Field>
      <Field label={t("clientPriority")}>
        <PriorityPicker value={priority} onChange={setPriority} />
      </Field>
      <Field label={t("clientSource")}>
        <Input value={source} onChange={(e) => setSource(e.target.value)} placeholder={t("clientSourcePh")} />
      </Field>
      <button
        onClick={() => setShowReq((v) => !v)}
        className="mt-3 text-[13px] font-bold text-primary inline-flex items-center gap-1.5 active:scale-95 transition"
      >
        <Plus size={15} /> {showReq ? t("hideWanted") : t("addWanted")}
      </button>
      {showReq && (
        <>
          <Hint>{t("wantedHint")}</Hint>
          <CriteriaEditor value={crit} onChange={setCrit} />
        </>
      )}
      <Button full className="mt-4" disabled={saving} onClick={save}>
        {t("saveClient")}
      </Button>
    </Card>
  );
}

// ── Экран: карточка клиента ─────────────────────────────────────────
export function ClientDetailScreen({ id }: { id: number }) {
  const { t, L, lang, toast, user } = useApp();
  const nav = useNav();
  const [c, setC] = useState<Client | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [addReq, setAddReq] = useState(false);
  const [crit, setCrit] = useState<Criteria>(emptyCriteria());
  const [saving, setSaving] = useState(false);
  const [editing, setEditing] = useState(false);

  async function load() {
    const r = await api<Client>("/api/v1/clients/" + id);
    if (r.ok && r.data) {
      setC(r.data);
      setErr(null);
    } else setErr(errText(r.data, r.status));
  }
  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id]);

  async function addRequest() {
    if (!criteriaNonEmpty(crit)) {
      toast(t("reqEmpty"), "err");
      return;
    }
    setSaving(true);
    const r = await api<{ found: number }>("/api/v1/clients/" + id + "/requests", { method: "POST", body: criteriaToBody(crit) });
    setSaving(false);
    if (r.ok && r.data) {
      const found = r.data.found || 0;
      toast(found > 0 ? t("reqSavedFound").replace("{n}", String(found)) : t("reqSaved"), "ok");
      setAddReq(false);
      setCrit(emptyCriteria());
      load();
    } else toast(errText(r.data, r.status), "err");
  }

  async function rescan(reqId: number) {
    toast(t("rescanning"), "info");
    const r = await api<{ found: number }>("/api/v1/clients/requests/" + reqId + "/rescan", { method: "POST" });
    if (r.ok && r.data) {
      const found = r.data.found || 0;
      toast(found > 0 ? t("reqSavedFound").replace("{n}", String(found)) : t("rescanNone"), found > 0 ? "ok" : "info");
      load();
    } else toast(errText(r.data, r.status), "err");
  }

  async function closeRequest(reqId: number) {
    const r = await api("/api/v1/clients/requests/" + reqId, { method: "PATCH", body: { status: "fulfilled" } });
    if (r.ok) {
      toast(t("saved"), "ok");
      load();
    } else toast(errText(r.data, r.status), "err");
  }
  async function delRequest(reqId: number) {
    if (!(await confirmDialog(t("delReqQ")))) return;
    const r = await api("/api/v1/clients/requests/" + reqId, { method: "DELETE" });
    if (r.ok) {
      toast(t("done"), "ok");
      load();
    } else toast(errText(r.data, r.status), "err");
  }
  async function toggleMute() {
    const r = await api("/api/v1/clients/" + id, { method: "PATCH", body: { muted: !c?.muted } });
    if (r.ok) {
      haptic();
      load();
    }
  }
  async function delClient() {
    if (!(await confirmDialog(t("delClientQ")))) return;
    const r = await api("/api/v1/clients/" + id, { method: "DELETE" });
    if (r.ok) {
      toast(t("done"), "ok");
      nav.pop();
    } else toast(errText(r.data, r.status), "err");
  }

  if (err) return <Empty>{err}</Empty>;
  if (!c) return <Spinner />;
  const name = c.last_name ? `${c.name} ${c.last_name}` : c.name;

  return (
    <div>
      <Card>
        {editing ? (
          <ClientEdit c={c} onDone={() => { setEditing(false); load(); }} />
        ) : (
          <>
            <div className="flex items-start justify-between gap-2">
              <div className="min-w-0">
                <div className="text-[18px] font-extrabold truncate">{name}</div>
                {c.phone && (
                  <a href={"tel:" + c.phone} className="text-[14px] text-primary font-bold inline-flex items-center gap-1.5 mt-0.5">
                    <Phone size={14} /> {c.phone}
                  </a>
                )}
                {c.created_by_name && <div className="text-[12.5px] text-muted mt-0.5">{t("addedBy")}: {c.created_by_name}</div>}
                {c.priority && (
                  <div className="inline-flex items-center gap-1.5 mt-1 text-[12.5px] font-bold">
                    <span className={"w-2 h-2 rounded-full " + (PRIORITY_DOT[c.priority] || "")} />
                    {t("prio_" + c.priority)}
                  </div>
                )}
                {c.source && <div className="text-[12.5px] text-muted mt-0.5">{t("clientSource")}: {c.source}</div>}
              </div>
              <div className="flex items-center gap-1.5 shrink-0">
                <button
                  onClick={toggleMute}
                  title={c.muted ? t("unmute") : t("mute")}
                  className={
                    "w-9 h-9 rounded-xl flex items-center justify-center active:scale-90 " +
                    (c.muted ? "bg-amber-100 text-amber-600" : "bg-primary-soft text-primary")
                  }
                >
                  {c.muted ? <BellOff size={16} /> : <Bell size={16} />}
                </button>
                <button onClick={() => setEditing(true)} className="w-9 h-9 rounded-xl bg-primary-soft text-primary flex items-center justify-center active:scale-90">
                  <Pencil size={16} />
                </button>
              </div>
            </div>
            {c.note && <Hint>{c.note}</Hint>}
          </>
        )}
      </Card>

      <ClientHints clientId={id} />

      <div className="flex items-center justify-between mt-4 mx-0.5 mb-1.5">
        <span className="text-[14px] font-extrabold tracking-tight">{t("wantedTitle")}</span>
        <button onClick={() => setAddReq((v) => !v)} className="text-[13px] font-bold text-primary inline-flex items-center gap-1 active:scale-95">
          <Plus size={15} /> {t("addRequest")}
        </button>
      </div>

      {addReq && (
        <Card className="mb-2">
          <Hint>{t("wantedHint")}</Hint>
          <CriteriaEditor value={crit} onChange={setCrit} />
          <Button full className="mt-4" disabled={saving} onClick={addRequest}>
            {t("saveRequestBtn")}
          </Button>
        </Card>
      )}

      {!c.requests.length && !addReq && <Empty sub={t("noRequestsSub")}>{t("noRequests")}</Empty>}

      {c.requests.map((r) => (
        <Card key={r.id} className="mt-2.5">
          <div className="flex items-start justify-between gap-2">
            <div className="min-w-0">
              <div className="font-bold text-[14px] leading-snug">{requestLabel(r, L, t)}</div>
              {r.note && <div className="text-[12.5px] text-muted mt-0.5">{r.note}</div>}
              <div className="text-[12px] text-muted mt-1">{fmtDate(r.created_at, lang)}</div>
            </div>
            <span className="flex flex-col items-end gap-1 shrink-0">
              {r.status !== "active" && <Badge color="gray">{t("reqStatus_" + r.status)}</Badge>}
              {r.match_count > 0 && (
                <Badge color={r.new_match_count > 0 ? "red" : "green"}>
                  {t("foundN").replace("{n}", String(r.match_count))}
                </Badge>
              )}
            </span>
          </div>
          <div className="mt-2 grid grid-cols-3 gap-2">
            <Button size="sm" variant="ghost" onClick={() => rescan(r.id)}>
              <RefreshCw size={14} /> {t("rescan")}
            </Button>
            {r.status === "active" ? (
              <Button size="sm" variant="ghost" onClick={() => closeRequest(r.id)}>
                {t("closeRequest")}
              </Button>
            ) : (
              <span />
            )}
            <Button size="sm" variant="danger" onClick={() => delRequest(r.id)}>
              <Trash2 size={14} />
            </Button>
          </div>
        </Card>
      ))}

      <ClientDeals clientId={id} />

      <ClientTasks clientId={id} />

      <ClientHistory clientId={id} />

      <Button full variant="danger" className="mt-5" onClick={delClient}>
        <Trash2 size={16} /> {t("delClient")}
      </Button>
    </div>
  );
}

function ClientEdit({ c, onDone }: { c: Client; onDone: () => void }) {
  const { t, toast } = useApp();
  const [name, setName] = useState(c.name);
  const [lastName, setLastName] = useState(c.last_name || "");
  const [phone, setPhone] = useState(c.phone || "");
  const [note, setNote] = useState(c.note || "");
  const [priority, setPriority] = useState(c.priority || "");
  const [source, setSource] = useState(c.source || "");
  const [saving, setSaving] = useState(false);
  async function save() {
    setSaving(true);
    const r = await api("/api/v1/clients/" + c.id, {
      method: "PATCH",
      body: { name: name.trim(), last_name: lastName.trim(), phone: phone.trim(), note: note.trim(), priority, source: source.trim() },
    });
    setSaving(false);
    if (r.ok) {
      toast(t("saved"), "ok");
      onDone();
    } else toast(errText(r.data, r.status), "err");
  }
  return (
    <div>
      <Field label={t("clientName")}>
        <Input value={name} onChange={(e) => setName(e.target.value)} />
      </Field>
      <Field label={t("clientLastName")}>
        <Input value={lastName} onChange={(e) => setLastName(e.target.value)} />
      </Field>
      <Field label={t("clientPhone")}>
        <Input inputMode="tel" value={phone} onChange={(e) => setPhone(e.target.value)} />
      </Field>
      <Field label={t("clientNote")}>
        <Textarea rows={2} value={note} onChange={(e) => setNote(e.target.value)} />
      </Field>
      <Field label={t("clientPriority")}>
        <PriorityPicker value={priority} onChange={setPriority} />
      </Field>
      <Field label={t("clientSource")}>
        <Input value={source} onChange={(e) => setSource(e.target.value)} placeholder={t("clientSourcePh")} />
      </Field>
      <div className="grid grid-cols-2 gap-2 mt-4">
        <Button variant="ghost" onClick={onDone}>{t("cancel")}</Button>
        <Button disabled={saving} onClick={save}>{t("saveChanges")}</Button>
      </div>
    </div>
  );
}

// ── Экран: совпадения ───────────────────────────────────────────────
export function MatchesScreen() {
  const { t, lang, toast } = useApp();
  const nav = useNav();
  const [matches, setMatches] = useState<Match[] | null>(null);

  async function load() {
    const r = await api<Match[]>("/api/v1/clients/matches");
    setMatches(r.ok && Array.isArray(r.data) ? r.data : []);
    // Открыли список → помечаем новые как просмотренные (значок гаснет).
    api("/api/v1/clients/matches/seen", { method: "POST" });
  }
  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function setStatus(m: Match, status: string) {
    const r = await api("/api/v1/clients/matches/" + m.id + "/status", { method: "POST", body: { status } });
    if (r.ok) load();
  }

  async function makeDeal(m: Match) {
    const r = await api("/api/v1/clients/" + m.client_id + "/deals", {
      method: "POST",
      body: { apartment_id: m.apartment.id, stage: "interested" },
    });
    if (r.ok) {
      haptic();
      toast(t("dealCreated"), "ok");
    } else toast(errText(r.data, r.status), "err");
  }

  if (!matches) return <Spinner />;
  if (!matches.length) return <Empty icon={<Bell size={24} />} sub={t("matchesEmptySub")}>{t("matchesEmpty")}</Empty>;

  return (
    <div>
      <Hint>{t("matchesHint")}</Hint>
      {matches.map((m) => (
        <Card key={m.id} className="mt-2.5">
          <button
            onClick={() => {
              haptic();
              nav.push({ name: "clientDetail", id: m.client_id });
            }}
            className="w-full text-left flex items-center gap-2 mb-1"
          >
            <Bell size={15} className={m.status === "new" ? "text-rose-500" : "text-muted"} />
            <span className="font-extrabold truncate flex-1">{m.client_name}</span>
            {typeof m.score === "number" && (
              <span
                className={
                  "text-[11px] font-extrabold px-1.5 py-0.5 rounded-full " +
                  (m.score >= 90
                    ? "bg-emerald-100 text-emerald-700"
                    : m.score >= 70
                    ? "bg-amber-100 text-amber-700"
                    : "bg-slate-100 text-slate-600")
                }
              >
                {m.score}%
              </span>
            )}
            {m.status === "new" && <Badge color="red">{t("matchNew")}</Badge>}
            {m.status === "offered" && <Badge color="green">{t("matchOffered")}</Badge>}
          </button>
          {m.request_label && <div className="text-[12px] text-muted mb-1">{t("wanted")}: {m.request_label}</div>}
          {!!(m.match_good && m.match_good.length) && (
            <div className="text-[11px] text-emerald-600 mb-1">✓ {m.match_good.map((c) => t("mr_" + c)).join(" · ")}</div>
          )}
          {!!(m.match_missing && m.match_missing.length) && (
            <div className="text-[11px] text-amber-600 mb-1">
              ⚠ {t("matchIncomplete")}: {m.match_missing.map((c) => t("mf_" + c)).join(", ")}
            </div>
          )}
          {m.source === "mls" && (
            <div className="text-[11px] font-bold text-indigo-600 mb-1 inline-flex items-center gap-1 flex-wrap">
              🌐 {t("mlsBadge")}
              {m.mls_agency ? " · " + m.mls_agency : ""}
              {m.possible_dup ? " · " + t("possibleDup") : ""}
            </div>
          )}
          <ApartmentCard o={m.apartment} />
          <div className="mt-2 grid grid-cols-3 gap-2">
            <Button size="sm" onClick={() => makeDeal(m)}>
              {t("toDeal")}
            </Button>
            <Button size="sm" variant="ghost" onClick={() => setStatus(m, "offered")}>
              {t("markOffered")}
            </Button>
            <Button size="sm" variant="danger" onClick={() => setStatus(m, "dismissed")}>
              {t("dismissMatch")}
            </Button>
          </div>
        </Card>
      ))}
    </div>
  );
}

// ── Экран: «Запомнить для клиента» (из поиска) ──────────────────────
export function SaveRequestScreen({ criteria }: { criteria: SearchParams }) {
  const { t, toast } = useApp();
  const nav = useNav();
  const [mode, setMode] = useState<"new" | "existing">("new");
  const [clients, setClients] = useState<Client[]>([]);
  const [pickId, setPickId] = useState<number | null>(null);
  const [name, setName] = useState("");
  const [lastName, setLastName] = useState("");
  const [phone, setPhone] = useState("");
  const [crit, setCrit] = useState<Criteria>(paramsToCriteria(criteria));
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    api<Client[]>("/api/v1/clients").then((r) => {
      if (r.ok && Array.isArray(r.data)) setClients(r.data);
    });
  }, []);

  async function save() {
    if (!criteriaNonEmpty(crit)) {
      toast(t("reqEmpty"), "err");
      return;
    }
    const reqBody = criteriaToBody(crit);
    setSaving(true);
    let ok = false;
    let found = 0;
    let clientId: number | null = null;
    if (mode === "new") {
      if (!name.trim()) {
        setSaving(false);
        toast(t("clientNameReq"), "err");
        return;
      }
      const r = await api<{ client: Client; found: number }>("/api/v1/clients", {
        method: "POST",
        body: { name: name.trim(), last_name: lastName.trim() || null, phone: phone.trim() || null, request: reqBody },
      });
      ok = r.ok;
      if (r.ok && r.data) { found = r.data.found || 0; clientId = r.data.client.id; }
      else toast(errText(r.data, r.status), "err");
    } else {
      if (!pickId) {
        setSaving(false);
        toast(t("pickClient"), "err");
        return;
      }
      const r = await api<{ found: number }>("/api/v1/clients/" + pickId + "/requests", { method: "POST", body: reqBody });
      ok = r.ok;
      if (r.ok && r.data) { found = r.data.found || 0; clientId = pickId; }
      else toast(errText(r.data, r.status), "err");
    }
    setSaving(false);
    if (ok && clientId) {
      toast(found > 0 ? t("reqSavedFound").replace("{n}", String(found)) : t("reqSaved"), "ok");
      nav.pop();
      nav.push({ name: "clientDetail", id: clientId });
    }
  }

  return (
    <div>
      <Hint>{t("saveReqHint")}</Hint>
      <Card className="mt-2">
        <div className="flex gap-1 p-1.5 rounded-[14px] bg-[var(--soft)] mb-1">
          {(["new", "existing"] as const).map((mm) => (
            <button
              key={mm}
              onClick={() => setMode(mm)}
              className={
                "flex-1 px-3 py-2.5 rounded-[10px] text-[13px] font-bold transition " +
                (mode === mm ? "bg-card text-text shadow-soft" : "text-muted")
              }
            >
              {mm === "new" ? t("newClient") : t("existingClient")}
            </button>
          ))}
        </div>
        {mode === "new" ? (
          <>
            <Field label={t("clientName")}>
              <Input value={name} onChange={(e) => setName(e.target.value)} />
            </Field>
            <Field label={t("clientLastName")}>
              <Input value={lastName} onChange={(e) => setLastName(e.target.value)} />
            </Field>
            <Field label={t("clientPhone")}>
              <Input inputMode="tel" value={phone} onChange={(e) => setPhone(e.target.value)} />
            </Field>
          </>
        ) : (
          <Field label={t("chooseClient")}>
            <Select value={pickId ?? ""} onChange={(e) => setPickId(e.target.value ? Number(e.target.value) : null)}>
              <option value="">{t("notSet")}</option>
              {clients.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.last_name ? `${c.name} ${c.last_name}` : c.name}
                  {c.phone ? ` · ${c.phone}` : ""}
                </option>
              ))}
            </Select>
          </Field>
        )}
      </Card>

      <div className="text-[12px] font-extrabold uppercase tracking-wider text-primary mt-4 mb-1 mx-0.5">{t("wantedTitle")}</div>
      <Card>
        <CriteriaEditor value={crit} onChange={setCrit} />
      </Card>

      <Button full className="mt-4" disabled={saving} onClick={save}>
        {t("rememberForClient")}
      </Button>
    </div>
  );
}
