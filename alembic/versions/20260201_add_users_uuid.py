"""convert users id to uuid

Revision ID: add_users_uuid_001
Revises: add_user_metadata_001
Create Date: 2026-02-01
"""

from typing import Sequence, Union, List, Dict, Any, Optional

from alembic import op
import sqlalchemy as sa
import re


# revision identifiers, used by Alembic.
revision: str = "add_users_uuid_001"
down_revision: Union[str, Sequence[str], None] = "add_user_metadata_001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _drop_fk(inspector, table: str, referred_table: str, column: str) -> bool:
    fks = inspector.get_foreign_keys(table)
    for fk in fks:
        if fk.get("referred_table") != referred_table:
            continue
        constrained = set(fk.get("constrained_columns") or [])
        if column in constrained and fk.get("name"):
            op.drop_constraint(fk["name"], table, type_="foreignkey")
            return True
    return False


def _table_has_column(inspector, table: str, column: str) -> bool:
    try:
        cols = {c.get("name") for c in inspector.get_columns(table)}
    except Exception:
        return False
    return column in cols


def _fetch_policies(conn: sa.Connection, table: str, schema: str = "public") -> List[Dict[str, Any]]:
    has_pg_policies = conn.execute(
        sa.text("SELECT to_regclass('pg_catalog.pg_policies') IS NOT NULL"),
    ).scalar()
    if has_pg_policies:
        rows = conn.execute(
            sa.text(
                """
                SELECT policyname AS name,
                       permissive,
                       roles,
                       cmd,
                       qual,
                       with_check
                FROM pg_catalog.pg_policies
                WHERE schemaname = :schema
                  AND tablename = :table
                """
            ),
            {"table": table, "schema": schema},
        ).mappings().all()
        return [dict(row) for row in rows]

    rows = conn.execute(
        sa.text(
            """
            SELECT pol.polname AS name,
                   pol.polpermissive AS permissive,
                   ARRAY(
                       SELECT rolname
                       FROM pg_roles
                       WHERE oid = ANY(pol.polroles)
                   ) AS roles,
                   CASE pol.polcmd
                       WHEN 'r' THEN 'SELECT'
                       WHEN 'a' THEN 'INSERT'
                       WHEN 'w' THEN 'UPDATE'
                       WHEN 'd' THEN 'DELETE'
                       ELSE 'ALL'
                   END AS cmd,
                   pg_get_expr(pol.polqual, pol.polrelid) AS qual,
                   pg_get_expr(pol.polwithcheck, pol.polrelid) AS with_check
            FROM pg_policy pol
            JOIN pg_class cls ON pol.polrelid = cls.oid
            JOIN pg_namespace nsp ON cls.relnamespace = nsp.oid
            WHERE cls.relname = :table
              AND nsp.nspname = :schema
            """
        ),
        {"table": table, "schema": schema},
    ).mappings().all()
    return [dict(row) for row in rows]


def _drop_policies(table: str, policies: List[Dict[str, Any]], schema: str = "public") -> None:
    table_ref = f'"{schema}"."{table}"'
    for policy in policies:
        name = policy.get("name")
        if not name:
            continue
        op.execute(f'DROP POLICY IF EXISTS "{name}" ON {table_ref}')


def _quote_ident(value: str) -> str:
    return '"' + value.replace('"', '""') + '"'


def _parse_roles(raw: Any) -> List[str]:
    if raw is None:
        return []
    if isinstance(raw, (list, tuple)):
        return [str(item) for item in raw if item]
    if isinstance(raw, str):
        text = raw.strip()
        if text.startswith("{") and text.endswith("}"):
            inner = text[1:-1]
            if not inner:
                return []
            roles: List[str] = []
            buf: List[str] = []
            in_quotes = False
            i = 0
            while i < len(inner):
                ch = inner[i]
                if in_quotes:
                    if ch == '"':
                        if i + 1 < len(inner) and inner[i + 1] == '"':
                            buf.append('"')
                            i += 1
                        else:
                            in_quotes = False
                    else:
                        buf.append(ch)
                else:
                    if ch == '"':
                        in_quotes = True
                    elif ch == ",":
                        roles.append("".join(buf))
                        buf = []
                    else:
                        buf.append(ch)
                i += 1
            roles.append("".join(buf))
            return [role for role in roles if role]
        if text:
            return [text]
    return [str(raw)]


def _normalize_policy_expr(expr: Optional[str], cast_target: Optional[str]) -> Optional[str]:
    if not expr or not cast_target:
        return expr
    updated = expr
    cast_types = r"(?:uuid|text|varchar|character varying)"
    updated = re.sub(
        rf"\(+\s*auth\.uid\(\)(?:\s*::\s*{cast_types})*\s*\)+\s*::\s*{cast_types}",
        f"auth.uid()::{cast_target}",
        updated,
        flags=re.IGNORECASE,
    )
    updated = re.sub(
        rf"auth\.uid\(\)(?:\s*::\s*{cast_types})*",
        f"auth.uid()::{cast_target}",
        updated,
        flags=re.IGNORECASE,
    )
    return updated


def _create_policies(
    table: str,
    policies: List[Dict[str, Any]],
    schema: str = "public",
    *,
    cast_target: Optional[str] = None,
) -> None:
    table_ref = f'"{schema}"."{table}"'
    for policy in policies:
        name = policy.get("name")
        definition = (policy.get("definition") or "").strip()
        definition = _normalize_policy_expr(definition, cast_target)
        if definition:
            op.execute(f'CREATE POLICY "{name}" ON {table_ref} {definition}')
            continue
        if not name:
            continue
        permissive = bool(policy.get("permissive", True))
        roles = _parse_roles(policy.get("roles"))
        cmd = (policy.get("cmd") or "").upper()
        qual = _normalize_policy_expr(policy.get("qual"), cast_target)
        with_check = _normalize_policy_expr(policy.get("with_check"), cast_target)

        clauses: List[str] = []
        if permissive:
            clauses.append("AS PERMISSIVE")
        else:
            clauses.append("AS RESTRICTIVE")
        if cmd and cmd != "ALL":
            clauses.append(f"FOR {cmd}")
        if roles:
            role_list = ", ".join(_quote_ident(role) for role in roles)
            clauses.append(f"TO {role_list}")
        if qual:
            clauses.append(f"USING ({qual})")
        if with_check:
            clauses.append(f"WITH CHECK ({with_check})")
        definition = " ".join(clauses)
        op.execute(f'CREATE POLICY "{name}" ON {table_ref} {definition}')


def upgrade() -> None:
    """Upgrade schema."""
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return

    from sqlalchemy import inspect
    from sqlalchemy.dialects import postgresql

    inspector = inspect(bind)
    tables = set(inspector.get_table_names())
    if "users" not in tables:
        return

    conn = bind

    policies_by_table: Dict[str, List[Dict[str, Any]]] = {}
    for table in ("connected_accounts", "users", "mcp_connections"):
        if table in tables:
            policies = _fetch_policies(conn, table)
            policies_by_table[table] = policies
            _drop_policies(table, policies)

    if "connected_accounts" in tables:
        _drop_fk(inspector, "connected_accounts", "users", "user_id")

    mcp_user_fk_dropped = False
    if "mcp_connections" in tables and _table_has_column(inspector, "mcp_connections", "user_id"):
        mcp_user_fk_dropped = _drop_fk(inspector, "mcp_connections", "users", "user_id")

    uuid_regex = r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
    op.execute(
        sa.text(
            f"""
            CREATE OR REPLACE FUNCTION _tb_uuid_normalize(val text)
            RETURNS text
            LANGUAGE plpgsql
            IMMUTABLE
            AS $$
            DECLARE
                v text;
            BEGIN
                IF val IS NULL THEN
                    RETURN NULL;
                END IF;
                IF val ~* '{uuid_regex}' THEN
                    RETURN lower(val);
                END IF;
                v := md5(val);
                RETURN lower(
                    substr(v, 1, 8) || '-' ||
                    substr(v, 9, 4) || '-' ||
                    substr(v, 13, 4) || '-' ||
                    substr(v, 17, 4) || '-' ||
                    substr(v, 21, 12)
                );
            END;
            $$;
            """
        )
    )

    op.execute(
        sa.text(
            f"""
            UPDATE users
            SET id = _tb_uuid_normalize(id)
            WHERE id IS NOT NULL
              AND id !~* '{uuid_regex}'
            """
        )
    )

    if "connected_accounts" in tables:
        op.execute(
            sa.text(
                f"""
                UPDATE connected_accounts
                SET user_id = _tb_uuid_normalize(user_id)
                WHERE user_id IS NOT NULL
                  AND user_id !~* '{uuid_regex}'
                """
            )
        )

    if "mcp_connections" in tables and _table_has_column(inspector, "mcp_connections", "user_id"):
        op.execute(
            sa.text(
                f"""
                UPDATE mcp_connections
                SET user_id = _tb_uuid_normalize(user_id)
                WHERE user_id IS NOT NULL
                  AND user_id !~* '{uuid_regex}'
                """
            )
        )

    if "connected_accounts" in tables:
        op.execute(
            """
            INSERT INTO users (id)
            SELECT DISTINCT user_id
            FROM connected_accounts
            WHERE user_id IS NOT NULL
            ON CONFLICT (id) DO NOTHING
            """
        )
    if "mcp_connections" in tables and _table_has_column(inspector, "mcp_connections", "user_id"):
        op.execute(
            """
            INSERT INTO users (id)
            SELECT DISTINCT user_id
            FROM mcp_connections
            WHERE user_id IS NOT NULL
            ON CONFLICT (id) DO NOTHING
            """
        )

    if "connected_accounts" in tables:
        op.alter_column(
            "connected_accounts",
            "user_id",
            type_=postgresql.UUID(as_uuid=True),
            postgresql_using="user_id::uuid",
        )

    if "mcp_connections" in tables and _table_has_column(inspector, "mcp_connections", "user_id"):
        op.alter_column(
            "mcp_connections",
            "user_id",
            type_=postgresql.UUID(as_uuid=True),
            postgresql_using="user_id::uuid",
        )

    op.alter_column(
        "users",
        "id",
        type_=postgresql.UUID(as_uuid=True),
        postgresql_using="id::uuid",
    )

    if "connected_accounts" in tables:
        op.create_foreign_key(
            "connected_accounts_user_id_fkey",
            "connected_accounts",
            "users",
            ["user_id"],
            ["id"],
            ondelete="cascade",
        )

    if mcp_user_fk_dropped:
        op.create_foreign_key(
            "mcp_connections_user_id_fkey",
            "mcp_connections",
            "users",
            ["user_id"],
            ["id"],
            ondelete="cascade",
        )

    for table, policies in policies_by_table.items():
        _create_policies(table, policies, cast_target="uuid")

    op.execute("DROP FUNCTION IF EXISTS _tb_uuid_normalize(text)")


def downgrade() -> None:
    """Downgrade schema."""
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return

    from sqlalchemy import inspect

    inspector = inspect(bind)
    tables = set(inspector.get_table_names())
    if "users" not in tables:
        return

    conn = bind

    policies_by_table: Dict[str, List[Dict[str, Any]]] = {}
    for table in ("connected_accounts", "users", "mcp_connections"):
        if table in tables:
            policies = _fetch_policies(conn, table)
            policies_by_table[table] = policies
            _drop_policies(table, policies)

    if "connected_accounts" in tables:
        _drop_fk(inspector, "connected_accounts", "users", "user_id")
        op.alter_column(
            "connected_accounts",
            "user_id",
            type_=sa.String(),
            postgresql_using="user_id::text",
        )

    mcp_user_fk_dropped = False
    if "mcp_connections" in tables and _table_has_column(inspector, "mcp_connections", "user_id"):
        mcp_user_fk_dropped = _drop_fk(inspector, "mcp_connections", "users", "user_id")
        op.alter_column(
            "mcp_connections",
            "user_id",
            type_=sa.String(),
            postgresql_using="user_id::text",
        )

    op.alter_column(
        "users",
        "id",
        type_=sa.String(),
        postgresql_using="id::text",
    )

    if "connected_accounts" in tables:
        op.create_foreign_key(
            "connected_accounts_user_id_fkey",
            "connected_accounts",
            "users",
            ["user_id"],
            ["id"],
            ondelete="cascade",
        )

    if mcp_user_fk_dropped:
        op.create_foreign_key(
            "mcp_connections_user_id_fkey",
            "mcp_connections",
            "users",
            ["user_id"],
            ["id"],
            ondelete="cascade",
        )

    for table, policies in policies_by_table.items():
        _create_policies(table, policies, cast_target="text")
