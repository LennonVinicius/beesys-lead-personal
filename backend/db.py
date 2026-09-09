import json
import os
import sqlite3
import threading
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

DATABASE_URL = (os.getenv("DATABASE_URL") or "").strip()
USE_POSTGRES = DATABASE_URL.startswith("postgres://") or DATABASE_URL.startswith("postgresql://")
DB_PATH = Path(__file__).with_name("leads.db")

PIPELINE_STATUSES = [
    "NEW", "PRIORITY", "ROUTE_PLANNED", "VISITED", "INTERESTED",
    "DEMO", "PROPOSAL", "CLIENT", "LOST", "DO_NOT_CONTACT",
]
FOLLOWUP_STATUSES = ["PENDING", "DONE", "CANCELED"]

# Increment this whenever init_db() gains a new schema migration.
SCHEMA_VERSION = 3
# Session-level advisory lock shared by every Render process connected to the
# same PostgreSQL database. It prevents concurrent DDL migrations.
MIGRATION_LOCK_ID = 846_537_221_905

_PG_POOL = None
_INIT_LOCK = threading.Lock()
_DB_INITIALIZED = False


def _postgres_dsn():
    db_url = DATABASE_URL
    if "supabase." in db_url and "sslmode=" not in db_url:
        db_url += ("&" if "?" in db_url else "?") + "sslmode=require"
    return db_url


def _conn():
    global _PG_POOL
    if USE_POSTGRES:
        # Reaproveita conexões com o Supabase. Abrir uma nova conexão SSL em
        # cada widget/rerun do Streamlit adicionava bastante latência.
        if _PG_POOL is None:
            from psycopg.rows import dict_row
            from psycopg_pool import ConnectionPool
            _PG_POOL = ConnectionPool(
                conninfo=_postgres_dsn(),
                min_size=0,
                max_size=int(os.getenv("DB_POOL_MAX", "5")),
                timeout=10,
                max_idle=180,
                kwargs={"row_factory": dict_row, "autocommit": False},
                open=True,
            )
        return _PG_POOL.connection()
    conn = sqlite3.connect(DB_PATH, timeout=20)
    conn.row_factory = sqlite3.Row
    return conn


def _sql(query: str) -> str:
    if USE_POSTGRES:
        return query.replace("?", "%s")
    return query


def _execute(conn, query, params=()):
    return conn.execute(_sql(query), params)


def _columns(conn, table):
    if USE_POSTGRES:
        rows = _execute(
            conn,
            "SELECT column_name AS name FROM information_schema.columns WHERE table_schema='public' AND table_name=?",
            (table,),
        ).fetchall()
        return {r["name"] for r in rows}
    return {r["name"] for r in _execute(conn, f"PRAGMA table_info({table})").fetchall()}


def _table_exists(conn, table: str) -> bool:
    if USE_POSTGRES:
        row = _execute(
            conn,
            "SELECT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema='public' AND table_name=?) AS found",
            (table,),
        ).fetchone()
        return bool(row and row["found"])
    row = _execute(
        conn,
        "SELECT 1 AS found FROM sqlite_master WHERE type='table' AND name=? LIMIT 1",
        (table,),
    ).fetchone()
    return bool(row)


def _ensure_columns(conn, table, specs):
    existing = _columns(conn, table)
    for name, ddl in specs.items():
        if name not in existing:
            _execute(conn, f"ALTER TABLE {table} ADD COLUMN {name} {ddl}")


def _ensure_index(conn, index_name: str, ddl: str):
    """Create an index only when it is actually absent.

    PostgreSQL's CREATE INDEX IF NOT EXISTS can still take relation locks while
    checking an existing index. Avoiding the DDL entirely reduces contention
    during deploys and Streamlit session startup.
    """
    if USE_POSTGRES:
        row = _execute(
            conn,
            "SELECT 1 AS found FROM pg_indexes WHERE schemaname='public' AND indexname=? LIMIT 1",
            (index_name,),
        ).fetchone()
        if row:
            return
    _execute(conn, ddl)


def _schema_version(conn) -> int:
    if not _table_exists(conn, "app_settings"):
        return 0
    try:
        row = _execute(
            conn,
            "SELECT value_json FROM app_settings WHERE setting_key='__schema_version__' LIMIT 1",
        ).fetchone()
        if not row:
            return 0
        value = json.loads(row["value_json"] or "0")
        if isinstance(value, dict):
            value = value.get("version", 0)
        return int(value or 0)
    except Exception:
        return 0


def _set_schema_version(conn, version: int):
    now = datetime.now(timezone.utc).isoformat()
    value = json.dumps(int(version))
    _execute(
        conn,
        """
        INSERT INTO app_settings(setting_key, value_json, updated_at)
        VALUES (?, ?, ?)
        ON CONFLICT(setting_key) DO UPDATE SET
            value_json=excluded.value_json,
            updated_at=excluded.updated_at
        """,
        ("__schema_version__", value, now),
    )


def _enable_rls(conn, tables):
    """Enable RLS on public tables exposed by Supabase/PostgREST.

    The Render app connects directly with DATABASE_URL, so enabling RLS does
    not change its server-side PostgreSQL access. With no PostgREST policies,
    anon/authenticated API clients cannot read these internal CRM tables.
    """
    if not USE_POSTGRES:
        return
    for table in tables:
        if not _table_exists(conn, table):
            continue
        row = _execute(
            conn,
            """
            SELECT c.relrowsecurity AS enabled
            FROM pg_class c
            JOIN pg_namespace n ON n.oid = c.relnamespace
            WHERE n.nspname='public' AND c.relname=? AND c.relkind='r'
            """,
            (table,),
        ).fetchone()
        if row and not bool(row["enabled"]):
            # table names are from the internal constant below, never user input.
            _execute(conn, f'ALTER TABLE public."{table}" ENABLE ROW LEVEL SECURITY')


def _acquire_migration_lock(conn, timeout_seconds: int = 35):
    if not USE_POSTGRES:
        return
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        row = _execute(
            conn,
            "SELECT pg_try_advisory_lock(?) AS locked",
            (MIGRATION_LOCK_ID,),
        ).fetchone()
        if row and bool(row["locked"]):
            return
        time.sleep(0.35)
    raise TimeoutError("O banco está finalizando outra atualização. Tente novamente em alguns segundos.")


def _release_migration_lock(conn):
    if not USE_POSTGRES:
        return
    try:
        _execute(conn, "SELECT pg_advisory_unlock(?)", (MIGRATION_LOCK_ID,))
        conn.commit()
    except Exception:
        try:
            conn.rollback()
        except Exception:
            pass


def _retryable_init_error(exc: Exception) -> bool:
    sqlstate = getattr(exc, "sqlstate", None)
    # 40P01 = deadlock_detected, 55P03 = lock_not_available,
    # 57014 = statement/query canceled (can include statement_timeout).
    if sqlstate in {"40P01", "55P03", "57014"}:
        return True
    msg = str(exc).lower()
    return any(term in msg for term in ("deadlock detected", "lock timeout", "could not obtain lock"))


def _apply_schema(conn):
    activity_id = "BIGSERIAL PRIMARY KEY" if USE_POSTGRES else "INTEGER PRIMARY KEY AUTOINCREMENT"
    followup_id = "BIGSERIAL PRIMARY KEY" if USE_POSTGRES else "INTEGER PRIMARY KEY AUTOINCREMENT"
    goal_id = "BIGSERIAL PRIMARY KEY" if USE_POSTGRES else "INTEGER PRIMARY KEY AUTOINCREMENT"
    job_id = "BIGSERIAL PRIMARY KEY" if USE_POSTGRES else "INTEGER PRIMARY KEY AUTOINCREMENT"
    job_item_id = "BIGSERIAL PRIMARY KEY" if USE_POSTGRES else "INTEGER PRIMARY KEY AUTOINCREMENT"
    ai_usage_id = "BIGSERIAL PRIMARY KEY" if USE_POSTGRES else "INTEGER PRIMARY KEY AUTOINCREMENT"
    snapshot_id = "BIGSERIAL PRIMARY KEY" if USE_POSTGRES else "INTEGER PRIMARY KEY AUTOINCREMENT"

    _execute(
        conn,
        """
        CREATE TABLE IF NOT EXISTS businesses (
            business_key TEXT PRIMARY KEY,
            provider TEXT NOT NULL,
            source_id TEXT,
            name TEXT NOT NULL,
            address TEXT,
            lat REAL NOT NULL,
            lon REAL NOT NULL,
            category TEXT,
            phone TEXT,
            website TEXT,
            rating REAL,
            reviews INTEGER,
            maps_url TEXT,
            site_functional INTEGER,
            site_status INTEGER,
            site_response_ms INTEGER,
            site_https INTEGER,
            site_mobile INTEGER,
            has_booking INTEGER,
            has_catalog INTEGER,
            has_whatsapp INTEGER,
            score INTEGER,
            score_reasons TEXT,
            visited INTEGER DEFAULT 0,
            visited_at TEXT,
            notes TEXT,
            first_seen_at TEXT NOT NULL,
            last_seen_at TEXT NOT NULL,
            raw_json TEXT
        )
        """,
    )
    _ensure_columns(conn, "businesses", {
        "opportunity_score": "INTEGER",
        "commercial_potential_score": "INTEGER",
        "visit_priority_score": "INTEGER",
        "conversion_probability": "REAL",
        "learning_reasons": "TEXT",
        "digital_maturity_score": "INTEGER",
        "score_profile": "TEXT",
        "site_title": "TEXT",
        "site_description": "TEXT",
        "site_quality_score": "INTEGER",
        "presence_completeness_score": "INTEGER",
        "has_contact_form": "INTEGER",
        "has_instagram": "INTEGER",
        "has_facebook": "INTEGER",
        "instagram_url": "TEXT",
        "facebook_url": "TEXT",
        "whatsapp_url": "TEXT",
        "emails_found": "TEXT",
        "booking_provider": "TEXT",
        "competitor_detected": "INTEGER",
        "competitor_name": "TEXT",
        "manual_booking_detected": "INTEGER",
        "manual_booking_channel": "TEXT",
        "manual_booking_evidence": "TEXT",
        "tech_stack": "TEXT",
        "open_now": "INTEGER",
        "opening_hours_text": "TEXT",
        "ai_summary": "TEXT",
        "sales_pitch": "TEXT",
        "why_approach": "TEXT",
        "pipeline_status": "TEXT DEFAULT 'NEW'",
        "assigned_to": "TEXT",
        "contact_name": "TEXT",
        "contact_phone": "TEXT",
        "next_action_at": "TEXT",
        "last_contact_at": "TEXT",
        "lost_reason": "TEXT",
        "do_not_contact": "INTEGER DEFAULT 0",
        "estimated_mrr": "REAL DEFAULT 89.90",
        "analysis_version": "TEXT",
        "last_analyzed_at": "TEXT",
        "campaign_name": "TEXT",
        "data_confidence": "INTEGER",
        "source_notes": "TEXT",
        "decision_maker_name": "TEXT",
        "decision_maker_role": "TEXT",
        "decision_maker_confidence": "INTEGER",
        "decision_maker_candidates": "TEXT",
        "company_size_estimate": "TEXT",
        "pitch_variant": "TEXT",
        "likely_objection": "TEXT",
        "ai_provider_used": "TEXT",
        "ai_model_used": "TEXT",
        "has_structured_data": "INTEGER",
        "has_local_business_schema": "INTEGER",
        "robots_noindex": "INTEGER",
        "ai_search_readiness_score": "INTEGER",
    })

    _execute(
        conn,
        f"""
        CREATE TABLE IF NOT EXISTS activities (
            id {activity_id},
            business_key TEXT NOT NULL,
            activity_type TEXT NOT NULL,
            details TEXT,
            outcome TEXT,
            created_at TEXT NOT NULL,
            FOREIGN KEY (business_key) REFERENCES businesses(business_key) ON DELETE CASCADE
        )
        """,
    )
    _ensure_columns(conn, "activities", {"actor_email": "TEXT"})

    _execute(
        conn,
        """
        CREATE TABLE IF NOT EXISTS website_analysis_cache (
            website TEXT PRIMARY KEY,
            result_json TEXT NOT NULL,
            analyzed_at TEXT NOT NULL
        )
        """,
    )
    _execute(
        conn,
        f"""
        CREATE TABLE IF NOT EXISTS followups (
            id {followup_id},
            business_key TEXT NOT NULL,
            title TEXT NOT NULL,
            due_at TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'PENDING',
            source TEXT,
            notes TEXT,
            created_at TEXT NOT NULL,
            completed_at TEXT,
            FOREIGN KEY (business_key) REFERENCES businesses(business_key) ON DELETE CASCADE
        )
        """,
    )
    _execute(
        conn,
        f"""
        CREATE TABLE IF NOT EXISTS goals (
            id {goal_id},
            metric TEXT NOT NULL,
            target REAL NOT NULL,
            period TEXT NOT NULL DEFAULT 'DAILY',
            start_at TEXT NOT NULL,
            end_at TEXT NOT NULL,
            label TEXT,
            active INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL
        )
        """,
    )
    _execute(
        conn,
        f"""
        CREATE TABLE IF NOT EXISTS search_jobs (
            id {job_id},
            query_text TEXT NOT NULL,
            center_lat REAL NOT NULL,
            center_lon REAL NOT NULL,
            center_display_name TEXT,
            radius_m INTEGER NOT NULL,
            provider TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'QUEUED',
            stage TEXT NOT NULL DEFAULT 'DISCOVERED',
            total_items INTEGER NOT NULL DEFAULT 0,
            processed_items INTEGER NOT NULL DEFAULT 0,
            failed_items INTEGER NOT NULL DEFAULT 0,
            reused_items INTEGER NOT NULL DEFAULT 0,
            new_items INTEGER NOT NULL DEFAULT 0,
            config_json TEXT,
            created_by TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            error TEXT
        )
        """,
    )
    _execute(
        conn,
        f"""
        CREATE TABLE IF NOT EXISTS search_job_items (
            id {job_item_id},
            job_id INTEGER NOT NULL,
            business_key TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'PENDING',
            raw_json TEXT NOT NULL,
            result_json TEXT,
            error TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            UNIQUE(job_id, business_key),
            FOREIGN KEY (job_id) REFERENCES search_jobs(id) ON DELETE CASCADE
        )
        """,
    )
    _execute(
        conn,
        f"""
        CREATE TABLE IF NOT EXISTS ai_usage (
            id {ai_usage_id},
            provider TEXT NOT NULL,
            model TEXT,
            business_key TEXT,
            input_tokens INTEGER DEFAULT 0,
            output_tokens INTEGER DEFAULT 0,
            estimated_cost_usd REAL DEFAULT 0,
            success INTEGER NOT NULL DEFAULT 1,
            error TEXT,
            created_at TEXT NOT NULL
        )
        """,
    )
    _execute(
        conn,
        """
        CREATE TABLE IF NOT EXISTS app_settings (
            setting_key TEXT PRIMARY KEY,
            value_json TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """,
    )
    _execute(
        conn,
        f"""
        CREATE TABLE IF NOT EXISTS business_snapshots (
            id {snapshot_id},
            business_key TEXT NOT NULL,
            snapshot_json TEXT NOT NULL,
            reason TEXT,
            created_at TEXT NOT NULL,
            FOREIGN KEY (business_key) REFERENCES businesses(business_key) ON DELETE CASCADE
        )
        """,
    )

    indexes = [
        ("idx_businesses_pipeline", "CREATE INDEX IF NOT EXISTS idx_businesses_pipeline ON businesses(pipeline_status)"),
        ("idx_businesses_score", "CREATE INDEX IF NOT EXISTS idx_businesses_score ON businesses(score)"),
        ("idx_businesses_priority", "CREATE INDEX IF NOT EXISTS idx_businesses_priority ON businesses(visit_priority_score)"),
        ("idx_activities_business", "CREATE INDEX IF NOT EXISTS idx_activities_business ON activities(business_key, created_at DESC)"),
        ("idx_followups_due", "CREATE INDEX IF NOT EXISTS idx_followups_due ON followups(status, due_at)"),
        ("idx_goals_period", "CREATE INDEX IF NOT EXISTS idx_goals_period ON goals(active, start_at, end_at)"),
        ("idx_search_jobs_status", "CREATE INDEX IF NOT EXISTS idx_search_jobs_status ON search_jobs(status, updated_at)"),
        ("idx_search_job_items_status", "CREATE INDEX IF NOT EXISTS idx_search_job_items_status ON search_job_items(job_id, status, id)"),
        ("idx_ai_usage_created", "CREATE INDEX IF NOT EXISTS idx_ai_usage_created ON ai_usage(created_at, provider)"),
        ("idx_business_snapshots_key", "CREATE INDEX IF NOT EXISTS idx_business_snapshots_key ON business_snapshots(business_key, created_at DESC)"),
    ]
    for index_name, ddl in indexes:
        _ensure_index(conn, index_name, ddl)

    # Supabase Security Advisor: tables in the public schema should have RLS
    # enabled. No PostgREST policy is intentionally created because these are
    # internal CRM tables; the Render backend accesses PostgreSQL directly.
    _enable_rls(conn, [
        "businesses",
        "website_analysis_cache",
        "followups",
        "goals",
        "activities",
        "search_jobs",
        "search_job_items",
        "ai_usage",
        "app_settings",
        "business_snapshots",
    ])

    _set_schema_version(conn, SCHEMA_VERSION)


def init_db():
    """Initialize/migrate the database once, safely under concurrent startup.

    Streamlit can start more than one session at the same time and Render can
    overlap old/new instances during deploy. Previous versions allowed both to
    execute DDL concurrently, which caused PostgreSQL deadlocks between
    CREATE INDEX and ALTER TABLE. This function serializes migrations locally
    and with a PostgreSQL advisory lock, and stores a schema version so normal
    startups perform no DDL at all.
    """
    global _DB_INITIALIZED
    if _DB_INITIALIZED:
        return

    with _INIT_LOCK:
        if _DB_INITIALIZED:
            return

        attempts = 4 if USE_POSTGRES else 1
        last_error = None
        for attempt in range(attempts):
            try:
                with _conn() as conn:
                    # Fast path: after the first successful migration, normal
                    # starts only perform a couple of read-only catalog queries.
                    if _schema_version(conn) >= SCHEMA_VERSION:
                        try:
                            conn.rollback()  # close the read transaction cleanly
                        except Exception:
                            pass
                        _DB_INITIALIZED = True
                        return

                    lock_acquired = False
                    try:
                        if USE_POSTGRES:
                            _acquire_migration_lock(conn)
                            lock_acquired = True
                            # Another Render/Streamlit process may have finished
                            # the migration while this process was waiting.
                            if _schema_version(conn) >= SCHEMA_VERSION:
                                conn.commit()
                                _DB_INITIALIZED = True
                                return
                            # Avoid waiting forever behind an unrelated long write.
                            _execute(conn, "SET LOCAL lock_timeout = '20s'")
                            _execute(conn, "SET LOCAL statement_timeout = '120s'")

                        _apply_schema(conn)
                        conn.commit()
                        _DB_INITIALIZED = True
                        return
                    except Exception:
                        try:
                            conn.rollback()
                        except Exception:
                            pass
                        raise
                    finally:
                        if USE_POSTGRES and lock_acquired:
                            _release_migration_lock(conn)
            except Exception as exc:
                last_error = exc
                if attempt + 1 < attempts and _retryable_init_error(exc):
                    time.sleep(0.8 * (2 ** attempt))
                    continue
                raise

        if last_error:
            raise last_error

def _bool(value):
    if value is None:
        return None
    return int(bool(value))


def _json(value, default):
    if value is None:
        return json.dumps(default, ensure_ascii=False)
    if isinstance(value, str):
        try:
            json.loads(value)
            return value
        except Exception:
            pass
    return json.dumps(value, ensure_ascii=False)


def _decode_business(row):
    r = dict(row)
    for f in {
        "site_functional", "site_https", "site_mobile", "has_booking", "has_catalog", "has_whatsapp",
        "has_contact_form", "has_instagram", "has_facebook", "competitor_detected", "manual_booking_detected",
        "visited", "do_not_contact", "open_now", "has_structured_data", "has_local_business_schema", "robots_noindex",
    }:
        if r.get(f) is not None:
            r[f] = bool(r[f])
    for f, default in (("score_reasons", []), ("learning_reasons", []), ("emails_found", []), ("decision_maker_candidates", [])):
        try:
            r[f] = json.loads(r.get(f) or "[]")
        except Exception:
            r[f] = default
    return r


def upsert_businesses(rows):
    now = datetime.now(timezone.utc).isoformat()
    preserve_fields = [
        "visited", "visited_at", "notes", "first_seen_at", "pipeline_status", "assigned_to",
        "contact_name", "contact_phone", "next_action_at", "last_contact_at", "lost_reason", "do_not_contact",
        "estimated_mrr", "pitch_variant",
    ]
    with _conn() as conn:
        for row in rows:
            current = _execute(conn, "SELECT * FROM businesses WHERE business_key = ?", (row["business_key"],)).fetchone()
            current = dict(current) if current else {}
            if current:
                tracked = ["website", "site_functional", "has_booking", "competitor_name", "manual_booking_detected", "booking_provider"]
                changed = any(
                    row.get(k) is not None and str(row.get(k)) != str(current.get(k))
                    for k in tracked
                )
                if changed:
                    snapshot = {k: current.get(k) for k in ["name", "website", "site_functional", "has_booking", "competitor_name", "manual_booking_detected", "booking_provider", "last_analyzed_at"]}
                    _execute(
                        conn,
                        "INSERT INTO business_snapshots(business_key,snapshot_json,reason,created_at) VALUES(?,?,?,?)",
                        (row["business_key"], json.dumps(snapshot, ensure_ascii=False), "DIGITAL_CHANGE", now),
                    )
            preserved = {k: current.get(k) for k in preserve_fields}
            first_seen = preserved.get("first_seen_at") or now
            pipeline_status = preserved.get("pipeline_status") or row.get("pipeline_status") or "NEW"
            visited = preserved.get("visited") if preserved.get("visited") is not None else int(bool(row.get("visited", False)))
            dnc = preserved.get("do_not_contact") if preserved.get("do_not_contact") is not None else int(bool(row.get("do_not_contact", False)))
            estimated_mrr = preserved.get("estimated_mrr") if preserved.get("estimated_mrr") is not None else float(row.get("estimated_mrr") or 89.90)

            values = {
                "business_key": row["business_key"], "provider": row.get("provider") or "unknown",
                "source_id": row.get("source_id"), "name": row.get("name") or row["business_key"],
                "address": row.get("address"), "lat": row.get("lat"), "lon": row.get("lon"),
                "category": row.get("category"), "phone": row.get("phone"), "website": row.get("website"),
                "rating": row.get("rating"), "reviews": row.get("reviews"), "maps_url": row.get("maps_url"),
                "site_functional": _bool(row.get("site_functional")), "site_status": row.get("site_status"),
                "site_response_ms": row.get("site_response_ms"), "site_https": _bool(row.get("site_https")),
                "site_mobile": _bool(row.get("site_mobile")), "has_booking": _bool(row.get("has_booking")),
                "has_catalog": _bool(row.get("has_catalog")), "has_whatsapp": _bool(row.get("has_whatsapp")),
                "score": row.get("score"), "score_reasons": _json(row.get("score_reasons"), []),
                "opportunity_score": row.get("opportunity_score") or row.get("score"),
                "commercial_potential_score": row.get("commercial_potential_score"),
                "visit_priority_score": row.get("visit_priority_score"),
                "conversion_probability": row.get("conversion_probability"),
                "learning_reasons": _json(row.get("learning_reasons"), []),
                "visited": visited, "visited_at": preserved.get("visited_at"), "notes": preserved.get("notes") or "",
                "first_seen_at": first_seen, "last_seen_at": now, "raw_json": _json(row.get("raw"), {}),
                "digital_maturity_score": row.get("digital_maturity_score"), "score_profile": row.get("score_profile"),
                "site_title": row.get("site_title"), "site_description": row.get("site_description"),
                "site_quality_score": row.get("site_quality_score"),
                "presence_completeness_score": row.get("presence_completeness_score"),
                "has_contact_form": _bool(row.get("has_contact_form")), "has_instagram": _bool(row.get("has_instagram")),
                "has_facebook": _bool(row.get("has_facebook")), "instagram_url": row.get("instagram_url"),
                "facebook_url": row.get("facebook_url"), "whatsapp_url": row.get("whatsapp_url"),
                "emails_found": _json(row.get("emails_found"), []), "booking_provider": row.get("booking_provider"),
                "competitor_detected": _bool(row.get("competitor_detected")), "competitor_name": row.get("competitor_name"),
                "manual_booking_detected": _bool(row.get("manual_booking_detected")),
                "manual_booking_channel": row.get("manual_booking_channel"),
                "manual_booking_evidence": row.get("manual_booking_evidence"), "tech_stack": row.get("tech_stack"),
                "open_now": _bool(row.get("open_now")), "opening_hours_text": row.get("opening_hours_text"),
                "ai_summary": row.get("ai_summary"), "sales_pitch": row.get("sales_pitch"),
                "why_approach": row.get("why_approach"), "pipeline_status": pipeline_status,
                "assigned_to": preserved.get("assigned_to") or "", "contact_name": preserved.get("contact_name") or "",
                "contact_phone": preserved.get("contact_phone") or "", "next_action_at": preserved.get("next_action_at"),
                "last_contact_at": preserved.get("last_contact_at"), "lost_reason": preserved.get("lost_reason") or "",
                "do_not_contact": dnc, "estimated_mrr": estimated_mrr,
                "analysis_version": row.get("analysis_version"), "last_analyzed_at": row.get("last_analyzed_at"),
                "campaign_name": row.get("campaign_name") or current.get("campaign_name") or "Prospecção geral",
                "data_confidence": row.get("data_confidence"), "source_notes": row.get("source_notes"),
                "decision_maker_name": row.get("decision_maker_name"), "decision_maker_role": row.get("decision_maker_role"),
                "decision_maker_confidence": row.get("decision_maker_confidence"),
                "decision_maker_candidates": _json(row.get("decision_maker_candidates"), []),
                "company_size_estimate": row.get("company_size_estimate"),
                "pitch_variant": preserved.get("pitch_variant") or row.get("pitch_variant") or "A",
                "likely_objection": row.get("likely_objection"),
                "ai_provider_used": row.get("ai_provider_used"), "ai_model_used": row.get("ai_model_used"),
                "has_structured_data": _bool(row.get("has_structured_data")),
                "has_local_business_schema": _bool(row.get("has_local_business_schema")),
                "robots_noindex": _bool(row.get("robots_noindex")),
                "ai_search_readiness_score": row.get("ai_search_readiness_score"),
            }
            cols = list(values)
            placeholders = ",".join("?" for _ in cols)
            updates = ",".join(f"{c}=excluded.{c}" for c in cols if c not in {"business_key", "first_seen_at"})
            _execute(
                conn,
                f"INSERT INTO businesses ({','.join(cols)}) VALUES ({placeholders}) "
                f"ON CONFLICT(business_key) DO UPDATE SET {updates}",
                tuple(values[c] for c in cols),
            )
        conn.commit()


def hydrate_saved_state(rows, analysis_max_age_days=14):
    if not rows:
        return rows
    cutoff = datetime.now(timezone.utc) - timedelta(days=int(analysis_max_age_days))
    analysis_fields = [
        "site_functional", "site_status", "site_response_ms", "site_https", "site_mobile", "has_booking",
        "has_catalog", "has_whatsapp", "site_title", "site_description", "site_quality_score",
        "presence_completeness_score", "has_contact_form", "has_instagram", "has_facebook", "instagram_url",
        "facebook_url", "whatsapp_url", "emails_found", "booking_provider", "competitor_detected", "competitor_name",
        "manual_booking_detected", "manual_booking_channel", "manual_booking_evidence", "tech_stack", "ai_summary",
        "sales_pitch", "why_approach", "analysis_version", "last_analyzed_at",
        "decision_maker_name", "decision_maker_role", "decision_maker_confidence", "decision_maker_candidates",
        "company_size_estimate", "likely_objection", "ai_provider_used", "ai_model_used", "data_confidence", "source_notes",
        "has_structured_data", "has_local_business_schema", "robots_noindex", "ai_search_readiness_score",
    ]
    persistent_fields = [
        "visited", "visited_at", "notes", "pipeline_status", "assigned_to", "contact_name", "contact_phone",
        "next_action_at", "last_contact_at", "lost_reason", "do_not_contact", "estimated_mrr", "pitch_variant",
    ]
    with _conn() as conn:
        for row in rows:
            saved = _execute(conn, "SELECT * FROM businesses WHERE business_key=?", (row["business_key"],)).fetchone()
            if not saved:
                continue
            saved = _decode_business(saved)
            for f in persistent_fields:
                if f in saved:
                    row[f] = saved[f]
            fresh = False
            if saved.get("last_analyzed_at"):
                try:
                    dt = datetime.fromisoformat(saved["last_analyzed_at"])
                    fresh = dt >= cutoff
                except Exception:
                    fresh = False
            if fresh and saved.get("website") == row.get("website"):
                for f in analysis_fields:
                    row[f] = saved.get(f)
                row["analysis_cached"] = True
    return rows


def get_visit_state(keys):
    if not keys:
        return {}
    placeholders = ",".join("?" for _ in keys)
    with _conn() as conn:
        rows = _execute(conn, f"SELECT * FROM businesses WHERE business_key IN ({placeholders})", tuple(keys)).fetchall()
    result = {}
    for row in rows:
        r = _decode_business(row)
        result[r["business_key"]] = {
            k: r.get(k) for k in [
                "visited", "visited_at", "notes", "pipeline_status", "assigned_to", "contact_name", "contact_phone",
                "next_action_at", "do_not_contact", "estimated_mrr", "conversion_probability", "visit_priority_score",
            ]
        }
    return result


def update_visit(business_key, visited, notes=""):
    visited_at = datetime.now(timezone.utc).isoformat() if visited else None
    with _conn() as conn:
        old = _execute(conn, "SELECT visited FROM businesses WHERE business_key=?", (business_key,)).fetchone()
        _execute(
            conn,
            "UPDATE businesses SET visited=?, visited_at=?, notes=?, pipeline_status=CASE WHEN ?=1 AND pipeline_status IN ('NEW','PRIORITY','ROUTE_PLANNED') THEN 'VISITED' ELSE pipeline_status END WHERE business_key=?",
            (int(bool(visited)), visited_at, notes or "", int(bool(visited)), business_key),
        )
        if visited and (not old or not old["visited"]):
            _execute(
                conn,
                "INSERT INTO activities(business_key, activity_type, details, created_at) VALUES(?,?,?,?)",
                (business_key, "VISIT", notes or "Visita marcada como realizada", datetime.now(timezone.utc).isoformat()),
            )
        conn.commit()
    recalculate_business_score(business_key)


def _auto_followup_for_status(business_key, pipeline_status):
    rules = {
        "INTERESTED": (2, "Retornar para lead interessado"),
        "DEMO": (1, "Follow-up após demonstração"),
        "PROPOSAL": (3, "Follow-up da proposta"),
    }
    if pipeline_status not in rules:
        return None
    days, title = rules[pipeline_status]
    return create_followup(
        business_key, title, datetime.now(timezone.utc) + timedelta(days=days),
        source=f"AUTO_{pipeline_status}", dedupe=True,
    )


def update_crm(business_key, pipeline_status="NEW", assigned_to="", contact_name="", contact_phone="", next_action_at=None,
               notes="", do_not_contact=False, lost_reason="", estimated_mrr=None, auto_followup=True, actor_email=""):

    now = datetime.now(timezone.utc).isoformat()
    with _conn() as conn:
        before = _execute(conn, "SELECT pipeline_status FROM businesses WHERE business_key=?", (business_key,)).fetchone()
        if estimated_mrr is None:
            _execute(
                conn,
                """
                UPDATE businesses SET pipeline_status=?, assigned_to=?, contact_name=?, contact_phone=?, next_action_at=?,
                    notes=?, do_not_contact=?, lost_reason=?,
                    last_contact_at=CASE WHEN ?=1 THEN ? ELSE last_contact_at END
                WHERE business_key=?
                """,
                (pipeline_status, assigned_to or "", contact_name or "", contact_phone or "", next_action_at,
                 notes or "", int(bool(do_not_contact)), lost_reason or "",
                 int(pipeline_status not in {"NEW", "PRIORITY", "ROUTE_PLANNED"}), now, business_key),
            )
        else:
            _execute(
                conn,
                """
                UPDATE businesses SET pipeline_status=?, assigned_to=?, contact_name=?, contact_phone=?, next_action_at=?,
                    notes=?, do_not_contact=?, lost_reason=?, estimated_mrr=?,
                    last_contact_at=CASE WHEN ?=1 THEN ? ELSE last_contact_at END
                WHERE business_key=?
                """,
                (pipeline_status, assigned_to or "", contact_name or "", contact_phone or "", next_action_at,
                 notes or "", int(bool(do_not_contact)), lost_reason or "", float(estimated_mrr),
                 int(pipeline_status not in {"NEW", "PRIORITY", "ROUTE_PLANNED"}), now, business_key),
            )
        if before and before["pipeline_status"] != pipeline_status:
            _execute(
                conn,
                "INSERT INTO activities(business_key, activity_type, details, outcome, created_at, actor_email) VALUES(?,?,?,?,?,?)",
                (business_key, "STATUS_CHANGE", f"{before['pipeline_status']} → {pipeline_status}", pipeline_status, now, actor_email or None),
            )
        conn.commit()
    if auto_followup:
        _auto_followup_for_status(business_key, pipeline_status)
    recalculate_business_score(business_key)


def add_activity(business_key, activity_type, details="", outcome="", actor_email=""):
    now = datetime.now(timezone.utc).isoformat()
    with _conn() as conn:
        _execute(
            conn,
            "INSERT INTO activities(business_key, activity_type, details, outcome, created_at, actor_email) VALUES(?,?,?,?,?,?)",
            (business_key, activity_type, details or "", outcome or "", now, actor_email or None),
        )
        _execute(conn, "UPDATE businesses SET last_contact_at=? WHERE business_key=?", (now, business_key))
        conn.commit()


def quick_outcome(business_key, outcome, notes="", actor_email=""):
    outcome = (outcome or "").upper()
    now = datetime.now(timezone.utc)
    mapping = {
        "VISITED": "VISITED", "NO_OWNER": "VISITED", "INTERESTED": "INTERESTED",
        "DEMO": "DEMO", "PROPOSAL": "PROPOSAL", "CLIENT": "CLIENT", "NOT_INTERESTED": "LOST",
    }
    status = mapping.get(outcome, "VISITED")
    update_visit(business_key, True, notes)
    update_crm(business_key, status, notes=notes, lost_reason="Sem interesse" if outcome == "NOT_INTERESTED" else "", actor_email=actor_email)
    add_activity(business_key, "STREET_OUTCOME", notes, outcome, actor_email=actor_email)
    if outcome == "NO_OWNER":
        create_followup(business_key, "Tentar novamente quando o responsável estiver", now + timedelta(days=1), source="AUTO_NO_OWNER", dedupe=True)
    elif outcome == "VISITED":
        create_followup(business_key, "Definir próximo passo da visita", now + timedelta(days=1), source="AUTO_VISIT", dedupe=True)
    return status


def load_activities(business_key=None, limit=500):
    with _conn() as conn:
        if business_key:
            rows = _execute(conn, "SELECT * FROM activities WHERE business_key=? ORDER BY created_at DESC LIMIT ?", (business_key, int(limit))).fetchall()
        else:
            rows = _execute(conn, "SELECT * FROM activities ORDER BY created_at DESC LIMIT ?", (int(limit),)).fetchall()
    return [dict(r) for r in rows]


def load_history(limit=5000):
    with _conn() as conn:
        rows = _execute(conn, "SELECT * FROM businesses ORDER BY last_seen_at DESC LIMIT ?", (int(limit),)).fetchall()
    return [_decode_business(r) for r in rows]


def recalculate_business_score(business_key):
    from scoring import build_sales_pitch, build_why_approach, score_business
    with _conn() as conn:
        row = _execute(conn, "SELECT * FROM businesses WHERE business_key=?", (business_key,)).fetchone()
        if not row:
            return None
        lead = _decode_business(row)
        profile = lead.get("score_profile") or "Auto"
        score, reasons = score_business(lead, profile)
        why = build_why_approach(lead)
        pitch = build_sales_pitch(lead)
        _execute(
            conn,
            """UPDATE businesses SET score=?, opportunity_score=?, score_reasons=?, digital_maturity_score=?,
               commercial_potential_score=?, visit_priority_score=?, why_approach=?, sales_pitch=? WHERE business_key=?""",
            (score, lead.get("opportunity_score"), json.dumps(reasons, ensure_ascii=False), lead.get("digital_maturity_score"),
             lead.get("commercial_potential_score"), lead.get("visit_priority_score"), why, pitch, business_key),
        )
        conn.commit()
    return score


def get_cached_site_analysis(website, max_age_days=14):
    if not website:
        return None
    cutoff = datetime.now(timezone.utc) - timedelta(days=int(max_age_days))
    with _conn() as conn:
        row = _execute(conn, "SELECT * FROM website_analysis_cache WHERE website=?", (website,)).fetchone()
    if not row:
        return None
    try:
        if datetime.fromisoformat(row["analyzed_at"]) < cutoff:
            return None
        return json.loads(row["result_json"])
    except Exception:
        return None


def set_cached_site_analysis(website, result):
    if not website:
        return
    analyzed_at = datetime.now(timezone.utc).isoformat()
    result_json = json.dumps(result, ensure_ascii=False)
    with _conn() as conn:
        _execute(
            conn,
            """INSERT INTO website_analysis_cache(website, result_json, analyzed_at) VALUES(?,?,?)
               ON CONFLICT(website) DO UPDATE SET result_json=excluded.result_json, analyzed_at=excluded.analyzed_at""",
            (website, result_json, analyzed_at),
        )
        conn.commit()


def create_followup(business_key, title, due_at, source="MANUAL", notes="", dedupe=False):
    if isinstance(due_at, datetime):
        due_at = due_at.isoformat()
    now = datetime.now(timezone.utc).isoformat()
    with _conn() as conn:
        if dedupe:
            existing = _execute(
                conn,
                "SELECT id FROM followups WHERE business_key=? AND source=? AND status='PENDING' ORDER BY due_at LIMIT 1",
                (business_key, source),
            ).fetchone()
            if existing:
                _execute(conn, "UPDATE followups SET title=?, due_at=?, notes=? WHERE id=?", (title, due_at, notes or "", existing["id"]))
                conn.commit()
                return existing["id"]
        if USE_POSTGRES:
            cur = _execute(
                conn,
                "INSERT INTO followups(business_key,title,due_at,status,source,notes,created_at) VALUES(?,?,?,?,?,?,?) RETURNING id",
                (business_key, title, due_at, "PENDING", source, notes or "", now),
            )
            followup_id = cur.fetchone()["id"]
        else:
            cur = _execute(
                conn,
                "INSERT INTO followups(business_key,title,due_at,status,source,notes,created_at) VALUES(?,?,?,?,?,?,?)",
                (business_key, title, due_at, "PENDING", source, notes or "", now),
            )
            followup_id = cur.lastrowid
        _execute(conn, "UPDATE businesses SET next_action_at=? WHERE business_key=?", (due_at, business_key))
        conn.commit()
        return followup_id


def load_followups(status="PENDING", limit=1000):
    with _conn() as conn:
        if status:
            rows = _execute(
                conn,
                """SELECT f.*, b.name AS business_name, b.phone, b.contact_name, b.assigned_to, b.pipeline_status
                   FROM followups f JOIN businesses b ON b.business_key=f.business_key
                   WHERE f.status=? ORDER BY f.due_at LIMIT ?""", (status, int(limit)),
            ).fetchall()
        else:
            rows = _execute(
                conn,
                """SELECT f.*, b.name AS business_name, b.phone, b.contact_name, b.assigned_to, b.pipeline_status
                   FROM followups f JOIN businesses b ON b.business_key=f.business_key
                   ORDER BY f.due_at DESC LIMIT ?""", (int(limit),),
            ).fetchall()
    return [dict(r) for r in rows]


def complete_followup(followup_id, status="DONE"):
    completed = datetime.now(timezone.utc).isoformat() if status == "DONE" else None
    with _conn() as conn:
        row = _execute(conn, "SELECT business_key FROM followups WHERE id=?", (int(followup_id),)).fetchone()
        _execute(conn, "UPDATE followups SET status=?, completed_at=? WHERE id=?", (status, completed, int(followup_id)))
        if row:
            nxt = _execute(
                conn,
                "SELECT due_at FROM followups WHERE business_key=? AND status='PENDING' ORDER BY due_at LIMIT 1",
                (row["business_key"],),
            ).fetchone()
            _execute(conn, "UPDATE businesses SET next_action_at=? WHERE business_key=?", (nxt["due_at"] if nxt else None, row["business_key"]))
        conn.commit()


def due_followup_count():
    now = datetime.now(timezone.utc).isoformat()
    with _conn() as conn:
        row = _execute(conn, "SELECT COUNT(*) AS c FROM followups WHERE status='PENDING' AND due_at<=?", (now,)).fetchone()
    return int(row["c"] if row else 0)


def create_goal(metric, target, start_at, end_at, period="DAILY", label=""):
    now = datetime.now(timezone.utc).isoformat()
    if isinstance(start_at, datetime):
        start_at = start_at.isoformat()
    if isinstance(end_at, datetime):
        end_at = end_at.isoformat()
    with _conn() as conn:
        if USE_POSTGRES:
            cur = _execute(conn,
                "INSERT INTO goals(metric,target,period,start_at,end_at,label,active,created_at) VALUES(?,?,?,?,?,?,1,?) RETURNING id",
                (metric, float(target), period, start_at, end_at, label or "", now))
            goal_id = cur.fetchone()["id"]
        else:
            cur = _execute(conn,
                "INSERT INTO goals(metric,target,period,start_at,end_at,label,active,created_at) VALUES(?,?,?,?,?,?,1,?)",
                (metric, float(target), period, start_at, end_at, label or "", now))
            goal_id = cur.lastrowid
        conn.commit()
        return goal_id


def load_goals(active_only=True, limit=200):
    with _conn() as conn:
        if active_only:
            now = datetime.now(timezone.utc).isoformat()
            rows = _execute(conn, "SELECT * FROM goals WHERE active=1 AND end_at>? ORDER BY start_at DESC LIMIT ?", (now, int(limit))).fetchall()
        else:
            rows = _execute(conn, "SELECT * FROM goals ORDER BY created_at DESC LIMIT ?", (int(limit),)).fetchall()
    return [dict(r) for r in rows]


def deactivate_goal(goal_id):
    with _conn() as conn:
        _execute(conn, "UPDATE goals SET active=0 WHERE id=?", (int(goal_id),))
        conn.commit()


def goal_progress(metric, start_at, end_at):
    if isinstance(start_at, datetime):
        start_at = start_at.isoformat()
    if isinstance(end_at, datetime):
        end_at = end_at.isoformat()
    metric = (metric or "").upper()
    with _conn() as conn:
        if metric == "LEADS":
            row = _execute(conn, "SELECT COUNT(*) AS v FROM businesses WHERE first_seen_at>=? AND first_seen_at<?", (start_at, end_at)).fetchone()
            return float(row["v"] or 0)
        if metric == "CONTACTS":
            row = _execute(conn, """SELECT COUNT(DISTINCT business_key) AS v FROM activities
                WHERE created_at>=? AND created_at<? AND activity_type IN ('VISIT','CALL','WHATSAPP','EMAIL','FOLLOW_UP','STREET_OUTCOME','ARRIVED')""", (start_at, end_at)).fetchone()
            return float(row["v"] or 0)
        outcome_map = {"VISITS": "VISITED", "INTERESTED": "INTERESTED", "DEMOS": "DEMO", "PROPOSALS": "PROPOSAL", "CLIENTS": "CLIENT"}
        if metric in outcome_map:
            outcome = outcome_map[metric]
            if metric == "VISITS":
                row = _execute(conn, """SELECT COUNT(DISTINCT business_key) AS v FROM activities
                    WHERE created_at>=? AND created_at<? AND (outcome='VISITED' OR activity_type='ARRIVED' OR activity_type='VISIT')""", (start_at, end_at)).fetchone()
            else:
                row = _execute(conn, "SELECT COUNT(DISTINCT business_key) AS v FROM activities WHERE created_at>=? AND created_at<? AND outcome=?", (start_at, end_at, outcome)).fetchone()
            return float(row["v"] or 0)
        if metric == "MRR":
            row = _execute(conn, """SELECT COALESCE(SUM(b.estimated_mrr),0) AS v FROM businesses b
                WHERE b.business_key IN (SELECT DISTINCT business_key FROM activities WHERE created_at>=? AND created_at<? AND outcome='CLIENT')""", (start_at, end_at)).fetchone()
            return float(row["v"] or 0)
    return 0.0


def database_backend_name():
    return "Supabase/PostgreSQL" if USE_POSTGRES else "SQLite local"

# -----------------------------
# production helpers
# -----------------------------

def existing_business_keys(keys):
    keys = [k for k in (keys or []) if k]
    if not keys:
        return set()
    found = set()
    # Evita queries gigantes no SQLite/Postgres.
    for i in range(0, len(keys), 500):
        chunk = keys[i:i+500]
        placeholders = ",".join("?" for _ in chunk)
        with _conn() as conn:
            rows = _execute(conn, f"SELECT business_key FROM businesses WHERE business_key IN ({placeholders})", tuple(chunk)).fetchall()
        found.update(r["business_key"] for r in rows)
    return found


def create_search_job(query_text, center, radius_m, provider, rows, config=None, created_by=""):
    rows = rows or []
    now = datetime.now(timezone.utc).isoformat()
    keys = [r.get("business_key") for r in rows if r.get("business_key")]
    existing = existing_business_keys(keys)
    new_count = sum(k not in existing for k in keys)
    reused_count = len(keys) - new_count
    config_json = json.dumps(config or {}, ensure_ascii=False)
    with _conn() as conn:
        if USE_POSTGRES:
            cur = _execute(
                conn,
                """INSERT INTO search_jobs(query_text,center_lat,center_lon,center_display_name,radius_m,provider,status,stage,total_items,processed_items,failed_items,reused_items,new_items,config_json,created_by,created_at,updated_at)
                   VALUES(?,?,?,?,?,?,'RUNNING','ANALYZING',?,0,0,?,?,?, ?,?,?) RETURNING id""",
                (query_text, float(center["lat"]), float(center["lon"]), center.get("display_name"), int(radius_m), provider,
                 len(rows), reused_count, new_count, config_json, created_by or "", now, now),
            )
            job_id = cur.fetchone()["id"]
        else:
            cur = _execute(
                conn,
                """INSERT INTO search_jobs(query_text,center_lat,center_lon,center_display_name,radius_m,provider,status,stage,total_items,processed_items,failed_items,reused_items,new_items,config_json,created_by,created_at,updated_at)
                   VALUES(?,?,?,?,?,?,'RUNNING','ANALYZING',?,0,0,?,?,?, ?,?,?)""",
                (query_text, float(center["lat"]), float(center["lon"]), center.get("display_name"), int(radius_m), provider,
                 len(rows), reused_count, new_count, config_json, created_by or "", now, now),
            )
            job_id = cur.lastrowid
        for row in rows:
            if not row.get("business_key"):
                continue
            raw = json.dumps(row, ensure_ascii=False, default=str)
            _execute(
                conn,
                """INSERT INTO search_job_items(job_id,business_key,status,raw_json,created_at,updated_at)
                   VALUES(?,?,'PENDING',?,?,?) ON CONFLICT(job_id,business_key) DO NOTHING""",
                (job_id, row["business_key"], raw, now, now),
            )
        if not rows:
            _execute(conn, "UPDATE search_jobs SET status='DONE',stage='DONE',updated_at=? WHERE id=?", (now, job_id))
        conn.commit()
        return int(job_id)


def get_search_job(job_id):
    with _conn() as conn:
        row = _execute(conn, "SELECT * FROM search_jobs WHERE id=?", (int(job_id),)).fetchone()
    if not row:
        return None
    out = dict(row)
    try:
        out["config"] = json.loads(out.get("config_json") or "{}")
    except Exception:
        out["config"] = {}
    return out


def list_search_jobs(limit=30):
    with _conn() as conn:
        rows = _execute(conn, "SELECT * FROM search_jobs ORDER BY created_at DESC LIMIT ?", (int(limit),)).fetchall()
    return [dict(r) for r in rows]


def recover_stale_search_job_items(job_id, older_minutes=10):
    cutoff = (datetime.now(timezone.utc) - timedelta(minutes=int(older_minutes))).isoformat()
    now = datetime.now(timezone.utc).isoformat()
    with _conn() as conn:
        _execute(
            conn,
            "UPDATE search_job_items SET status='PENDING',updated_at=? WHERE job_id=? AND status='PROCESSING' AND updated_at<?",
            (now, int(job_id), cutoff),
        )
        conn.commit()


def claim_search_job_batch(job_id, limit=10):
    now = datetime.now(timezone.utc).isoformat()
    with _conn() as conn:
        rows = _execute(
            conn,
            "SELECT * FROM search_job_items WHERE job_id=? AND status='PENDING' ORDER BY id LIMIT ?",
            (int(job_id), int(limit)),
        ).fetchall()
        ids = [r["id"] for r in rows]
        for item_id in ids:
            _execute(conn, "UPDATE search_job_items SET status='PROCESSING',updated_at=? WHERE id=? AND status='PENDING'", (now, item_id))
        conn.commit()
    out = []
    for r in rows:
        d = dict(r)
        try:
            d["raw"] = json.loads(d.get("raw_json") or "{}")
        except Exception:
            d["raw"] = {}
        out.append(d)
    return out


def finish_search_job_item(item_id, result=None, error=None):
    now = datetime.now(timezone.utc).isoformat()
    status = "FAILED" if error else "DONE"
    payload = json.dumps(result or {}, ensure_ascii=False, default=str) if result is not None else None
    with _conn() as conn:
        row = _execute(conn, "SELECT job_id FROM search_job_items WHERE id=?", (int(item_id),)).fetchone()
        if not row:
            return
        job_id = row["job_id"]
        _execute(conn, "UPDATE search_job_items SET status=?,result_json=?,error=?,updated_at=? WHERE id=?",
                 (status, payload, (str(error)[:500] if error else None), now, int(item_id)))
        stats = _execute(
            conn,
            """SELECT COUNT(*) AS total,
                      SUM(CASE WHEN status='DONE' THEN 1 ELSE 0 END) AS done,
                      SUM(CASE WHEN status='FAILED' THEN 1 ELSE 0 END) AS failed,
                      SUM(CASE WHEN status='PENDING' THEN 1 ELSE 0 END) AS pending,
                      SUM(CASE WHEN status='PROCESSING' THEN 1 ELSE 0 END) AS processing
               FROM search_job_items WHERE job_id=?""",
            (job_id,),
        ).fetchone()
        done = int(stats["done"] or 0)
        failed = int(stats["failed"] or 0)
        pending = int(stats["pending"] or 0)
        processing = int(stats["processing"] or 0)
        final = pending == 0 and processing == 0
        if final and done == 0 and failed > 0:
            final_status, final_stage = "FAILED", "FAILED"
        elif final:
            final_status, final_stage = "DONE", "DONE"
        else:
            final_status, final_stage = "RUNNING", "ANALYZING"
        _execute(
            conn,
            "UPDATE search_jobs SET processed_items=?,failed_items=?,status=?,stage=?,updated_at=? WHERE id=?",
            (done, failed, final_status, final_stage, now, job_id),
        )
        conn.commit()


def fail_search_job(job_id, error):
    now = datetime.now(timezone.utc).isoformat()
    with _conn() as conn:
        _execute(conn, "UPDATE search_jobs SET status='FAILED',stage='FAILED',error=?,updated_at=? WHERE id=?",
                 (str(error)[:1000], now, int(job_id)))
        conn.commit()


def cancel_search_job(job_id):
    now = datetime.now(timezone.utc).isoformat()
    with _conn() as conn:
        _execute(conn, "UPDATE search_jobs SET status='CANCELED',stage='CANCELED',updated_at=? WHERE id=?", (now, int(job_id)))
        _execute(conn, "UPDATE search_job_items SET status='CANCELED',updated_at=? WHERE job_id=? AND status IN ('PENDING','PROCESSING')", (now, int(job_id)))
        conn.commit()


def load_job_businesses(job_id, limit=5000):
    with _conn() as conn:
        rows = _execute(
            conn,
            """SELECT b.* FROM search_job_items i JOIN businesses b ON b.business_key=i.business_key
               WHERE i.job_id=? AND i.status='DONE' ORDER BY b.visit_priority_score DESC, b.reviews DESC LIMIT ?""",
            (int(job_id), int(limit)),
        ).fetchall()
    return [_decode_business(r) for r in rows]


def set_app_setting(key, value):
    now = datetime.now(timezone.utc).isoformat()
    value_json = json.dumps(value, ensure_ascii=False)
    with _conn() as conn:
        _execute(conn,
                 """INSERT INTO app_settings(setting_key,value_json,updated_at) VALUES(?,?,?)
                    ON CONFLICT(setting_key) DO UPDATE SET value_json=excluded.value_json,updated_at=excluded.updated_at""",
                 (key, value_json, now))
        conn.commit()


def get_app_setting(key, default=None):
    with _conn() as conn:
        row = _execute(conn, "SELECT value_json FROM app_settings WHERE setting_key=?", (key,)).fetchone()
    if not row:
        return default
    try:
        return json.loads(row["value_json"])
    except Exception:
        return default


def record_ai_usage(provider, model, business_key=None, input_tokens=0, output_tokens=0, estimated_cost_usd=0.0, success=True, error=None):
    now = datetime.now(timezone.utc).isoformat()
    with _conn() as conn:
        _execute(conn,
                 """INSERT INTO ai_usage(provider,model,business_key,input_tokens,output_tokens,estimated_cost_usd,success,error,created_at)
                    VALUES(?,?,?,?,?,?,?,?,?)""",
                 (provider or "unknown", model or "", business_key, int(input_tokens or 0), int(output_tokens or 0),
                  float(estimated_cost_usd or 0), int(bool(success)), (str(error)[:500] if error else None), now))
        conn.commit()


def ai_usage_since(start_at):
    if isinstance(start_at, datetime):
        start_at = start_at.isoformat()
    with _conn() as conn:
        row = _execute(conn,
            """SELECT COUNT(*) AS calls, COALESCE(SUM(input_tokens),0) AS input_tokens,
                      COALESCE(SUM(output_tokens),0) AS output_tokens,
                      COALESCE(SUM(estimated_cost_usd),0) AS cost_usd,
                      COALESCE(SUM(CASE WHEN success=0 THEN 1 ELSE 0 END),0) AS errors
               FROM ai_usage WHERE created_at>=?""", (start_at,)).fetchone()
    return {"calls": int(row["calls"] or 0), "input_tokens": int(row["input_tokens"] or 0),
            "output_tokens": int(row["output_tokens"] or 0), "cost_usd": float(row["cost_usd"] or 0),
            "errors": int(row["errors"] or 0)}


def ai_usage_today():
    now = datetime.now(timezone.utc)
    start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    return ai_usage_since(start)


def load_business_snapshots(business_key, limit=50):
    with _conn() as conn:
        rows = _execute(conn, "SELECT * FROM business_snapshots WHERE business_key=? ORDER BY created_at DESC LIMIT ?",
                        (business_key, int(limit))).fetchall()
    out = []
    for r in rows:
        d = dict(r)
        try:
            d["snapshot"] = json.loads(d.get("snapshot_json") or "{}")
        except Exception:
            d["snapshot"] = {}
        out.append(d)
    return out


def conversion_funnel(start_at=None, end_at=None):
    clauses = []
    params = []
    if start_at:
        if isinstance(start_at, datetime): start_at = start_at.isoformat()
        clauses.append("created_at>=?")
        params.append(start_at)
    if end_at:
        if isinstance(end_at, datetime): end_at = end_at.isoformat()
        clauses.append("created_at<?")
        params.append(end_at)
    where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
    with _conn() as conn:
        total = _execute(conn, "SELECT COUNT(*) AS c FROM businesses").fetchone()["c"]
        activities = _execute(conn, f"SELECT business_key,activity_type,outcome FROM activities{where}", tuple(params)).fetchall()
    sets = {"CONTACTS": set(), "VISITS": set(), "INTERESTED": set(), "DEMOS": set(), "PROPOSALS": set(), "CLIENTS": set()}
    for a in activities:
        key = a["business_key"]
        typ = (a["activity_type"] or "").upper()
        out = (a["outcome"] or "").upper()
        if typ in {"VISIT","CALL","WHATSAPP","EMAIL","FOLLOW_UP","STREET_OUTCOME","ARRIVED","STATUS_CHANGE"}:
            sets["CONTACTS"].add(key)
        if typ in {"VISIT","ARRIVED","STREET_OUTCOME"} or out == "VISITED": sets["VISITS"].add(key)
        if out == "INTERESTED": sets["INTERESTED"].add(key)
        if out == "DEMO": sets["DEMOS"].add(key)
        if out == "PROPOSAL": sets["PROPOSALS"].add(key)
        if out == "CLIENT": sets["CLIENTS"].add(key)
    return {"LEADS": int(total), **{k: len(v) for k,v in sets.items()}}


def get_business(business_key):
    with _conn() as conn:
        row = _execute(conn, "SELECT * FROM businesses WHERE business_key=?", (business_key,)).fetchone()
    return _decode_business(row) if row else None


def list_businesses(limit=500, status=None, min_score=None, search=None):
    clauses=[]; params=[]
    if status:
        clauses.append("pipeline_status=?"); params.append(status)
    if min_score is not None:
        clauses.append("COALESCE(visit_priority_score,score,0)>=?"); params.append(int(min_score))
    if search:
        clauses.append("(LOWER(name) LIKE ? OR LOWER(COALESCE(address,'')) LIKE ?)")
        q=f"%{str(search).lower()}%"; params.extend([q,q])
    where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
    with _conn() as conn:
        rows=_execute(conn, f"SELECT * FROM businesses{where} ORDER BY COALESCE(visit_priority_score,score,0) DESC, last_seen_at DESC LIMIT ?", tuple(params+[int(limit)])).fetchall()
    return [_decode_business(r) for r in rows]


def get_job_peer_businesses(job_id, limit=5000):
    return load_job_businesses(job_id, limit=limit)


def dashboard_summary():
    with _conn() as conn:
        row=_execute(conn, """SELECT COUNT(*) total,
          SUM(CASE WHEN COALESCE(visit_priority_score,score,0)>=75 THEN 1 ELSE 0 END) hot,
          SUM(CASE WHEN visited=1 THEN 1 ELSE 0 END) visited,
          SUM(CASE WHEN pipeline_status='INTERESTED' THEN 1 ELSE 0 END) interested,
          SUM(CASE WHEN pipeline_status='CLIENT' THEN 1 ELSE 0 END) clients,
          SUM(CASE WHEN website IS NULL OR website='' THEN 1 ELSE 0 END) no_website
          FROM businesses""").fetchone()
    return dict(row or {})
