// Шина «данные изменились» для умного обновления при возврате на страницу.
//
// Идея: страницы теперь живые (keep-alive) и НЕ перезагружаются при возврате —
// состояние и скролл сохраняются. Но если пока мы были на другой странице данные
// поменялись (создали/изменили/удалили объект, клиента и т.п.), список под нами
// должен тихо подтянуть свежее. Любой успешный НЕ-GET запрос (см. api.ts) бампает
// версию; экраны через useRevisit перезагружаются при возврате, ЕСЛИ версия
// изменилась с момента их последней загрузки. Скролл при этом не трогаем.
import { useEffect, useRef } from "react";
import { usePaneActive } from "./nav";

let _version = 0;

/** Пометить, что данные на бэкенде изменились (после POST/PATCH/PUT/DELETE). */
export function bumpData(): void {
  _version += 1;
}

/** Текущая версия данных. */
export function dataVersion(): number {
  return _version;
}

/**
 * Вызвать `reload` при ВОЗВРАТЕ на страницу (снова стала видимой), но только если
 * с момента прошлой загрузки данные менялись. Экран передаёт свою функцию загрузки.
 */
export function useRevisit(reload: () => void): void {
  const active = usePaneActive();
  const reloadRef = useRef(reload);
  reloadRef.current = reload;
  const prevActive = useRef(active);
  const seen = useRef(dataVersion());

  useEffect(() => {
    const wasActive = prevActive.current;
    prevActive.current = active;
    if (active && !wasActive) {
      // Вернулись на страницу: обновляем, только если данные поменялись.
      if (dataVersion() !== seen.current) {
        seen.current = dataVersion();
        reloadRef.current();
      }
    } else if (active) {
      // Первая активная отрисовка — синхронизируем «виденную» версию.
      seen.current = dataVersion();
    }
  }, [active]);
}
