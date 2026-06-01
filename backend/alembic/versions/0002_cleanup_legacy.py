"""cleanup: one-time data normalization + drop dead/legacy columns

Этой миграцией мы:
  1) выполняем РОВНО ОДИН РАЗ те процедуры, что раньше гонялись при каждом
     старте: нормализация старых номеров объектов и назначение «главного»
     админа в старых агентствах;
  2) удаляем мёртвое поле apartments.agent_id (всегда было пустым; реальный
     автор объекта — created_by) и старые легаси-колонки
     apartments.phone / furniture / appliances (данные из них давно перенесены
     в owner_phone / furniture_appliances).

Откат (downgrade) возвращает удалённые колонки (пустыми) — данные нормализации
не откатываются (это одноразовое приведение к порядку).

Revision ID: 0002_cleanup_legacy
Revises: 0001_baseline
"""
import re
from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "0002_cleanup_legacy"
down_revision: Union[str, Sequence[str], None] = "0001_baseline"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _normalize_display_ids(bind) -> None:
    """
    Привести старые номера объектов к виду «0001»: из display_id берём только
    цифры и дополняем до 4 знаков; при конфликте в пределах агентства сдвигаем
    на следующий свободный. Уже числовые номера не трогаем (идемпотентно).
    """
    rows = bind.execute(
        sa.text("SELECT id, agency_id, display_id FROM apartments")
    ).fetchall()

    by_agency: dict[int, list] = {}
    for row in rows:
        by_agency.setdefault(row.agency_id, []).append(row)

    updates: list[tuple[int, str]] = []
    for _agency_id, items in by_agency.items():
        used: set[str] = set()
        # Сначала фиксируем уже корректные числовые номера.
        for a in items:
            if a.display_id and re.fullmatch(r"\d+", a.display_id):
                used.add(a.display_id.zfill(4))
        # Затем чиним нечисловые (например «OTH-0001»).
        for a in items:
            if a.display_id and re.fullmatch(r"\d+", a.display_id):
                continue
            digits = "".join(ch for ch in (a.display_id or "") if ch.isdigit())
            num = int(digits) if digits else 1
            candidate = f"{num:04d}"
            while candidate in used:
                num += 1
                candidate = f"{num:04d}"
            used.add(candidate)
            updates.append((a.id, candidate))

    for apt_id, new_display in updates:
        bind.execute(
            sa.text("UPDATE apartments SET display_id = :d WHERE id = :i"),
            {"d": new_display, "i": apt_id},
        )


def _backfill_agency_owners(bind) -> None:
    """
    Для каждого агентства, где ни у одного админа не выставлен is_owner,
    назначить главным самого раннего по дате создания администратора.
    """
    bind.execute(sa.text("""
        UPDATE users u
        SET is_owner = true
        WHERE u.role = 'agency_admin'
          AND u.id = (
              SELECT u2.id FROM users u2
              WHERE u2.agency_id = u.agency_id AND u2.role = 'agency_admin'
              ORDER BY u2.created_at, u2.id
              LIMIT 1
          )
          AND NOT EXISTS (
              SELECT 1 FROM users u3
              WHERE u3.agency_id = u.agency_id
                AND u3.role = 'agency_admin'
                AND u3.is_owner = true
          )
    """))


def upgrade() -> None:
    bind = op.get_bind()

    # 1) Одноразовые приведения данных к порядку.
    _normalize_display_ids(bind)
    _backfill_agency_owners(bind)

    # 2) Удаляем мёртвое поле agent_id (внешний ключ снимется автоматически).
    op.drop_column("apartments", "agent_id")

    # 3) Удаляем старые легаси-колонки, если они ещё остались (на новых базах
    #    их нет — поэтому IF EXISTS, чтобы миграция не падала).
    for col in ("phone", "furniture", "appliances"):
        op.execute(f"ALTER TABLE apartments DROP COLUMN IF EXISTS {col}")


def downgrade() -> None:
    # Возвращаем удалённые колонки (пустыми). Нормализацию данных не откатываем.
    op.add_column("apartments", sa.Column("appliances", sa.Text(), nullable=True))
    op.add_column("apartments", sa.Column("furniture", sa.Text(), nullable=True))
    op.add_column("apartments", sa.Column("phone", sa.Text(), nullable=True))
    op.add_column("apartments", sa.Column("agent_id", sa.BigInteger(), nullable=True))
    op.create_foreign_key(
        "apartments_agent_id_fkey", "apartments", "agents", ["agent_id"], ["id"]
    )
