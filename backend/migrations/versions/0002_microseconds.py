"""Preserve job scheduling and event ordering precision on MySQL."""
from alembic import op
from sqlalchemy import DateTime
from sqlalchemy.dialects.mysql import DATETIME
from app.models import Base

revision = '0002_microseconds'
down_revision = '0001_pilot'
branch_labels = None
depends_on = None

def upgrade():
    if op.get_bind().dialect.name == 'mysql':
        for table in Base.metadata.sorted_tables:
            for column in table.columns:
                if isinstance(column.type, DateTime):
                    op.alter_column(table.name, column.name, existing_type=DATETIME(), type_=DATETIME(fsp=6), existing_nullable=column.nullable)

def downgrade():
    if op.get_bind().dialect.name == 'mysql':
        for table in Base.metadata.sorted_tables:
            for column in table.columns:
                if isinstance(column.type, DateTime):
                    op.alter_column(table.name, column.name, existing_type=DATETIME(fsp=6), type_=DATETIME(), existing_nullable=column.nullable)
