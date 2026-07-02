import React, { useEffect, useMemo, useRef, useState } from "react";
import {
  Archive as ArchiveIcon,
  ArrowLeft,
  Camera,
  Check,
  ChevronLeft,
  ChevronRight,
  Copy,
  ExternalLink,
  Home as HomeIcon,
  Image as ImageIcon,
  Lock,
  Pencil,
  RotateCcw,
  Search as SearchIcon,
  SearchX,
  SlidersHorizontal,
  Send,
  Sparkles,
  Trash2,
  UserPlus,
  X,
} from "lucide-react";
import { useApp } from "../store";
import { useNav } from "../nav";
import { api, buildQuery, errText } from "../api";
import {
  Button,
  Card,
  Chips,
  Empty,
  Field,
  Hint,
  Input,
  Row,
  Select,
  Segmented,
  Spinner,
  Textarea, ListSkeleton, Swipeable } from "../components/ui";
import {
  CURRENCIES,
  FA_VALUES,
  hasLandArea,
  OBJ_COND_VALUES,
  OBJ_TYPE_VALUES,
  STATUS_BADGE,
} from "../i18n";
import { Badge } from "../components/ui";
import type { Apartment, ApartmentEvent, ApartmentList, ApartmentPhoto, DictItem, ListingImport, MlsPoolItem, MlsPoolResponse, SearchParams } from "../types";
import { copyText, downscaleToDataUrl, fmtDate, fmtPrice } from "../utils";
import { canShareMessage, haptic, openLink, shareMessage, confirmDialog } from "../telegram";

// Загрузка справочника районов (один раз на жизнь экрана).
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

const numOrNull = (v: string): number | null => {
  const s = v.trim();
  if (!s) return null;
  const n = Number(s.replace(",", "."));
  return Number.isNaN(n) ? null : n;
};
const intOrNull = (v: string): number | null => {
  const s = v.trim();
  if (!s) return null;
  const n = parseInt(s, 10);
  return Number.isNaN(n) ? null : n;
};

// Отправить одно фото (data-URL) на сервер как JSON. Возвращает ответ API.
async function uploadOnePhoto(apartmentId: number, dataUrl: string) {
  return api<ApartmentPhoto[]>(`/api/v1/apartments/${apartmentId}/photos`, {
    method: "POST",
    body: { images: [dataUrl] },
  });
}

// Форма объекта (создание и редактирование). При full=true пустые поля
// отправляются как null (очистка).
function ObjectForm({
  initial,
  onSubmit,
  submitLabel,
  saving,
  children,
}: {
  initial?: Partial<Apartment> | null;
  onSubmit: (body: Record<string, unknown>, full: boolean) => void;
  submitLabel: string;
  saving: boolean;
  children?: React.ReactNode;
}) {
  const { t, L, settings } = useApp();
  const districts = useDistricts();
  const o = initial || {};
  const full = !!initial?.id;

  const [f, setF] = useState({
    deal_type: o.deal_type ?? "sale",
    rent_period: o.rent_period ?? "month",
    name: o.name ?? "",
    type: o.type ?? "",
    district: o.district ?? "",
    address: o.address ?? "",
    rooms: o.rooms != null ? String(o.rooms) : "",
    floor: o.floor != null ? String(o.floor) : "",
    total_floors: o.total_floors != null ? String(o.total_floors) : "",
    land_area: o.land_area != null ? String(o.land_area) : "",
    area: o.area != null ? String(o.area) : "",
    price: o.price != null ? String(o.price) : "",
    currency: o.currency || "USD",
    condition: o.condition ?? "",
    furniture_appliances: o.furniture_appliances ?? "",
    owner_phone: o.owner_phone ?? "",
    source_link: o.source_link ?? "",
    source: o.source ?? "",
    description: o.description ?? "",
    comment: o.comment ?? "",
    shared_mls: o.shared_mls ?? (settings?.is_shared ?? false),
  });
  const set = (k: keyof typeof f, v: string) => setF((p) => ({ ...p, [k]: v }));
  // Дом/участок/земля: вместо «Этажа» показываем «Соток»; «Этажность» остаётся.
  const withLand = hasLandArea(f.type);

  function submit() {
    const land = hasLandArea(f.type);
    const isRent = f.deal_type === "rent";
    const fields: Record<string, unknown> = {
      deal_type: f.deal_type || "sale",
      // Срок аренды — только для аренды; для продажи отправляем null (очистка).
      rent_period: isRent ? f.rent_period || "month" : null,
      name: f.name.trim() || null,
      type: f.type || null,
      district: f.district || null,
      address: f.address.trim() || null,
      rooms: intOrNull(f.rooms),
      // Дом/участок/земля: без «Этажа», но с «Этажностью» и «Соток».
      // Квартира/коммерция: с «Этажом»+«Этажностью», без «Соток».
      floor: land ? null : intOrNull(f.floor),
      total_floors: intOrNull(f.total_floors),
      land_area: land ? numOrNull(f.land_area) : null,
      area: numOrNull(f.area),
      price: numOrNull(f.price),
      currency: f.currency,
      condition: f.condition || null,
      furniture_appliances: f.furniture_appliances || null,
      owner_phone: f.owner_phone.trim() || null,
      source_link: f.source_link.trim() || null,
      source: f.source.trim() || null,
      description: f.description.trim() || null,
      comment: f.comment.trim() || null,
      shared_mls: f.shared_mls,
    };
    const body: Record<string, unknown> = {};
    Object.keys(fields).forEach((k) => {
      if (full && k === "currency" && !fields[k]) return;
      if (full || fields[k] !== null) body[k] = fields[k];
    });
    onSubmit(body, full);
  }

  const Sec = ({ children }: { children: React.ReactNode }) => (
    <div className="text-[12px] font-extrabold uppercase tracking-wider text-primary mt-5 mb-1 pt-3 border-t border-[var(--border)] first:border-0 first:pt-0 first:mt-1">
      {children}
    </div>
  );

  return (
    <Card>
      <Sec>{t("sectionMain")}</Sec>
      {/* Тип сделки: продажа / аренда. Для аренды — выбор срока (месяц/сутки). */}
      <div className="mb-1">
        <div className="text-[12px] font-bold text-muted mb-1.5">{t("dealType")}</div>
        <Segmented
          value={f.deal_type as "sale" | "rent"}
          onChange={(v) => set("deal_type", v)}
          options={[
            { value: "sale", label: t("dealSale") },
            { value: "rent", label: t("dealRent") },
          ]}
        />
      </div>
      {f.deal_type === "rent" && (
        <div className="mb-1 mt-2">
          <div className="text-[12px] font-bold text-muted mb-1.5">{t("rentPeriodLbl")}</div>
          <Segmented
            value={f.rent_period as "month" | "day"}
            onChange={(v) => set("rent_period", v)}
            options={[
              { value: "month", label: t("rentMonth") },
              { value: "day", label: t("rentDay") },
            ]}
          />
        </div>
      )}
      {/* Ссылка на пост и источник (канал) — наверху, чтобы при добавлении
          по ссылке всё было сразу под рукой. */}
      <Field label={t("f_source")}>
        <Input inputMode="url" placeholder="https://…" value={f.source_link} onChange={(e) => set("source_link", e.target.value)} />
      </Field>
      <Field label={t("f_sourceName")}>
        <Input placeholder={t("f_sourceNamePh")} value={f.source} onChange={(e) => set("source", e.target.value)} />
      </Field>
      <Field label={t("f_name")}>
        <Input value={f.name} onChange={(e) => set("name", e.target.value)} />
      </Field>
      <Field label={t("f_type")}>
        <Select value={f.type} onChange={(e) => set("type", e.target.value)}>
          <option value="">{t("notSet")}</option>
          {OBJ_TYPE_VALUES.map((v) => (
            <option key={v} value={v}>
              {L.typeLabel(v)}
            </option>
          ))}
        </Select>
      </Field>
      <Field label={t("f_district")}>
        <Select value={f.district} onChange={(e) => set("district", e.target.value)}>
          <option value="">{t("notSet")}</option>
          {districts.map((d) => (
            <option key={d.id} value={d.value}>
              {d.value}
            </option>
          ))}
        </Select>
      </Field>
      <Field label={t("f_address")}>
        <Input value={f.address} onChange={(e) => set("address", e.target.value)} />
      </Field>

      <Sec>{t("sectionDetails")}</Sec>
      <div className="flex gap-2">
        <div className="flex-1 min-w-0">
          <Field label={t("f_rooms")}>
            <Input inputMode="numeric" value={f.rooms} onChange={(e) => set("rooms", e.target.value)} />
          </Field>
        </div>
        {/* «Этаж» — только для квартиры/коммерции (не для дома/участка/земли). */}
        {!withLand && (
          <div className="flex-1 min-w-0">
            <Field label={t("f_floor")}>
              <Input inputMode="numeric" value={f.floor} onChange={(e) => set("floor", e.target.value)} />
            </Field>
          </div>
        )}
        {/* «Этажность» — для всех типов. */}
        <div className="flex-1 min-w-0">
          <Field label={t("f_tfloors")}>
            <Input inputMode="numeric" value={f.total_floors} onChange={(e) => set("total_floors", e.target.value)} />
          </Field>
        </div>
        {/* «Соток» — для дома/участка/земли. */}
        {withLand && (
          <div className="flex-1 min-w-0">
            <Field label={t("f_land_area")}>
              <Input inputMode="decimal" value={f.land_area} onChange={(e) => set("land_area", e.target.value)} />
            </Field>
          </div>
        )}
      </div>
      <div className="flex gap-2">
        <div className="flex-1">
          <Field label={t("f_area")}>
            <Input inputMode="decimal" value={f.area} onChange={(e) => set("area", e.target.value)} />
          </Field>
        </div>
        <div className="flex-1">
          <Field label={f.deal_type === "rent" ? t("priceRent") : t("f_price")}>
            <Input inputMode="numeric" value={f.price} onChange={(e) => set("price", e.target.value)} />
          </Field>
        </div>
        <div className="flex-1">
          <Field label={t("f_currency")}>
            <Select value={f.currency} onChange={(e) => set("currency", e.target.value)}>
              {CURRENCIES.map((c) => (
                <option key={c} value={c}>
                  {c}
                </option>
              ))}
            </Select>
          </Field>
        </div>
      </div>
      <Field label={t("f_condition")}>
        <Select value={f.condition} onChange={(e) => set("condition", e.target.value)}>
          <option value="">{t("notSet")}</option>
          {OBJ_COND_VALUES.map((v) => (
            <option key={v} value={v}>
              {L.condLabel(v)}
            </option>
          ))}
        </Select>
      </Field>
      <Field label={t("f_furniture")}>
        <Select value={f.furniture_appliances} onChange={(e) => set("furniture_appliances", e.target.value)}>
          <option value="">{t("notSet")}</option>
          {FA_VALUES.map((v) => (
            <option key={v} value={v}>
              {L.faLabel(v)}
            </option>
          ))}
        </Select>
      </Field>

      <Sec>{t("sectionContacts")}</Sec>
      <Field label={t("f_owner_phone")}>
        <Input value={f.owner_phone} onChange={(e) => set("owner_phone", e.target.value)} />
      </Field>
      <Hint>{t("ownerPhoneHint")}</Hint>

      <button
        type="button"
        onClick={() => setF((p) => ({ ...p, shared_mls: !p.shared_mls }))}
        className="w-full flex items-center gap-3 mt-2 rounded-xl border border-line p-3 active:scale-[.99] transition text-left"
      >
        <span className={"w-5 h-5 rounded-md border shrink-0 flex items-center justify-center " + (f.shared_mls ? "bg-primary border-primary text-white" : "border-line")}>
          {f.shared_mls && <Check size={13} />}
        </span>
        <span className="min-w-0">
          <span className="text-[13.5px] font-bold block">{t("shareMls")}</span>
          <span className="text-[12px] text-muted block leading-snug">{t("shareMlsHint")}</span>
        </span>
      </button>
      <Field label={t("f_desc")}>
        <Textarea rows={3} value={f.description} onChange={(e) => set("description", e.target.value)} />
      </Field>

      <Sec>{t("sectionInternal")}</Sec>
      <Field label={t("f_comment")}>
        <Textarea rows={3} value={f.comment} onChange={(e) => set("comment", e.target.value)} />
      </Field>
      <Hint>{t("commentHint")}</Hint>

      {children}

      <Button full className="mt-4" disabled={saving} onClick={submit}>
        {submitLabel}
      </Button>
    </Card>
  );
}

// Текст карточки для отправки клиенту (эмодзи, без номера собственника и
// комментария; вместо номера — контактный телефон агентства).
function buildShareCard(o: Apartment, L: ReturnType<typeof useApp>["L"], t: (k: string) => string, contactPhone?: string | null, contactUsername?: string | null): string {
  const lines: string[] = [];
  // Наименование (если задано вручную) — первым.
  if (o.name) lines.push("🏠 " + o.name);
  lines.push("№ " + (o.display_id || ""));
  // Для аренды явно помечаем тип сделки и период.
  if (o.deal_type === "rent") {
    lines.push("🤝 " + t("dealRent") + " (" + (o.rent_period === "day" ? t("rentDay") : t("rentMonth")) + ")");
  }
  // Описание — сразу после наименования (или первым, если наименования нет).
  if (o.description) {
    lines.push("");
    lines.push("📝 " + o.description);
  }
  // Остальные данные по порядку.
  const d: string[] = [];
  if (o.type) d.push("🏗 " + t("f_type") + ": " + L.typeLabel(o.type));
  if (o.district) d.push("📍 " + t("f_district") + ": " + o.district);
  if (o.address) d.push("🗺 " + t("f_address") + ": " + o.address);
  if (o.rooms != null) d.push("🚪 " + t("f_rooms") + ": " + o.rooms);
  // Дом/участок/земля: «Соток» вместо «Этажа», «Этажность» остаётся для всех.
  if (hasLandArea(o.type)) {
    if (o.land_area != null) d.push("🌳 " + t("f_land_area") + ": " + o.land_area);
  } else {
    if (o.floor != null) d.push("🏢 " + t("f_floor") + ": " + o.floor);
  }
  if (o.total_floors != null) d.push("🏢 " + t("f_tfloors") + ": " + o.total_floors);
  if (o.area != null) d.push("📐 " + t("f_area") + ": " + o.area);
  if (o.condition) d.push("🔧 " + L.condLabel(o.condition));
  const fa = L.faLabel(o.furniture_appliances);
  if (fa) d.push("🛋 " + fa);
  if (o.price != null) d.push("💵 " + t("f_price") + ": " + o.price + " " + (o.currency || "") + L.priceSuffix(o.deal_type, o.rent_period));
  // Ссылку-источник клиенту НЕ показываем (никаких ссылок в карточке).
  if (d.length) {
    lines.push("");
    lines.push(...d);
  }
  if (contactPhone) {
    lines.push("");
    lines.push("📞 " + contactPhone);
  }
  // Username главного админа в карточку клиента НЕ добавляем (по требованию).
  return lines.join("\n");
}

// ── Просмотр фото внутри приложения (увеличение, без внешнего браузера) ──
function Lightbox({
  urls,
  index,
  onClose,
  onIndex,
}: {
  urls: string[];
  index: number;
  onClose: () => void;
  onIndex: (i: number) => void;
}) {
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
      else if (e.key === "ArrowLeft") onIndex((index - 1 + urls.length) % urls.length);
      else if (e.key === "ArrowRight") onIndex((index + 1) % urls.length);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [index, urls.length, onClose, onIndex]);

  if (index < 0 || index >= urls.length) return null;
  const multi = urls.length > 1;
  const go = (e: React.MouseEvent, i: number) => {
    e.stopPropagation();
    onIndex((i + urls.length) % urls.length);
  };
  return (
    <div className="fixed inset-0 z-[60] bg-black/90 flex items-center justify-center" onClick={onClose}>
      <button
        className="absolute top-3 right-3 w-10 h-10 rounded-full bg-white/15 text-white flex items-center justify-center active:scale-90"
        onClick={onClose}
        aria-label="close"
      >
        <X size={20} />
      </button>
      <img
        src={urls[index]}
        alt=""
        className="max-w-[94vw] max-h-[82vh] object-contain rounded-lg"
        onClick={(e) => e.stopPropagation()}
      />
      {multi && (
        <>
          <button
            className="absolute left-2 top-1/2 -translate-y-1/2 w-10 h-10 rounded-full bg-white/15 text-white flex items-center justify-center active:scale-90"
            onClick={(e) => go(e, index - 1)}
            aria-label="prev"
          >
            <ChevronLeft size={22} />
          </button>
          <button
            className="absolute right-2 top-1/2 -translate-y-1/2 w-10 h-10 rounded-full bg-white/15 text-white flex items-center justify-center active:scale-90"
            onClick={(e) => go(e, index + 1)}
            aria-label="next"
          >
            <ChevronRight size={22} />
          </button>
          <div className="absolute bottom-4 left-0 right-0 text-center text-white/80 text-sm font-semibold">
            {index + 1} / {urls.length}
          </div>
        </>
      )}
    </div>
  );
}

// ── Галерея фото объекта (загрузка/импорт/удаление) ─────────────────
function PhotoGallery({ apartmentId, onChange }: { apartmentId: number; onChange?: () => void }) {
  const { t, toast } = useApp();
  const [photos, setPhotos] = useState<ApartmentPhoto[] | null>(null);
  const [busy, setBusy] = useState(false);
  const [prog, setProg] = useState<{ cur: number; total: number } | null>(null);
  const [viewer, setViewer] = useState<number | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);

  async function load() {
    const r = await api<ApartmentPhoto[]>(`/api/v1/apartments/${apartmentId}/photos`);
    setPhotos(r.ok && Array.isArray(r.data) ? r.data : []);
  }
  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [apartmentId]);

  async function onFiles(e: React.ChangeEvent<HTMLInputElement>) {
    const files = e.target.files;
    if (!files || !files.length) return;
    setBusy(true);
    toast(t("uploadingPhotos"), "info");
    let lastOk: ApartmentPhoto[] | null = null;
    let failed: { data: unknown; status: number } | null = null;
    const arr = Array.from(files);
    // По одному фото за запрос (JSON), чтобы каждый запрос был лёгким.
    for (let i = 0; i < arr.length; i++) {
      setProg({ cur: i + 1, total: arr.length });
      const dataUrl = await downscaleToDataUrl(arr[i]);
      const r = await uploadOnePhoto(apartmentId, dataUrl);
      if (r.ok && r.data) lastOk = r.data;
      else {
        failed = { data: r.data, status: r.status };
        break;
      }
    }
    setProg(null);
    setBusy(false);
    e.target.value = "";
    if (lastOk) setPhotos(lastOk);
    if (lastOk && !failed) {
      toast(t("photoAdded"), "ok");
      onChange?.();
    } else if (failed) {
      onChange?.();
      toast(errText(failed.data, failed.status), "err");
    }
  }

  async function importTg() {
    const url = window.prompt(t("importTgPrompt"), "");
    if (!url) return;
    setBusy(true);
    toast(t("importingPhotos"), "info");
    const r = await api<ApartmentPhoto[]>(`/api/v1/apartments/${apartmentId}/photos/import-telegram`, { method: "POST", body: { url } });
    setBusy(false);
    if (r.ok && r.data) {
      setPhotos(r.data);
      toast(t("photoAdded"), "ok");
      onChange?.();
    } else toast(errText(r.data, r.status), "err");
  }

  async function del(id: number) {
    if (!(await confirmDialog(t("delPhotoQ")))) return;
    const r = await api(`/api/v1/apartments/${apartmentId}/photos/${id}`, { method: "DELETE" });
    if (r.ok) {
      toast(t("photoDeleted"), "ok");
      load();
      onChange?.();
    } else toast(errText(r.data, r.status), "err");
  }

  return (
    <div className="mb-3">
      {photos && photos.length > 0 && (
        <div className="grid grid-cols-3 gap-2 mb-2.5">
          {photos.map((p, i) => (
            <div
              key={p.id}
              className={cx2(
                "relative aspect-square rounded-[14px] overflow-hidden bg-[var(--soft)] border border-line",
                // Первое фото — крупная «обложка» 2×2: премиальная подача объекта.
                i === 0 && photos.length > 1 && "col-span-2 row-span-2"
              )}
            >
              <button type="button" className="block w-full h-full active:scale-95 transition" onClick={() => setViewer(i)}>
                <img src={p.url} alt="" loading="lazy" className="w-full h-full object-cover" />
              </button>
              <button
                onClick={() => del(p.id)}
                className="absolute top-1 right-1 w-7 h-7 rounded-full bg-black/55 text-white flex items-center justify-center active:scale-90"
                aria-label={t("del")}
              >
                <X size={15} />
              </button>
            </div>
          ))}
        </div>
      )}
      <div className="flex gap-2 flex-wrap">
        <input ref={fileRef} type="file" accept="image/*" multiple hidden onChange={onFiles} />
        <Button size="sm" variant="ghost" disabled={busy} onClick={() => fileRef.current?.click()}>
          <Camera size={15} /> {t("addPhotos")}
        </Button>
        <Button size="sm" variant="ghost" disabled={busy} onClick={importTg}>
          <Send size={15} /> {t("importTg")}
        </Button>
      </div>
      {prog && (
        <div className="mt-2">
          <div className="text-[12px] font-bold text-muted mb-1">
            {t("uploadingPhotos")} {prog.cur}/{prog.total}
          </div>
          <div className="h-1.5 rounded-full bg-[var(--soft)] overflow-hidden">
            <div className="h-full bg-primary transition-all" style={{ width: `${(prog.cur / prog.total) * 100}%` }} />
          </div>
        </div>
      )}
      <Hint>{t("photosHint")}</Hint>
      {viewer != null && photos && photos.length > 0 && (
        <Lightbox urls={photos.map((p) => p.url)} index={viewer} onClose={() => setViewer(null)} onIndex={setViewer} />
      )}
    </div>
  );
}

// ── Карточка в списке ───────────────────────────────────────────────
export function ApartmentCard({ o, onOpen }: { o: Apartment; onOpen?: (() => void) | false }) {
  const { t, L } = useApp();
  const nav = useNav();
  // onOpen: не задан → открываем карточку объекта (по умолчанию); false → карточка
  // не кликабельна (чужой объект в общей базе — его детали нам недоступны);
  // функция → своё действие.
  const interactive = onOpen !== false;
  const parts = [L.typeLabel(o.type), o.district, o.rooms != null ? `${o.rooms} ${t("f_rooms").toLowerCase()}` : null]
    .filter(Boolean)
    .join(" · ");
  const accent: Record<string, string> = {
    active: "border-l-emerald-500",
    deposit: "border-l-amber-500",
    sold: "border-l-slate-400",
    rented: "border-l-slate-400",
    archived: "border-l-slate-400",
  };
  const Comp: React.ElementType = interactive ? "button" : "div";
  return (
    <Comp
      onClick={
        interactive
          ? () => {
              haptic();
              if (typeof onOpen === "function") onOpen();
              else nav.push({ name: "objectDetail", id: o.id });
            }
          : undefined
      }
      className={cx2(
        "w-full text-left mt-2.5 rounded-xl2 bg-card border border-line shadow-soft p-3.5 transition border-l-[3px]",
        interactive ? "active:scale-[.99] hover:shadow-lg2" : "",
        accent[o.status] || "border-l-slate-400"
      )}
    >
      {/* Фото растянуто на всю высоту карточки (items-stretch): максимум веса
          снимку без увеличения самой карточки. */}
      <div className="flex items-stretch gap-3">
        <div className="w-[88px] shrink-0 self-stretch rounded-[14px] bg-primary-soft text-primary flex items-center justify-center overflow-hidden">
          {o.photo_url ? (
            <img src={o.photo_url} alt="" loading="lazy" className="w-full h-full object-cover" />
          ) : (
            <HomeIcon size={26} className="opacity-70" />
          )}
        </div>
        <div className="min-w-0 flex-1">
          <div className="flex items-center justify-between gap-2">
            <span className="font-extrabold flex items-center gap-1.5 min-w-0">
              <span className="shrink-0">№{o.display_id}</span>
              {o.deal_type === "rent" && <Badge color="blue">{t("dealRent")}</Badge>}
            </span>
            <Badge color={STATUS_BADGE[o.status] || "gray"}>{L.statusLabel(o.status, o.deal_type)}</Badge>
          </div>
          {o.name && <div className="text-[13px] text-muted truncate">{o.name}</div>}
          <div className="text-[13px] text-muted">{parts || t("notSet")}</div>
          <div className="text-[13px] text-muted">
            {fmtPrice(o.price, o.currency) ? (
              <>
                {t("f_price")}: <span className="font-extrabold text-primary">{fmtPrice(o.price, o.currency)}{L.priceSuffix(o.deal_type, o.rent_period)}</span>
              </>
            ) : (
              <span className="text-muted">{t("priceNotSet")}</span>
            )}
          </div>
          {o.created_by_name && (
            <div className="text-[13px] text-muted">
              {t("addedBy")}: {o.created_by_name}
            </div>
          )}
        </div>
      </div>
    </Comp>
  );
}

function cx2(...a: Array<string | false | null | undefined>) {
  return a.filter(Boolean).join(" ");
}

// ── Экран: общая база МЛС (открыта всем агентствам) ─────────────────
// Показывает объекты, которыми поделились агентства платформы. Номер собственника
// виден ТОЛЬКО у своих объектов (у чужих — скрыт, карточка не открывается).
const MLS_STATUSES: { key: string; labelKey: string }[] = [
  { key: "active", labelKey: "statusActive" },
  { key: "deposit", labelKey: "statusDeposit" },
  { key: "sold", labelKey: "statusSold" },
];

export function MlsBrowseScreen() {
  const { t, user } = useApp();
  const [items, setItems] = useState<MlsPoolItem[] | null>(null);
  const [total, setTotal] = useState(0);
  const [status, setStatus] = useState("active");
  const [q, setQ] = useState("");
  const [offset, setOffset] = useState(0);
  const [busy, setBusy] = useState(false);
  const LIMIT = 20;

  async function load(reset: boolean) {
    setBusy(true);
    const off = reset ? 0 : offset;
    const params = new URLSearchParams({ status, limit: String(LIMIT), offset: String(off) });
    if (q.trim()) params.set("q", q.trim());
    const r = await api<MlsPoolResponse>("/api/v1/mls/browse?" + params.toString());
    setBusy(false);
    if (r.ok && r.data) {
      const data = r.data;
      setTotal(data.total);
      setItems((prev) => (reset || !prev ? data.items : [...prev, ...data.items]));
      setOffset(off + data.items.length);
    } else if (reset) setItems([]);
  }

  useEffect(() => {
    setItems(null);
    setOffset(0);
    const id = window.setTimeout(() => load(true), q ? 300 : 0);
    return () => window.clearTimeout(id);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [status, q]);

  return (
    <div>
      <Hint>{t("mlsBrowseHint")}</Hint>
      <div className="relative mt-2 mb-2">
        <SearchIcon size={16} className="absolute left-3 top-1/2 -translate-y-1/2 text-muted" />
        <Input className="pl-9" placeholder={t("mlsSearchPlaceholder")} value={q} onChange={(e) => setQ(e.target.value)} />
      </div>
      <div className="flex gap-2 mb-1">
        {MLS_STATUSES.map((s) => (
          <button
            key={s.key}
            type="button"
            onClick={() => setStatus(s.key)}
            className={"flex-1 min-h-[38px] rounded-xl text-[13px] font-bold transition active:scale-95 " + (status === s.key ? "bg-primary text-white shadow-glow" : "bg-[var(--soft)] text-muted")}
          >
            {t(s.labelKey)}
          </button>
        ))}
      </div>
      {items === null ? (
        <Spinner />
      ) : !items.length ? (
        <Empty icon={<HomeIcon size={24} />}>{t("mlsEmpty")}</Empty>
      ) : (
        <>
          <div className="text-[12.5px] text-muted mt-2 mb-1 mx-0.5">
            {t("mlsTotal")}: {total}
          </div>
          {items.map((it, i) => {
            const mine = user?.agency_id != null && it.agency_id === user.agency_id;
            return (
              <div key={String(it.apartment.id) + "_" + i}>
                <div className="flex items-center gap-1.5 mt-2.5 mx-0.5 text-[11.5px] font-bold flex-wrap">
                  <span className={"px-1.5 py-0.5 rounded-full " + (mine ? "bg-emerald-100 text-emerald-700" : "bg-primary-soft text-primary")}>
                    {mine ? t("mlsMine") : it.agency_name || t("mlsOtherAgency")}
                  </span>
                  {!mine && (
                    <span className="text-muted inline-flex items-center gap-1">
                      <Lock size={11} /> {t("mlsContactHidden")}
                    </span>
                  )}
                </div>
                <ApartmentCard o={it.apartment} onOpen={mine ? undefined : false} />
              </div>
            );
          })}
          {items.length < total && (
            <Button full variant="ghost" className="mt-3" disabled={busy} onClick={() => load(false)}>
              {busy ? t("loading") : t("showMore")}
            </Button>
          )}
        </>
      )}
    </div>
  );
}

// Кнопка «Запомнить для клиента»: текущие фильтры поиска сохраняем как заявку
// клиента (открывается экран выбора/создания клиента).
function SaveRequestButton({ params }: { params: SearchParams }) {
  const { t } = useApp();
  const nav = useNav();
  return (
    <button
      onClick={() => {
        haptic();
        nav.push({ name: "saveRequest", criteria: params });
      }}
      className="w-full mt-3 rounded-xl2 p-3.5 text-left text-white shadow-glow active:scale-[.99] transition flex items-center gap-3"
      style={{ background: "var(--grad)" }}
    >
      <span className="w-10 h-10 rounded-xl bg-white/20 flex items-center justify-center shrink-0">
        <UserPlus size={20} />
      </span>
      <span className="min-w-0">
        <span className="block font-extrabold">{t("rememberForClient")}</span>
        <span className="block text-[12.5px] opacity-90">{t("rememberForClientSub")}</span>
      </span>
    </button>
  );
}

// ── Список/поиск с пагинацией ───────────────────────────────────────
export function ObjectList({ params, allowSaveRequest }: { params: SearchParams; allowSaveRequest?: boolean }) {
  const { t } = useApp();
  const [items, setItems] = useState<Apartment[]>([]);
  const [total, setTotal] = useState(0);
  const [offset, setOffset] = useState(0);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState<string | null>(null);

  async function load(reset: boolean) {
    setLoading(true);
    const off = reset ? 0 : offset;
    const q = buildQuery({ ...params, status: params.status || "all", limit: 20, offset: off });
    const r = await api<ApartmentList>("/api/v1/apartments?" + q);
    setLoading(false);
    if (!r.ok || !r.data) {
      setErr(`${t("notFound")} (${r.status})`);
      return;
    }
    setErr(null);
    const newItems = r.data.items || [];
    setTotal(r.data.total || 0);
    setItems((prev) => (reset ? newItems : [...prev, ...newItems]));
    setOffset(off + newItems.length);
  }

  useEffect(() => {
    load(true);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [JSON.stringify(params)]);

  if (loading && !items.length) return <ListSkeleton />;
  if (err) return <Empty>{err}</Empty>;
  if (!items.length)
    return (
      <div>
        <Empty icon={<SearchX size={24} />} sub={t("emptyListSub")}>
          {t("notFound")}
        </Empty>
        {allowSaveRequest && <SaveRequestButton params={params} />}
      </div>
    );
  const left = total - items.length;
  return (
    <div>
      <div className="text-[13px] text-muted my-1.5">
        {t("found")}: {total}
      </div>
      {items.map((o) => (
        <ApartmentCard key={o.id} o={o} />
      ))}
      {left > 0 && (
        <Button variant="ghost" full className="mt-3" onClick={() => load(false)}>
          {t("showMore")} ({left})
        </Button>
      )}
      {allowSaveRequest && <SaveRequestButton params={params} />}
    </div>
  );
}

// ── Выбор фото при создании объекта (до того, как объект сохранён) ──
function PendingPhotos({
  files,
  setFiles,
  tgUrls,
  setTgUrls,
  imgUrls = [],
  setImgUrls,
}: {
  files: File[];
  setFiles: (f: File[]) => void;
  tgUrls: string[];
  setTgUrls: (u: string[]) => void;
  imgUrls?: string[];
  setImgUrls?: (u: string[]) => void;
}) {
  const { t } = useApp();
  const fileRef = useRef<HTMLInputElement>(null);
  const [previews, setPreviews] = useState<string[]>([]);
  useEffect(() => {
    const urls = files.map((f) => URL.createObjectURL(f));
    setPreviews(urls);
    return () => urls.forEach((u) => URL.revokeObjectURL(u));
  }, [files]);

  return (
    <>
      <div className="text-[12px] font-extrabold uppercase tracking-wider text-primary mt-5 mb-1 pt-3 border-t border-[var(--border)]">
        {t("photos")}
      </div>
      {(previews.length > 0 || tgUrls.length > 0 || imgUrls.length > 0) && (
        <div className="grid grid-cols-3 gap-2 mb-2.5">
          {imgUrls.map((u, i) => (
            <div key={"i" + i} className="relative aspect-square rounded-[14px] overflow-hidden bg-[var(--soft)] border border-line">
              <img src={u} alt="" className="w-full h-full object-cover" />
              <button
                type="button"
                onClick={() => setImgUrls?.(imgUrls.filter((_, idx) => idx !== i))}
                className="absolute top-1 right-1 w-7 h-7 rounded-full bg-black/55 text-white flex items-center justify-center active:scale-90"
              >
                <X size={15} />
              </button>
            </div>
          ))}
          {previews.map((src, i) => (
            <div key={"f" + i} className="relative aspect-square rounded-[14px] overflow-hidden bg-[var(--soft)] border border-line">
              <img src={src} alt="" className="w-full h-full object-cover" />
              <button
                type="button"
                onClick={() => setFiles(files.filter((_, idx) => idx !== i))}
                className="absolute top-1 right-1 w-7 h-7 rounded-full bg-black/55 text-white flex items-center justify-center active:scale-90"
              >
                <X size={15} />
              </button>
            </div>
          ))}
          {tgUrls.map((u, i) => (
            <div key={"t" + i} className="relative aspect-square rounded-[14px] bg-[var(--soft)] border border-line flex items-center justify-center text-muted text-[11px] p-2 text-center">
              <Send size={18} />
              <button
                type="button"
                onClick={() => setTgUrls(tgUrls.filter((_, idx) => idx !== i))}
                className="absolute top-1 right-1 w-7 h-7 rounded-full bg-black/55 text-white flex items-center justify-center active:scale-90"
              >
                <X size={15} />
              </button>
            </div>
          ))}
        </div>
      )}
      <div className="flex gap-2 flex-wrap">
        <input
          ref={fileRef}
          type="file"
          accept="image/*"
          multiple
          hidden
          onChange={(e) => {
            if (e.target.files) setFiles([...files, ...Array.from(e.target.files)]);
            e.target.value = "";
          }}
        />
        <Button type="button" size="sm" variant="ghost" onClick={() => fileRef.current?.click()}>
          <Camera size={15} /> {t("addPhotos")}
        </Button>
        <Button
          type="button"
          size="sm"
          variant="ghost"
          onClick={() => {
            const url = window.prompt(t("importTgPrompt"), "");
            if (url && url.trim()) setTgUrls([...tgUrls, url.trim()]);
          }}
        >
          <Send size={15} /> {t("importTg")}
        </Button>
      </div>
      <Hint>{t("photosHint")}</Hint>
    </>
  );
}

// ── Импорт объявления по ссылке (AI-разбор) ─────────────────────────
function ImportFromLink({ onImported }: { onImported: (r: ListingImport) => void }) {
  const { t, toast } = useApp();
  const [url, setUrl] = useState("");
  const [busy, setBusy] = useState(false);

  async function run() {
    const v = url.trim();
    if (!v) return;
    setBusy(true);
    toast(t("importing"), "info");
    const r = await api<ListingImport>("/api/v1/apartments/import-preview", { method: "POST", body: { url: v } });
    setBusy(false);
    if (r.ok && r.data) {
      onImported(r.data);
      const warns = r.data.warnings || [];
      toast(warns.includes("few_fields") ? t("importFewFields") : t("importDone"), warns.includes("few_fields") ? "warn" : "ok");
      if (warns.includes("no_photos")) toast(t("importNoPhotos"), "warn");
    } else {
      toast(errText(r.data, r.status), "err");
    }
  }

  return (
    <Card className="mb-3 relative overflow-hidden">
      {/* Тонкое фиолетовое свечение — подсказывает, что здесь работает ИИ. */}
      <div
        className="absolute -right-14 -top-14 w-44 h-44 rounded-full pointer-events-none"
        style={{ background: "radial-gradient(circle, var(--ring), transparent 68%)" }}
      />
      <div className="relative">
        <div className="flex items-center gap-2.5 mb-2">
          <span className="w-9 h-9 rounded-[11px] flex items-center justify-center text-white shadow-glow" style={{ background: "var(--grad)" }}>
            <Sparkles size={17} />
          </span>
          <div>
            <div className="text-[14px] font-extrabold leading-tight">{t("aiImportTitle")}</div>
            <div className="text-[11.5px] text-muted">{t("importLinkLabel")}</div>
          </div>
        </div>
        <Input inputMode="url" placeholder="https://…" value={url} onChange={(e) => setUrl(e.target.value)} />
        <Button full className="mt-3" disabled={busy} onClick={run}>
          <Sparkles size={16} /> {busy ? t("importing") : t("importBtn")}
        </Button>
        <Hint>{t("importHint")}</Hint>
      </div>
    </Card>
  );
}

// ── Экран: добавить объект ──────────────────────────────────────────
export function AddObjectScreen() {
  const { t, toast } = useApp();
  const nav = useNav();
  const [saving, setSaving] = useState(false);
  const [files, setFiles] = useState<File[]>([]);
  const [tgUrls, setTgUrls] = useState<string[]>([]);
  // Импорт по ссылке: подставленные поля и найденные фото.
  const [imgUrls, setImgUrls] = useState<string[]>([]);
  const [imported, setImported] = useState<Partial<Apartment> | null>(null);
  const [formKey, setFormKey] = useState(0);

  function applyImport(r: ListingImport) {
    setImported({
      // Наименование намеренно НЕ заполняем из ИИ — пользователь вводит его сам
      // (или оставляет пустым). См. пожелание заказчика.
      name: null,
      deal_type: r.deal_type ?? "sale",
      rent_period: r.rent_period ?? "month",
      type: r.type ?? null,
      district: r.district ?? null,
      address: r.address ?? null,
      rooms: r.rooms ?? null,
      floor: r.floor ?? null,
      total_floors: r.total_floors ?? null,
      land_area: r.land_area ?? null,
      area: r.area ?? null,
      condition: r.condition ?? null,
      furniture_appliances: r.furniture_appliances ?? null,
      price: r.price ?? null,
      currency: r.currency || "USD",
      owner_phone: r.owner_phone ?? null,
      description: r.description ?? null,
      source_link: r.source_link ?? null,
      // «Источник» заполняем названием канала/площадки — как в массовом импорте.
      source: r.source ?? null,
    });
    setImgUrls(r.photo_urls || []);
    setFormKey((k) => k + 1); // перемонтировать форму, чтобы поля перечитались
  }

  async function submit(body: Record<string, unknown>) {
    setSaving(true);
    // Предупреждаем о возможных дублях по ключевым полям (можно всё равно добавить).
    const dq = buildQuery({
      district: body.district as string | undefined,
      rooms: body.rooms as number | undefined,
      type: body.type as string | undefined,
      price: body.price as number | undefined,
      address: body.address as string | undefined,
    });
    if (dq) {
      const sim = await api<Apartment[]>("/api/v1/apartments/similar?" + dq);
      if (sim.ok && Array.isArray(sim.data) && sim.data.length) {
        const ids = sim.data.map((a) => "№" + a.display_id).join(", ");
        if (!(await confirmDialog(t("dupFound") + " " + ids + "\n\n" + t("dupAsk")))) {
          setSaving(false);
          return;
        }
      }
    }
    const r = await api<Apartment>("/api/v1/apartments", { method: "POST", body });
    if (!r.ok || !r.data) {
      setSaving(false);
      toast(errText(r.data, r.status), "err");
      return;
    }
    const newId = r.data.id;
    // Прикрепляем выбранные фото к уже созданному объекту (по одному, JSON).
    // Каждое фото — отдельно: одна ошибка не должна срывать остальные.
    let photoFail = 0;
    for (const f of files) {
      try {
        const dataUrl = await downscaleToDataUrl(f);
        const up = await uploadOnePhoto(newId, dataUrl);
        if (!up.ok) photoFail++;
      } catch {
        photoFail++;
      }
    }
    for (const url of tgUrls) {
      try {
        const up = await api(`/api/v1/apartments/${newId}/photos/import-telegram`, { method: "POST", body: { url } });
        if (!up.ok) photoFail++;
      } catch {
        photoFail++;
      }
    }
    // Фото, найденные при импорте объявления (прямые ссылки) — одним запросом.
    if (imgUrls.length) {
      try {
        const up = await api(`/api/v1/apartments/${newId}/photos/import-urls`, { method: "POST", body: { urls: imgUrls } });
        if (!up.ok) photoFail++;
      } catch {
        photoFail++;
      }
    }
    setSaving(false);
    toast(t("objCreated") + r.data.display_id, "ok");
    if (photoFail > 0) toast(t("photoPartialFail"), "warn");
    // Открываем карточку нового объекта (там видно фото и можно дозагрузить).
    nav.pop();
    nav.push({ name: "objectDetail", id: newId });
  }

  return (
    <>
      <ImportFromLink onImported={applyImport} />
      <ObjectForm key={formKey} initial={imported || undefined} onSubmit={submit} submitLabel={t("saveObject")} saving={saving}>
        <PendingPhotos
          files={files}
          setFiles={setFiles}
          tgUrls={tgUrls}
          setTgUrls={setTgUrls}
          imgUrls={imgUrls}
          setImgUrls={setImgUrls}
        />
      </ObjectForm>
    </>
  );
}

// ── Экран: редактирование ───────────────────────────────────────────
export function ObjectEditScreen({ obj }: { obj: Apartment }) {
  const { t, toast } = useApp();
  const nav = useNav();
  const [saving, setSaving] = useState(false);
  async function submit(body: Record<string, unknown>) {
    setSaving(true);
    const r = await api<Apartment>("/api/v1/apartments/" + obj.id, { method: "PATCH", body });
    setSaving(false);
    if (r.ok) {
      toast(t("saved"), "ok");
      nav.pop();
    } else toast(errText(r.data, r.status), "err");
  }
  return (
    <>
      <ObjectForm initial={obj} onSubmit={submit} submitLabel={t("saveChanges")} saving={saving} />
      <Hint>{t("clearHint")}</Hint>
    </>
  );
}

// ── Экран: поиск (форма фильтров) ───────────────────────────────────
export function SearchScreen() {
  const { t, L } = useApp();
  const nav = useNav();
  const districts = useDistricts();
  const [status, setStatus] = useState("all");
  const [deal, setDeal] = useState("");
  const [types, setTypes] = useState<string[]>([]);
  const [dist, setDist] = useState<string[]>([]);
  const [q, setQ] = useState("");
  const [rmin, setRmin] = useState("");
  const [rmax, setRmax] = useState("");
  const [fmin, setFmin] = useState("");
  const [fmax, setFmax] = useState("");
  const [lamin, setLamin] = useState("");
  const [lamax, setLamax] = useState("");
  const [pmin, setPmin] = useState("");
  const [pmax, setPmax] = useState("");
  const [cur, setCur] = useState("");

  const toggle = (arr: string[], set: (v: string[]) => void, v: string) =>
    set(arr.includes(v) ? arr.filter((x) => x !== v) : [...arr, v]);

  // Какие фильтры показывать. Независимо: «Соток» — если выбран дом/участок/земля;
  // «Этаж» — если выбрана квартира/коммерция (или тип не выбран вовсе). При выборе
  // обоих видов сразу (например, квартира + участок) показываем И «Этаж», И «Соток».
  const showLand = types.some(hasLandArea);
  const showFloor = types.length === 0 || types.some((tp) => !hasLandArea(tp));

  function run() {
    const params: SearchParams = { status };
    if (deal) params.deal_type = deal;
    if (types.length) params.types = types;
    if (dist.length) params.districts = dist;
    if (q.trim()) params.q = q.trim();
    if (rmin) params.rooms_min = rmin;
    if (rmax) params.rooms_max = rmax;
    if (showLand) {
      if (lamin) params.land_area_min = lamin;
      if (lamax) params.land_area_max = lamax;
    }
    if (showFloor) {
      if (fmin) params.floor_min = fmin;
      if (fmax) params.floor_max = fmax;
    }
    if (pmin) params.price_min = pmin;
    if (pmax) params.price_max = pmax;
    if (cur) params.currency = cur;
    nav.push({ name: "objectList", params, titleKey: "findObject" });
  }

  // Статусы зависят от типа сделки: у аренды «свободна/бронь/сдан».
  const statusOpts: { value: string; label: string }[] =
    deal === "rent"
      ? [
          { value: "all", label: t("notSet") },
          { value: "active", label: t("rentFree") },
          { value: "deposit", label: t("rentReserved") },
          { value: "rented", label: t("statusRented") },
        ]
      : [
          { value: "all", label: t("notSet") },
          { value: "active", label: t("statusActive") },
          { value: "deposit", label: t("statusDeposit") },
          { value: "sold", label: t("statusSold") },
        ];

  return (
    <Card>
      <div className="mb-3">
        <div className="text-[12px] font-bold text-muted mb-1.5">{t("dealType")}</div>
        <Segmented
          value={deal as "" | "sale" | "rent"}
          onChange={(v) => {
            setDeal(v);
            setStatus("all"); // статусы у продажи/аренды разные — сбрасываем
          }}
          options={[
            { value: "", label: t("dealAll") },
            { value: "sale", label: t("dealSale") },
            { value: "rent", label: t("dealRent") },
          ]}
        />
      </div>
      <Field label={t("searchText")}>
        <Input value={q} onChange={(e) => setQ(e.target.value)} />
      </Field>
      <Field label={t("f_status")}>
        <Select value={status} onChange={(e) => setStatus(e.target.value)}>
          {statusOpts.map((s) => (
            <option key={s.value} value={s.value}>
              {s.label}
            </option>
          ))}
        </Select>
      </Field>
      <div className="mt-3">
        <div className="text-[12px] font-bold text-muted mb-1.5">{t("f_type")}</div>
        <Chips
          options={OBJ_TYPE_VALUES.map((v) => ({ value: v, label: L.typeLabel(v) }))}
          selected={types}
          onToggle={(v) => toggle(types, setTypes, v)}
        />
        <Hint>{t("typeMultiHint")}</Hint>
      </div>
      {districts.length > 0 && (
        <div className="mt-3">
          <div className="text-[12px] font-bold text-muted mb-1.5">{t("f_district")}</div>
          <Chips
            options={districts.map((d) => ({ value: d.value, label: d.value }))}
            selected={dist}
            onToggle={(v) => toggle(dist, setDist, v)}
          />
        </div>
      )}
      <div className="flex gap-2">
        <div className="flex-1">
          <Field label={t("roomsFrom")}>
            <Input inputMode="numeric" value={rmin} onChange={(e) => setRmin(e.target.value)} />
          </Field>
        </div>
        <div className="flex-1">
          <Field label={t("to")}>
            <Input inputMode="numeric" value={rmax} onChange={(e) => setRmax(e.target.value)} />
          </Field>
        </div>
      </div>
      {showFloor && (
        <div className="flex gap-2">
          <div className="flex-1 min-w-0">
            <Field label={t("floorFrom")}>
              <Input inputMode="numeric" value={fmin} onChange={(e) => setFmin(e.target.value)} />
            </Field>
          </div>
          <div className="flex-1 min-w-0">
            <Field label={t("to")}>
              <Input inputMode="numeric" value={fmax} onChange={(e) => setFmax(e.target.value)} />
            </Field>
          </div>
        </div>
      )}
      {showLand && (
        <div className="flex gap-2">
          <div className="flex-1 min-w-0">
            <Field label={t("landFrom")}>
              <Input inputMode="decimal" value={lamin} onChange={(e) => setLamin(e.target.value)} />
            </Field>
          </div>
          <div className="flex-1 min-w-0">
            <Field label={t("to")}>
              <Input inputMode="decimal" value={lamax} onChange={(e) => setLamax(e.target.value)} />
            </Field>
          </div>
        </div>
      )}
      <div className="flex gap-2">
        <div className="flex-1">
          <Field label={t("priceFrom")}>
            <Input inputMode="numeric" value={pmin} onChange={(e) => setPmin(e.target.value)} />
          </Field>
        </div>
        <div className="flex-1">
          <Field label={t("to")}>
            <Input inputMode="numeric" value={pmax} onChange={(e) => setPmax(e.target.value)} />
          </Field>
        </div>
      </div>
      <Field label={t("priceCurrency")}>
        <Select value={cur} onChange={(e) => setCur(e.target.value)}>
          <option value="">{t("anyCurrency")}</option>
          {CURRENCIES.map((c) => (
            <option key={c} value={c}>
              {c}
            </option>
          ))}
        </Select>
      </Field>
      <Button full className="mt-4" onClick={run}>
        <SearchIcon size={18} /> {t("searchBtn")}
      </Button>
    </Card>
  );
}

// ── Экран: «Моя база» (не проданные / проданные) ────────────────────
export function DatabaseScreen() {
  const { t } = useApp();
  const nav = useNav();
  const views = ["working", "closed", "archived"] as const;
  const [view, setView] = useState<(typeof views)[number]>("working");
  const [deal, setDeal] = useState("");
  const [showFilter, setShowFilter] = useState(false);
  const [from, setFrom] = useState("");
  const [to, setTo] = useState("");
  const hasFilter = !!(from || to);

  function swipe(d: 1 | -1) {
    const i = views.indexOf(view);
    const n = i + d;
    if (n >= 0 && n < views.length) {
      haptic();
      setView(views[n]);
    }
  }

  return (
    <div>
      <div className="flex justify-between items-center mb-1.5">
        <button
          onClick={() => {
            haptic();
            nav.push({ name: "duplicates" });
          }}
          className="inline-flex items-center gap-1.5 rounded-xl border px-3 py-1.5 text-[12px] font-bold transition active:scale-95 bg-card border-line text-muted"
        >
          <Copy size={14} /> {t("duplicatesBtn")}
        </button>
        <button
          onClick={() => {
            haptic();
            setShowFilter((v) => !v);
          }}
          className={cx2(
            "inline-flex items-center gap-1.5 rounded-xl border px-3 py-1.5 text-[12px] font-bold transition active:scale-95",
            hasFilter || showFilter
              ? "bg-primary-soft border-primary text-primary"
              : "bg-card border-line text-muted",
          )}
        >
          <SlidersHorizontal size={14} /> {t("filterBtn")}
          {hasFilter && <span className="w-1.5 h-1.5 rounded-full bg-primary" />}
        </button>
      </div>

      <div className="mb-2">
        <Segmented
          value={deal as "" | "sale" | "rent"}
          onChange={(v) => {
            haptic();
            setDeal(v);
          }}
          options={[
            { value: "", label: t("dealAll") },
            { value: "sale", label: t("dealSale") },
            { value: "rent", label: t("dealRent") },
          ]}
        />
      </div>

      <Segmented
        value={view}
        onChange={(v) => {
          haptic();
          setView(v);
        }}
        options={[
          { value: "working", label: t("tabWorking") },
          { value: "closed", label: deal === "rent" ? t("statusRented") : t("statusSold") },
          { value: "archived", label: t("archive") },
        ]}
      />

      {showFilter && (
        <div className="mt-2 rounded-xl2 bg-card border border-line shadow-soft p-3">
          <div className="flex gap-2">
            <label className="flex-1 min-w-0 text-[12px] font-bold text-muted">
              {t("dateFrom")}
              <input
                type="date"
                value={from}
                max={to || undefined}
                onChange={(e) => setFrom(e.target.value)}
                className="mt-1 block w-full min-w-0 box-border appearance-none rounded-xl bg-[var(--soft)] border border-line px-3 py-2 text-sm text-text"
              />
            </label>
            <label className="flex-1 min-w-0 text-[12px] font-bold text-muted">
              {t("dateTo")}
              <input
                type="date"
                value={to}
                min={from || undefined}
                onChange={(e) => setTo(e.target.value)}
                className="mt-1 block w-full min-w-0 box-border appearance-none rounded-xl bg-[var(--soft)] border border-line px-3 py-2 text-sm text-text"
              />
            </label>
          </div>
          {hasFilter && (
            <button
              onClick={() => {
                setFrom("");
                setTo("");
              }}
              className="mt-2 text-[12px] font-bold text-primary active:scale-95 transition"
            >
              {t("filterReset")}
            </button>
          )}
        </div>
      )}

      <Swipeable onSwipe={swipe} className="mt-1">
        {view === "archived" ? (
          <ArchiveScreen createdFrom={from || undefined} createdTo={to || undefined} />
        ) : (
          <ObjectList
            params={{
              status: view === "working" ? "unsold" : deal === "rent" ? "rented" : "sold",
              deal_type: deal || undefined,
              created_from: from || undefined,
              created_to: to || undefined,
            }}
          />
        )}
      </Swipeable>
    </div>
  );
}

// ── Экран: менеджер дубликатов ──────────────────────────────────────
// Группы возможных дубликатов (совпали фиксированные характеристики: тип, район,
// комнаты, этаж, этажность, площадь, сотки — цена не сравнивается) показываем
// по одной. В группе можно открыть/удалить лишние объекты, либо подтвердить «это
// не дубликаты» (группа больше не появится) и перейти к следующей.
type DupGroup = { key: string; label?: string | null; phone: string | null; count: number; items: Apartment[] };

export function DuplicatesScreen() {
  const { t, L, lang, toast } = useApp();
  const nav = useNav();
  const [groups, setGroups] = useState<DupGroup[] | null>(null);
  const [idx, setIdx] = useState(0);

  async function load() {
    const r = await api<DupGroup[]>("/api/v1/apartments/duplicates");
    setGroups(r.ok && Array.isArray(r.data) ? r.data : []);
  }
  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  if (!groups) return <Spinner />;
  if (!groups.length) return <Empty>{t("noDuplicates")}</Empty>;

  const pos = Math.min(idx, groups.length - 1);
  const g = groups[pos];

  async function removeItem(id: number) {
    if (!(await confirmDialog(t("delObjQ")))) return;
    const r = await api(`/api/v1/apartments/${id}`, { method: "DELETE" });
    if (r.ok) {
      toast(t("dupDeleted"), "ok");
      await load();
    } else toast(errText(r.data, r.status), "err");
  }

  async function notDup() {
    const r = await api("/api/v1/apartments/duplicates/dismiss", { method: "POST", body: { key: g.key } });
    if (r.ok) {
      toast(t("saved"), "ok");
      setIdx(0);
      await load();
    } else toast(errText(r.data, r.status), "err");
  }

  return (
    <div>
      <div className="flex items-center justify-between gap-2 mb-1">
        <span className="text-[13px] font-extrabold shrink-0">
          {t("group")} {pos + 1} / {groups.length}
        </span>
        {(g.label || g.phone) && (
          <span className="text-[12.5px] text-muted truncate">{g.label || "📞 " + g.phone}</span>
        )}
      </div>
      <Hint>{t("duplicatesHint")}</Hint>
      {g.items.map((o) => (
        <div key={o.id} className="mt-2.5 rounded-xl2 bg-card border border-line shadow-soft p-3.5">
          <div className="flex gap-3">
            {o.photo_url && (
              <img src={o.photo_url} alt="" loading="lazy" className="w-16 h-16 rounded-lg object-cover shrink-0" />
            )}
            <div className="min-w-0 flex-1">
              <div className="font-extrabold truncate">{o.name || "№ " + o.display_id}</div>
              <div className="text-[12px] text-muted truncate">
                {[L.typeLabel(o.type), o.district, o.rooms != null ? `${o.rooms} ${t("f_rooms").toLowerCase()}` : null]
                  .filter(Boolean)
                  .join(" · ")}
              </div>
              <div className="text-[12px] text-muted">
                {fmtPrice(o.price, o.currency)}
                {o.area != null ? ` · ${o.area} м²` : ""}
                {o.land_area != null ? ` · ${o.land_area} ${t("f_land_area").toLowerCase()}` : ""}
              </div>
              <div className="text-[11px] text-muted">
                {fmtDate(o.created_at, lang)}
                {/* Источник — чтобы было видно, какой канал оставить, какой удалить. */}
                {o.source ? <span className="text-primary font-bold"> · {o.source}</span> : ""}
              </div>
            </div>
          </div>
          <div className="mt-2 grid grid-cols-2 gap-2">
            <Button size="sm" variant="ghost" onClick={() => nav.push({ name: "objectDetail", id: o.id })}>
              {t("dupOpen")}
            </Button>
            <Button size="sm" variant="danger" onClick={() => removeItem(o.id)}>
              {t("dupDelete")}
            </Button>
          </div>
        </div>
      ))}
      <div className="mt-4 grid grid-cols-2 gap-2">
        <Button full variant="ghost" onClick={notDup}>
          {t("notDuplicates")}
        </Button>
        <Button full onClick={() => setIdx((i) => Math.min(i + 1, groups.length - 1))} disabled={pos >= groups.length - 1}>
          {t("nextGroup")}
        </Button>
      </div>
    </div>
  );
}

// ── Экран: архив (удалённые объекты) ────────────────────────────────
// Видят все сотрудники. Карточка кликабельна → открывается просмотр объекта,
// и уже внутри (для владельца агентства) доступны «Восстановить» и
// «Удалить навсегда».
function ArchiveCard({ o }: { o: Apartment }) {
  const { t, L } = useApp();
  const nav = useNav();
  const parts = [L.typeLabel(o.type), o.district, o.rooms != null ? `${o.rooms} ${t("f_rooms").toLowerCase()}` : null]
    .filter(Boolean)
    .join(" · ");

  return (
    <button
      onClick={() => {
        haptic();
        nav.push({ name: "objectDetail", id: o.id });
      }}
      className="w-full text-left mt-2.5 rounded-xl2 bg-card border border-line shadow-soft p-3.5 transition active:scale-[.99] hover:shadow-lg2 border-l-[3px] border-l-slate-400"
    >
      <div className="flex items-center justify-between gap-2">
        <span className="font-extrabold">№{o.display_id}</span>
        <Badge color="gray">{L.statusLabel(o.status, o.deal_type)}</Badge>
      </div>
      {o.name && <div className="text-[13px] text-muted truncate">{o.name}</div>}
      <div className="text-[13px] text-muted">{parts || t("notSet")}</div>
      <div className="text-[13px] text-muted">
        {fmtPrice(o.price, o.currency) ? (
              <>
                {t("f_price")}: <span className="font-extrabold text-primary">{fmtPrice(o.price, o.currency)}</span>
              </>
            ) : (
              <span className="text-muted">{t("priceNotSet")}</span>
            )}
      </div>
    </button>
  );
}

export function ArchiveScreen({ createdFrom, createdTo }: { createdFrom?: string; createdTo?: string } = {}) {
  const { t } = useApp();
  const [items, setItems] = useState<Apartment[]>([]);
  const [total, setTotal] = useState(0);
  const [offset, setOffset] = useState(0);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState<string | null>(null);

  async function load(reset: boolean) {
    setLoading(true);
    const off = reset ? 0 : offset;
    const r = await api<ApartmentList>(
      "/api/v1/apartments/archived?" +
        buildQuery({ limit: 20, offset: off, created_from: createdFrom || undefined, created_to: createdTo || undefined }),
    );
    setLoading(false);
    if (!r.ok || !r.data) {
      setErr(`${t("notFound")} (${r.status})`);
      return;
    }
    setErr(null);
    const newItems = r.data.items || [];
    setTotal(r.data.total || 0);
    setItems((prev) => (reset ? newItems : [...prev, ...newItems]));
    setOffset(off + newItems.length);
  }

  useEffect(() => {
    load(true);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [createdFrom, createdTo]);

  if (loading && !items.length) return <ListSkeleton />;
  if (err) return <Empty>{err}</Empty>;
  if (!items.length) return <Empty icon={<ArchiveIcon size={24} />}>{t("archiveEmpty")}</Empty>;
  const left = total - items.length;
  return (
    <div>
      <Hint>{t("archiveHint")}</Hint>
      <div className="text-[13px] text-muted my-1.5">
        {t("found")}: {total}
      </div>
      {items.map((o) => (
        <ArchiveCard key={o.id} o={o} />
      ))}
      {left > 0 && (
        <Button variant="ghost" full className="mt-3" onClick={() => load(false)}>
          {t("showMore")} ({left})
        </Button>
      )}
    </div>
  );
}

// ── Экран: карточка объекта ─────────────────────────────────────────
// Доступные переходы статуса зависят от типа сделки. Аренда: свободна → бронь →
// сдан → снова свободна. Продажа: активен → задаток → продан → снова активен.
function statusTransitions(status: string, dealType?: string | null): { to: string; key: string }[] {
  if (dealType === "rent") {
    const TX: Record<string, { to: string; key: string }[]> = {
      active: [
        { to: "deposit", key: "toReserve" },
        { to: "rented", key: "toRented" },
      ],
      deposit: [
        { to: "active", key: "removeReserve" },
        { to: "rented", key: "toRented" },
      ],
      rented: [{ to: "active", key: "backToFree" }],
    };
    return TX[status] || [];
  }
  const TX: Record<string, { to: string; key: string }[]> = {
    active: [
      { to: "deposit", key: "toDeposit" },
      { to: "sold", key: "toSold" },
    ],
    deposit: [
      { to: "active", key: "removeDeposit" },
      { to: "sold", key: "toSold" },
    ],
    sold: [{ to: "active", key: "backToActive" }],
  };
  return TX[status] || [];
}

const EV_FIELD_KEYS: Record<string, string> = {
  deal_type: "f_dealType", rent_period: "f_rentPeriod",
  name: "f_name", type: "f_type", district: "f_district", address: "f_address", rooms: "f_rooms",
  floor: "f_floor", total_floors: "f_tfloors", area: "f_area", price: "f_price", currency: "f_currency",
  condition: "f_condition", furniture_appliances: "f_furniture", owner_phone: "f_owner_phone",
  description: "f_desc", comment: "f_comment", photo_url: "f_photo", source_link: "f_source",
};

export function ObjectDetailScreen({ id }: { id: number }) {
  const { t, L, lang, settings, toast, user } = useApp();
  const nav = useNav();
  const isOwner = user?.role === "agency_admin" && !!user?.is_owner;
  const [o, setO] = useState<Apartment | null>(null);
  const [events, setEvents] = useState<ApartmentEvent[]>([]);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [shareOpen, setShareOpen] = useState(false);

  async function load(silent?: boolean) {
    if (!silent) setLoading(true);
    const r = await api<Apartment>("/api/v1/apartments/" + id);
    if (!silent) setLoading(false);
    if (r.ok && r.data) {
      setO(r.data);
      api<ApartmentEvent[]>("/api/v1/apartments/" + id + "/events").then((e) => {
        if (e.ok && Array.isArray(e.data)) setEvents(e.data);
      });
    } else if (!silent) toast(errText(r.data, r.status), "err");
  }
  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id]);

  if (loading || !o) return <Spinner />;

  const withLand = hasLandArea(o.type);
  const isRent = o.deal_type === "rent";
  const rows: [string | null, React.ReactNode][] = [
    // Тип сделки: для аренды показываем и срок (за месяц/сутки).
    [t("dealType"), isRent ? `${t("dealRent")} · ${o.rent_period === "day" ? t("rentDay") : t("rentMonth")}` : t("dealSale")],
    [t("f_name"), o.name],
    [t("f_type"), o.type ? L.typeLabel(o.type) : null],
    [t("f_district"), o.district],
    [t("f_address"), o.address],
    [t("f_rooms"), o.rooms],
    // Дом/участок/земля: «Соток» вместо «Этажа»; «Этажность» — для всех типов.
    withLand ? [t("f_land_area"), o.land_area] : [t("f_floor"), o.floor],
    [t("f_tfloors"), o.total_floors],
    [t("f_area"), o.area],
    [isRent ? t("priceRent") : t("f_price"), o.price != null ? `${fmtPrice(o.price, o.currency)}${L.priceSuffix(o.deal_type, o.rent_period)}` : null],
    [t("f_condition"), o.condition ? L.condLabel(o.condition) : null],
    [t("f_furniture"), L.faLabel(o.furniture_appliances)],
    [t("f_owner_phone"), o.owner_phone],
    [t("f_sourceName"), o.source],
    [t("f_desc"), o.description],
    [t("addedBy"), o.created_by_name],
    (o.status === "sold" || o.status === "rented") && o.archived_at
      ? [isRent ? t("statusRented") : t("soldDate"), fmtDate(o.archived_at, lang, settings?.timezone)]
      : [null, null],
  ];

  async function setStatus(to: string) {
    setBusy(true);
    const r = await api<Apartment>("/api/v1/apartments/" + id + "/status", { method: "POST", body: { status: to } });
    setBusy(false);
    if (r.ok && r.data) {
      setO(r.data);
      toast(t("done"), "ok");
      load();
    } else toast(errText(r.data, r.status), "err");
  }
  async function del() {
    if (!(await confirmDialog(t("delObjQ")))) return;
    const r = await api("/api/v1/apartments/" + id, { method: "DELETE" });
    if (r.ok) {
      toast(t("objDeleted"), "ok");
      nav.pop();
    } else toast(errText(r.data, r.status), "err");
  }
  // Восстановить объект из архива (только владелец агентства).
  async function restore() {
    setBusy(true);
    const r = await api("/api/v1/apartments/" + id + "/restore", { method: "POST" });
    setBusy(false);
    if (r.ok) {
      toast(t("restored"), "ok");
      nav.pop();
    } else toast(errText(r.data, r.status), "err");
  }
  // Удалить объект навсегда вместе с фото (необратимо; только владелец).
  async function purge() {
    if (!(await confirmDialog(t("deleteForeverQ")))) return;
    setBusy(true);
    const r = await api("/api/v1/apartments/" + id + "/permanent", { method: "DELETE" });
    setBusy(false);
    if (r.ok) {
      toast(t("deletedForever"), "ok");
      nav.pop();
    } else toast(errText(r.data, r.status), "err");
  }
  async function share() {
    setBusy(true);
    toast(t("shareSending"), "info");
    // Альбом со всеми фото уходит в личный чат сотрудника с ботом — оттуда он
    // одним нажатием пересылает клиенту. Так доходят ВСЕ фото (Telegram не даёт
    // мини-приложению отправить несколько фото напрямую в произвольный чужой чат).
    const r = await api<{ ok: boolean; photos: number }>(`/api/v1/apartments/${id}/share`, { method: "POST" });
    setBusy(false);
    if (r.ok) toast(t("shareAlbumSent"), "ok");
    else toast(errText(r.data, r.status), "err");
  }
  async function shareDirect() {
    // Прямая отправка в выбранный чат (нативный выбор получателя Telegram).
    // Ограничение Telegram: уходит ОДНА (обложечная) фотография + полный текст.
    if (!canShareMessage()) {
      toast(t("shareNeedUpdate"), "warn");
      return;
    }
    setBusy(true);
    const r = await api<{ prepared_message_id: string }>(`/api/v1/apartments/${id}/share-prepare`, { method: "POST" });
    if (!r.ok || !r.data) {
      setBusy(false);
      toast(errText(r.data, r.status), "err");
      return;
    }
    const sent = await shareMessage(r.data.prepared_message_id);
    setBusy(false);
    if (sent) toast(t("shareDone"), "ok");
  }
  async function copyCard() {
    const text = buildShareCard(o!, L, t, settings?.contact_phone, settings?.contact_username);
    const ok = await copyText(text);
    toast(ok ? t("copied") : t("copy"), ok ? "ok" : "info");
  }

  const badgeColor = STATUS_BADGE[o.status] || "gray";

  return (
    <div>
      <PhotoGallery apartmentId={id} onChange={() => load(true)} />
      <Card>
        <div className="flex items-center justify-between gap-2 mb-1">
          <span className="text-[16px] font-extrabold flex items-center gap-1.5">
            №{o.display_id}
            {o.deal_type === "rent" && <Badge color="blue">{t("dealRent")}</Badge>}
          </span>
          <Badge color={badgeColor}>{L.statusLabel(o.status, o.deal_type)}</Badge>
        </div>
        {rows
          .filter(([k, v]) => k != null && v != null && v !== "")
          .map(([k, v], i) => (
            <Row key={i} label={String(k)} value={String(v)} />
          ))}
      </Card>

      {o.source_link && (
        <Button variant="ghost" className="mt-2.5" onClick={() => openLink(o.source_link!)}>
          <ExternalLink size={16} /> {t("openSource")}
        </Button>
      )}

      {o.comment && (
        <div className="mt-2.5 rounded-[14px] px-3.5 py-3 text-sm leading-relaxed border border-dashed border-amber-500/60 bg-amber-500/10 text-amber-700 dark:text-amber-300 whitespace-pre-wrap">
          <div className="font-bold text-[12px] mb-1 opacity-90 flex items-center gap-1"><Lock size={12} /> {t("f_comment")}</div>
          {o.comment}
        </div>
      )}

      {o.deleted_at ? (
        /* Объект в архиве: только просмотр данных и действия восстановления. */
        <div className="mt-4">
          <div className="text-[11px] font-bold uppercase tracking-wider text-muted mx-0.5 mb-1.5">
            {t("secManage")}
          </div>
          {isOwner ? (
            <div className="flex gap-2">
              <Button size="sm" className="flex-1" variant="soft" disabled={busy} onClick={restore}>
                <RotateCcw size={15} /> {t("restore")}
              </Button>
              <Button size="sm" className="flex-1" variant="danger" disabled={busy} onClick={purge}>
                <Trash2 size={15} /> {t("deleteForever")}
              </Button>
            </div>
          ) : (
            <Hint>{t("archiveHint")}</Hint>
          )}
        </div>
      ) : (
      <div className="mt-4 space-y-3.5">
        {/* Статус объекта */}
        {statusTransitions(o.status, o.deal_type).length > 0 && (
          <div>
            <div className="text-[11px] font-bold uppercase tracking-wider text-muted mx-0.5 mb-1.5">
              {t("secStatus")}
            </div>
            <div className="flex gap-2">
              {statusTransitions(o.status, o.deal_type).map((tr) => (
                <Button
                  key={tr.to}
                  size="sm"
                  className="flex-1"
                  variant={tr.to === "sold" || tr.to === "rented" ? "soft" : "ghost"}
                  disabled={busy}
                  onClick={() => setStatus(tr.to)}
                >
                  {t(tr.key)}
                </Button>
              ))}
            </div>
          </div>
        )}

        {/* Поделиться */}
        <div>
          <div className="text-[11px] font-bold uppercase tracking-wider text-muted mx-0.5 mb-1.5">
            {t("secShare")}
          </div>
          {!shareOpen ? (
            <Button
              full
              variant="primary"
              disabled={busy}
              onClick={() => {
                haptic();
                setShareOpen(true);
              }}
            >
              <Send size={16} /> {t("shareBtn")}
            </Button>
          ) : (
            <div className="space-y-2">
              <Button full variant="primary" disabled={busy} onClick={shareDirect}>
                <Send size={16} /> {t("shareToClient")}
              </Button>
              <div className="flex gap-2">
                <Button size="sm" className="flex-1" variant="ghost" disabled={busy} onClick={share}>
                  <ImageIcon size={15} /> {t("shareAllPhotos")}
                </Button>
                <Button size="sm" className="flex-1" variant="ghost" onClick={copyCard}>
                  <Copy size={15} /> {t("shareCard")}
                </Button>
              </div>
            </div>
          )}
          <Hint>{t("shareDirectHint")}</Hint>
        </div>

        {/* Управление */}
        <div>
          <div className="text-[11px] font-bold uppercase tracking-wider text-muted mx-0.5 mb-1.5">
            {t("secManage")}
          </div>
          <div className="flex gap-2">
            <Button
              size="sm"
              className="flex-1"
              variant="ghost"
              onClick={() => nav.push({ name: "objectEdit", obj: o })}
            >
              <Pencil size={15} /> {t("edit")}
            </Button>
            {isOwner && (
              <Button size="sm" className="flex-1" variant="danger" onClick={del}>
                <Trash2 size={15} /> {t("del")}
              </Button>
            )}
          </div>
        </div>
      </div>
      )}

      {events.length > 0 && (
        <div className="mt-4">
          <div className="text-[13px] font-extrabold uppercase tracking-wider text-muted mx-0.5 mb-2">{t("history")}</div>
          {events.map((e, i) => (
            <Card key={i} className="mt-2 py-3">
              <div className="text-[13px] text-muted">
                <b className="text-text">{e.user_name || t("notSet")}</b> · {eventText(e, t, L)}
              </div>
              <div className="text-[12px] text-muted">{fmtDate(e.created_at, lang, settings?.timezone)}</div>
            </Card>
          ))}
        </div>
      )}
    </div>
  );
}

function eventText(e: ApartmentEvent, t: (k: string) => string, L: ReturnType<typeof useApp>["L"]): string {
  if (e.action === "created") return t("ev_created");
  if (e.action === "status") return t("ev_status") + ": " + L.statusLabel(e.note || "");
  if (e.action === "updated") {
    const fields = (e.note || "")
      .split(",")
      .filter(Boolean)
      .map((k) => t(EV_FIELD_KEYS[k] || k));
    return t("ev_updated") + (fields.length ? ": " + fields.join(", ") : "");
  }
  return e.action;
}
