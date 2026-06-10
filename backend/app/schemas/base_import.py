"""
Схемы импорта готовой базы клиента (.xlsx/.csv) — Этап 1.
"""
from typing import Dict, List, Optional

from pydantic import BaseModel


class TargetField(BaseModel):
    code: str
    label: str


class BaseImportAnalyzeOut(BaseModel):
    # Заголовки колонок из файла клиента.
    columns: List[str]
    # Первые строки-образцы (для превью).
    sample_rows: List[List[str]]
    # Сколько всего строк данных в файле.
    total_rows: int
    # Предложенный маппинг: код нашего поля -> индекс колонки клиента (или null).
    suggested_mapping: Dict[str, Optional[int]]
    # Наши поля-цели (код + человекочитаемая подпись) для отрисовки формы.
    target_fields: List[TargetField]


class BaseImportCommitOut(BaseModel):
    created: int
    skipped: int
    failed: int
    total: int
