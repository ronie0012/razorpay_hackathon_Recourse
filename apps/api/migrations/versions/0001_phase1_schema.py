"""Phase 1 deterministic vertical slice schema.

Revision ID: 0001_phase1
"""
from alembic import op

from recourse.persistence.database import Base
from recourse.persistence import tables  # noqa: F401

revision = "0001_phase1"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    Base.metadata.create_all(bind=op.get_bind())


def downgrade():
    Base.metadata.drop_all(bind=op.get_bind())

