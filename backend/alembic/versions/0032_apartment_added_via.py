"""apartments.added_via — как объект попал в базу (для наблюдения владельца)

Additive: nullable-колонка + бэкофилл существующих объектов по полю source:
  - source пуст            → 'manual' (добавлен вручную);
  - source начинается с @  → 'auto'   (из Telegram-канала; массовый vs авто для
                                        старых объектов не различить — помечаем auto);
  - иначе (домен площадки) → 'link'   (импорт по ссылке, по одному).
Новые объекты помечаются точно на месте создания: manual / link / bulk / auto.

Revision ID: 0032_apartment_added_via
Revises: 0031_user_last_seen
"""
from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "0032_apartment_added_via"
down_revision: Union[str, Sequence[str], None] = "0031_user_last_seen"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("apartments", sa.Column("added_via", sa.String(), nullable=True))
    op.execute(
        """
        UPDATE apartments SET added_via = CASE
            WHEN source IS NULL OR source = '' THEN 'manual'
            WHEN source LIKE '@%' THEN 'auto'
            ELSE 'link'
        END
        WHERE added_via IS NULL
        """
    )


def downgrade() -> None:
    op.drop_column("apartments", "added_via")
