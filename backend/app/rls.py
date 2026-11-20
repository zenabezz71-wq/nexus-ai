"""Per-request tenant context for PostgreSQL row level security.

Defense in depth: application queries are already org-scoped; on PostgreSQL the
database additionally refuses rows outside the request's organization. The GUCs
are transaction-local (set_config(..., true)), so pooled connections never leak
context between requests. On SQLite (tests) every helper is a no-op.

System context exists only for signed provider webhooks and token-bearing
public endpoints (unsubscribe) that must act on rows before any user session
exists. It is set explicitly in those handlers, never by clients.
"""
from sqlalchemy import event, text
from .database import SessionLocal

ORG_SETTING = "app.organization_id"
SYSTEM_SETTING = "app.system_context"


def _is_postgres(db):
    try:
        return db.get_bind().dialect.name == "postgresql"
    except Exception:
        return False


def _apply(db):
    if not _is_postgres(db):
        return
    org = db.info.get("organization_id")
    if org is not None:
        db.execute(text("SELECT set_config(:name, :value, true)"), {"name": ORG_SETTING, "value": str(org)})
    if db.info.get("system_context"):
        db.execute(text("SELECT set_config(:name, 'on', true)"), {"name": SYSTEM_SETTING})


@event.listens_for(SessionLocal, "after_begin")
def _tenant_context_after_begin(session, transaction, connection):
    """Re-apply the tenant context on every new transaction of this session.

    set_config(..., true) lasts only to the end of the current transaction, so
    after each commit the next transaction starts clean and must be re-stamped
    from session.info.
    """
    if connection.dialect.name != "postgresql":
        return
    org = session.info.get("organization_id")
    if org is not None:
        connection.exec_driver_sql("SELECT set_config('app.organization_id', %s, true)", (str(org),))
    if session.info.get("system_context"):
        connection.exec_driver_sql("SELECT set_config('app.system_context', 'on', true)")


def org_context(db, organization_id):
    """Bind this session to one organization for the rest of the request."""
    db.info["organization_id"] = organization_id
    _apply(db)


def system_context(db):
    """Mark this session as a verified server-side system actor (webhooks)."""
    db.info["system_context"] = True
    _apply(db)
