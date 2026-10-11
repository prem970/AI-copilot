"""Refresh provider consent and index state when switching embeddings to Google."""
from alembic import op
import sqlalchemy as sa

revision = '0004_gemini_embeddings'
down_revision = '0003_hosted_ai_consent'
branch_labels = None
depends_on = None

def upgrade():
    op.execute(sa.text('UPDATE patients SET external_ai_consent = false, consent_at = NULL'))
    op.execute(sa.text("UPDATE documents SET index_status = 'consent_required' WHERE approved_revision IS NOT NULL AND deleted_at IS NULL"))
    op.execute(sa.text('UPDATE source_chunks SET indexed = false'))
    op.execute(sa.text("UPDATE jobs SET status = 'cancelled' WHERE kind IN ('index', 'summary') AND status IN ('queued', 'running')"))

def downgrade():
    # Reverting the provider never restores permission to send private content.
    pass
