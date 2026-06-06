import React, { useEffect, useMemo, useRef, useState } from "react";
import {
  ArrowLeft,
  Archive as ArchiveIcon,
  Camera,
  ChevronLeft,
  ChevronRight,
  Copy,
  ExternalLink,
  Home as HomeIcon,
  Image as ImageIcon,
  Pencil,
  RotateCcw,
  Search as SearchIcon,
  Send,
  Trash2,
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
  Textarea,
} from "../components/ui";
import {
  CURRENCIES,
  FA_VALUES,
  OBJ_COND_VALUES,
  OBJ_TYPE_VALUES,
  STATUS_BADGE,
} from "../i18n";
import { Badge } from "../components/ui";
import type { Apartment, ApartmentEvent, ApartmentList, ApartmentPhoto, DictItem, SearchParams } from "../types";
import { copyText, downscaleToDataUrl, fmtDate, fmtPrice } from "../utils";
import { canShareMessage, haptic, openLink, shareMessage } from "../telegram";

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
    name: o.name ?? "",
    type: o.type ?? "",
    district: o.district ?? "",
    address: o.address ?? "",
    rooms: o.rooms != null ? String(o.rooms) : "",
    floor: o.floor != null ? String(o.floor) : "",
    total_floors: o.total_floors != null ? String(o.total_floors) : "",
    area: o.area != null ? String(o.area) : "",
    price: o.price != null ? String(o.price) : "",
    currency: o.currency || "USD",
    condition: o.condition ?? "",
    furniture_appliances: o.furniture_appliances ?? "",
    owner_phone: o.owner_phone ?? "",
    source_link: o.source_link ?? "",
    description: o.description ?? "",
    comment: o.comment ?? "",
  });
  const set = (k: keyof typeof f, v: string) => setF((p) => ({ ...p, [k]: v }));

  function submit() {
    const fields: Record<string, unknown> = {
      name: f.name.trim() || null,
      type: f.type || null,
      district: f.district || null,
      address: f.address.trim() || null,
      rooms: intOrNull(f.rooms),
      floor: intOrNull(f.floor),
      total_floors: intOrNull(f.total_floors),
      area: numOrNull(f.area),
      price: numOrNull(f.price),
      currency: f.currency,
      condition: f.condition || null,
      furniture_appliances: f.furniture_appliances || null,
      owner_phone: f.owner_phone.trim() || null,
      source_link: f.source_link.trim() || null,
      description: f.description.trim() || null,
      comment: f.comment.trim() || null,
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
        <div className="flex-1">
          <Field label={t("f_rooms")}>
            <Input inputMode="numeric" value={f.rooms} onChange={(e) => set("rooms", e.target.value)} />
          </Field>
        </div>
        <div className="flex-1">
          <Field label={t("f_floor")}>
            <Input inputMode="numeric" value={f.floor} onChange={(e) => set("floor", e.target.value)} />
          </Field>
        </div>
        <div className="flex-1">
          <Field label={t("f_tfloors")}>
            <Input inputMode="numeric" value={f.total_floors} onChange={(e) => set("total_floors", e.target.value)} />
          </Field>
        </div>
      </div>
      <div className="flex gap-2">
        <div className="flex-1">
          <Field label={t("f_area")}>
            <Input inputMode="decimal" value={f.area} onChange={(e) => set("area", e.target.value)} />
          </Field>
        </div>
        <div className="flex-1">
          <Field label={t("f_price")}>
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
      <Field label={t("f_source")}>
        <Input inputMode="url" placeholder="https://…" value={f.source_link} onChange={(e) => set("source_link", e.target.value)} />
      </Field>
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
  lines.push("🏠 " + t("apartment") + " №" + (o.display_id || ""));
  if (o.name) lines.push("📋 " + o.name);
  if (o.type) lines.push("🏗 " + t("f_type") + ": " + L.typeLabel(o.type));
  if (o.district) lines.push("📍 " + t("f_district") + ": " + o.district);
  if (o.address) lines.push("🗺 " + t("f_address") + ": " + o.address);
  if (o.rooms != null) lines.push("🚪 " + t("f_rooms") + ": " + o.rooms);
  const fl = o.floor != null && o.total_floors != null ? `${o.floor}/${o.total_floors}` : o.floor != null ? String(o.floor) : null;
  if (fl) lines.push("🏢 " + t("f_floor") + ": " + fl);
  if (o.area != null) lines.push("📐 " + o.area + " m²");
  if (o.condition) lines.push("🔧 " + L.condLabel(o.condition));
  const fa = L.faLabel(o.furniture_appliances);
  if (fa) lines.push("🛋 " + fa);
  if (o.price != null) lines.push("💵 " + o.price + " " + (o.currency || ""));
  if (o.source_link) lines.push("🔗 " + o.source_link);
  if (o.description) lines.push("📝 " + o.description);
  if (contactPhone) lines.push("📞 " + contactPhone);
  if (contactUsername) lines.push("✈️ " + contactUsername);
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
    // По одному фото за запрос (JSON), чтобы каждый запрос был лёгким.
    for (const f of Array.from(files)) {
      const dataUrl = await downscaleToDataUrl(f);
      const r = await uploadOnePhoto(apartmentId, dataUrl);
      if (r.ok && r.data) lastOk = r.data;
      else {
        failed = { data: r.data, status: r.status };
        break;
      }
    }
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
    if (!window.confirm(t("delPhotoQ"))) return;
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
            <div key={p.id} className="relative aspect-square rounded-[14px] overflow-hidden bg-[var(--soft)] border border-line">
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
      <Hint>{t("photosHint")}</Hint>
      {viewer != null && photos && photos.length > 0 && (
        <Lightbox urls={photos.map((p) => p.url)} index={viewer} onClose={() => setViewer(null)} onIndex={setViewer} />
      )}
    </div>
  );
}

// ── Карточка в списке ───────────────────────────────────────────────
export function ApartmentCard({ o }: { o: Apartment }) {
  const { t, L } = useApp();
  const nav = useNav();
  const parts = [L.typeLabel(o.type), o.district, o.rooms != null ? `${o.rooms} ${t("f_rooms").toLowerCase()}` : null]
    .filter(Boolean)
    .join(" · ");
  const accent: Record<string, string> = {
    active: "border-l-emerald-500",
    deposit: "border-l-amber-500",
    sold: "border-l-slate-400",
    archived: "border-l-slate-400",
  };
  return (
    <button
      onClick={() => {
        haptic();
        nav.push({ name: "objectDetail", id: o.id });
      }}
      className={cx2(
        "w-full text-left mt-2.5 rounded-xl2 bg-card border border-line shadow-soft p-3.5 transition active:scale-[.99] hover:shadow-lg2 border-l-[3px]",
        accent[o.status] || "border-l-slate-400"
      )}
    >
      <div className="flex items-center gap-3">
        <div className="w-11 h-11 shrink-0 rounded-[13px] bg-primary-soft text-primary flex items-center justify-center overflow-hidden">
          {o.photo_url ? (
            <img src={o.photo_url} alt="" className="w-full h-full object-cover" />
          ) : (
            <HomeIcon size={22} />
          )}
        </div>
        <div className="min-w-0 flex-1">
          <div className="flex items-center justify-between gap-2">
            <span className="font-extrabold">№{o.display_id}</span>
            <Badge color={STATUS_BADGE[o.status] || "gray"}>{L.statusLabel(o.status)}</Badge>
          </div>
          {o.name && <div className="text-[13px] text-muted truncate">{o.name}</div>}
          <div className="text-[13px] text-muted">{parts || t("notSet")}</div>
          <div className="text-[13px] text-muted">
            {t("f_price")}: <span className="font-extrabold text-primary">{fmtPrice(o.price, o.currency) || t("notSet")}</span>
          </div>
          {o.created_by_name && (
            <div className="text-[13px] text-muted">
              {t("addedBy")}: {o.created_by_name}
            </div>
          )}
        </div>
      </div>
    </button>
  );
}

function cx2(...a: Array<string | false | null | undefined>) {
  return a.filter(Boolean).join(" ");
}

// ── Список/поиск с пагинацией ───────────────────────────────────────
export function ObjectList({ params }: { params: SearchParams }) {
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

  if (loading && !items.length) return <Spinner />;
  if (err) return <Empty>{err}</Empty>;
  if (!items.length) return <Empty>{t("notFound")}</Empty>;
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
    </div>
  );
}

// ── Выбор фото при создании объекта (до того, как объект сохранён) ──
function PendingPhotos({
  files,
  setFiles,
  tgUrls,
  setTgUrls,
}: {
  files: File[];
  setFiles: (f: File[]) => void;
  tgUrls: string[];
  setTgUrls: (u: string[]) => void;
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
      {(previews.length > 0 || tgUrls.length > 0) && (
        <div className="grid grid-cols-3 gap-2 mb-2.5">
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

// ── Экран: добавить объект ──────────────────────────────────────────
export function AddObjectScreen() {
  const { t, toast } = useApp();
  const nav = useNav();
  const [saving, setSaving] = useState(false);
  const [files, setFiles] = useState<File[]>([]);
  const [tgUrls, setTgUrls] = useState<string[]>([]);

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
        if (!window.confirm(t("dupFound") + " " + ids + "\n\n" + t("dupAsk"))) {
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
    setSaving(false);
    toast(t("objCreated") + r.data.display_id, "ok");
    if (photoFail > 0) toast(t("photoPartialFail"), "warn");
    // Открываем карточку нового объекта (там видно фото и можно дозагрузить).
    nav.pop();
    nav.push({ name: "objectDetail", id: newId });
  }

  return (
    <ObjectForm onSubmit={submit} submitLabel={t("saveObject")} saving={saving}>
      <PendingPhotos files={files} setFiles={setFiles} tgUrls={tgUrls} setTgUrls={setTgUrls} />
    </ObjectForm>
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
  const [types, setTypes] = useState<string[]>([]);
  const [dist, setDist] = useState<string[]>([]);
  const [q, setQ] = useState("");
  const [rmin, setRmin] = useState("");
  const [rmax, setRmax] = useState("");
  const [fmin, setFmin] = useState("");
  const [fmax, setFmax] = useState("");
  const [pmin, setPmin] = useState("");
  const [pmax, setPmax] = useState("");
  const [cur, setCur] = useState("");

  const toggle = (arr: string[], set: (v: string[]) => void, v: string) =>
    set(arr.includes(v) ? arr.filter((x) => x !== v) : [...arr, v]);

  function run() {
    const params: SearchParams = { status };
    if (types.length) params.types = types;
    if (dist.length) params.districts = dist;
    if (q.trim()) params.q = q.trim();
    if (rmin) params.rooms_min = rmin;
    if (rmax) params.rooms_max = rmax;
    if (fmin) params.floor_min = fmin;
    if (fmax) params.floor_max = fmax;
    if (pmin) params.price_min = pmin;
    if (pmax) params.price_max = pmax;
    if (cur) params.currency = cur;
    nav.push({ name: "objectList", params, titleKey: "findObject" });
  }

  const statusOpts: { value: string; label: string }[] = [
    { value: "all", label: t("notSet") },
    { value: "active", label: t("statusActive") },
    { value: "deposit", label: t("statusDeposit") },
    { value: "sold", label: t("statusSold") },
  ];

  return (
    <Card>
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
      <div className="flex gap-2">
        <div className="flex-1">
          <Field label={t("floorFrom")}>
            <Input inputMode="numeric" value={fmin} onChange={(e) => setFmin(e.target.value)} />
          </Field>
        </div>
        <div className="flex-1">
          <Field label={t("to")}>
            <Input inputMode="numeric" value={fmax} onChange={(e) => setFmax(e.target.value)} />
          </Field>
        </div>
      </div>
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
  const [view, setView] = useState<"unsold" | "sold">("unsold");
  return (
    <div>
      <Segmented
        value={view}
        onChange={(v) => setView(v)}
        options={[
          { value: "unsold", label: t("notSold") },
          { value: "sold", label: t("statusSold") },
        ]}
      />
      <div className="flex justify-end mt-2">
        <Button size="sm" variant="ghost" onClick={() => nav.push({ name: "archive" })}>
          <ArchiveIcon size={15} /> {t("archive")}
        </Button>
      </div>
      <ObjectList params={{ status: view }} />
    </div>
  );
}

// ── Экран: архив (удалённые объекты) ────────────────────────────────
// Видят все сотрудники. Восстанавливать и удалять навсегда может только
// владелец агентства (главный администратор).
function ArchiveCard({ o, canManage, onChanged }: { o: Apartment; canManage: boolean; onChanged: () => void }) {
  const { t, L, toast } = useApp();
  const [busy, setBusy] = useState(false);
  const parts = [L.typeLabel(o.type), o.district, o.rooms != null ? `${o.rooms} ${t("f_rooms").toLowerCase()}` : null]
    .filter(Boolean)
    .join(" · ");

  async function restore() {
    setBusy(true);
    const r = await api<Apartment>("/api/v1/apartments/" + o.id + "/restore", { method: "POST" });
    setBusy(false);
    if (r.ok) {
      toast(t("restored"), "ok");
      onChanged();
    } else toast(errText(r.data, r.status), "err");
  }
  async function purge() {
    if (!window.confirm(t("deleteForeverQ"))) return;
    setBusy(true);
    const r = await api("/api/v1/apartments/" + o.id + "/permanent", { method: "DELETE" });
    setBusy(false);
    if (r.ok) {
      toast(t("deletedForever"), "ok");
      onChanged();
    } else toast(errText(r.data, r.status), "err");
  }

  return (
    <div className="mt-2.5 rounded-xl2 bg-card border border-line shadow-soft p-3.5 border-l-[3px] border-l-slate-400">
      <div className="flex items-center justify-between gap-2">
        <span className="font-extrabold">№{o.display_id}</span>
        <Badge color="gray">{L.statusLabel(o.status)}</Badge>
      </div>
      {o.name && <div className="text-[13px] text-muted truncate">{o.name}</div>}
      <div className="text-[13px] text-muted">{parts || t("notSet")}</div>
      <div className="text-[13px] text-muted">
        {t("f_price")}: <span className="font-extrabold text-primary">{fmtPrice(o.price, o.currency) || t("notSet")}</span>
      </div>
      {canManage && (
        <div className="flex gap-2 mt-2.5">
          <Button size="sm" className="flex-1" variant="soft" disabled={busy} onClick={restore}>
            <RotateCcw size={15} /> {t("restore")}
          </Button>
          <Button size="sm" className="flex-1" variant="danger" disabled={busy} onClick={purge}>
            <Trash2 size={15} /> {t("deleteForever")}
          </Button>
        </div>
      )}
    </div>
  );
}

export function ArchiveScreen() {
  const { t, user } = useApp();
  const canManage = user?.role === "agency_admin" && !!user?.is_owner;
  const [items, setItems] = useState<Apartment[]>([]);
  const [total, setTotal] = useState(0);
  const [offset, setOffset] = useState(0);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState<string | null>(null);

  async function load(reset: boolean) {
    setLoading(true);
    const off = reset ? 0 : offset;
    const r = await api<ApartmentList>("/api/v1/apartments/archived?" + buildQuery({ limit: 20, offset: off }));
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
  }, []);

  if (loading && !items.length) return <Spinner />;
  if (err) return <Empty>{err}</Empty>;
  if (!items.length) return <Empty>{t("archiveEmpty")}</Empty>;
  const left = total - items.length;
  return (
    <div>
      <Hint>{t("archiveHint")}</Hint>
      <div className="text-[13px] text-muted my-1.5">
        {t("found")}: {total}
      </div>
      {items.map((o) => (
        <ArchiveCard key={o.id} o={o} canManage={canManage} onChanged={() => load(true)} />
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
const STATUS_TRANSITIONS: Record<string, { to: string; key: string }[]> = {
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

const EV_FIELD_KEYS: Record<string, string> = {
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

  const floorTxt =
    o.floor != null && o.total_floors != null ? `${o.floor} / ${o.total_floors}` : o.floor != null ? String(o.floor) : null;
  const rows: [string | null, React.ReactNode][] = [
    [t("f_name"), o.name],
    [t("f_type"), o.type ? L.typeLabel(o.type) : null],
    [t("f_district"), o.district],
    [t("f_address"), o.address],
    [t("f_rooms"), o.rooms],
    [t("f_floor"), floorTxt],
    [t("f_area"), o.area],
    [t("f_price"), fmtPrice(o.price, o.currency)],
    [t("f_condition"), o.condition ? L.condLabel(o.condition) : null],
    [t("f_furniture"), L.faLabel(o.furniture_appliances)],
    [t("f_owner_phone"), o.owner_phone],
    [t("f_desc"), o.description],
    [t("addedBy"), o.created_by_name],
    o.status === "sold" && o.archived_at ? [t("soldDate"), fmtDate(o.archived_at, lang, settings?.timezone)] : [null, null],
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
    if (!window.confirm(t("delObjQ"))) return;
    const r = await api("/api/v1/apartments/" + id, { method: "DELETE" });
    if (r.ok) {
      toast(t("objDeleted"), "ok");
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
          <span className="text-[16px] font-extrabold">№{o.display_id}</span>
          <Badge color={badgeColor}>{L.statusLabel(o.status)}</Badge>
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
          <div className="font-bold text-[12px] mb-1 opacity-90">🔒 {t("f_comment")}</div>
          {o.comment}
        </div>
      )}

      <div className="mt-4 space-y-3.5">
        {/* Статус объекта */}
        {(STATUS_TRANSITIONS[o.status] || []).length > 0 && (
          <div>
            <div className="text-[11px] font-bold uppercase tracking-wider text-muted mx-0.5 mb-1.5">
              {t("secStatus")}
            </div>
            <div className="flex gap-2">
              {(STATUS_TRANSITIONS[o.status] || []).map((tr) => (
                <Button
                  key={tr.to}
                  size="sm"
                  className="flex-1"
                  variant={tr.to === "sold" ? "soft" : "ghost"}
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
          <Button full variant="primary" disabled={busy} onClick={shareDirect}>
            <Send size={16} /> {t("shareToClient")}
          </Button>
          <div className="flex gap-2 mt-2">
            <Button size="sm" className="flex-1" variant="ghost" disabled={busy} onClick={share}>
              <ImageIcon size={15} /> {t("shareAllPhotos")}
            </Button>
            <Button size="sm" className="flex-1" variant="ghost" onClick={copyCard}>
              <Copy size={15} /> {t("shareCard")}
            </Button>
          </div>
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
