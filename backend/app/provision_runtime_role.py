from __future__ import annotations

import os

from psycopg import sql

from app.database import engine


RUNTIME_ROLE = "trace_app"
ADMIN_ROLE = "tcga"


def provision_runtime_role() -> None:
    password = os.environ.get("POSTGRES_RUNTIME_PASSWORD", "")
    if len(password) < 32:
        raise RuntimeError(
            "POSTGRES_RUNTIME_PASSWORD must contain at least 32 characters."
        )

    connection = engine.raw_connection()
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                sql.SQL(
                    "DO $$ BEGIN "
                    "IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = {role}) "
                    "THEN CREATE ROLE {identifier} LOGIN; END IF; "
                    "END $$"
                ).format(
                    role=sql.Literal(RUNTIME_ROLE),
                    identifier=sql.Identifier(RUNTIME_ROLE),
                )
            )
            cursor.execute(
                sql.SQL(
                    "ALTER ROLE {role} WITH LOGIN NOSUPERUSER NOCREATEDB "
                    "NOCREATEROLE NOREPLICATION PASSWORD {password}"
                ).format(
                    role=sql.Identifier(RUNTIME_ROLE),
                    password=sql.Literal(password),
                )
            )
            cursor.execute(
                sql.SQL("GRANT CONNECT ON DATABASE {database} TO {role}").format(
                    database=sql.Identifier("tcga_explorer"),
                    role=sql.Identifier(RUNTIME_ROLE),
                )
            )
            cursor.execute(
                sql.SQL("GRANT USAGE ON SCHEMA public TO {role}").format(
                    role=sql.Identifier(RUNTIME_ROLE)
                )
            )
            cursor.execute(
                sql.SQL(
                    "GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES "
                    "IN SCHEMA public TO {role}"
                ).format(role=sql.Identifier(RUNTIME_ROLE))
            )
            cursor.execute(
                sql.SQL(
                    "GRANT USAGE, SELECT, UPDATE ON ALL SEQUENCES "
                    "IN SCHEMA public TO {role}"
                ).format(role=sql.Identifier(RUNTIME_ROLE))
            )
            cursor.execute(
                sql.SQL(
                    "GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA public TO {role}"
                ).format(role=sql.Identifier(RUNTIME_ROLE))
            )
            for privilege in (
                "SELECT, INSERT, UPDATE, DELETE ON TABLES",
                "USAGE, SELECT, UPDATE ON SEQUENCES",
                "EXECUTE ON FUNCTIONS",
            ):
                cursor.execute(
                    sql.SQL(
                        "ALTER DEFAULT PRIVILEGES FOR ROLE {owner} IN SCHEMA "
                        "public GRANT " + privilege + " TO {role}"
                    ).format(
                        owner=sql.Identifier(ADMIN_ROLE),
                        role=sql.Identifier(RUNTIME_ROLE),
                    )
                )
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


if __name__ == "__main__":
    provision_runtime_role()
