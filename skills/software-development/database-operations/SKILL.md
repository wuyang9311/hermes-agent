---
name: database-operations
description: Use when working with SQL databases (SQLite, PostgreSQL, MySQL) — connecting, exploring schema, running safe queries, debugging performance, and performing migrations. Applies whenever a task involves inspecting, querying, or modifying a relational database.
version: 1.0.0
author: Hermes Agent
license: MIT
platforms: [linux, macos, windows]
prerequisites:
  commands: [sqlite3]
  optional_commands: [psql, mysql, pg_dump, mysqldump]
metadata:
  hermes:
    tags: [database, SQL, SQLite, PostgreSQL, MySQL, schema, migration, debugging]
    related_skills: [data-monitoring, systematic-debugging]
---

# Database Operations

Safe, repeatable workflows for working with SQL databases through Hermes's terminal tool. Covers connection discovery, schema exploration, read-only querying, safe mutations, migration patterns, and performance debugging — across SQLite, PostgreSQL, and MySQL.

## Overview

Hermes has raw terminal access, but ad-hoc database work is error-prone: a mistyped `DROP`, an un-backed-up migration, or a query run against the wrong database. This skill provides guardrails:

- **Connect safely** — auto-detect database type and credentials, verify with a health check
- **Explore first** — always inspect schema before touching data
- **Read by default** — queries run read-only unless explicitly acknowledged as writes
- **Backup before mutation** — every DDL or DML change is preceded by a snapshot
- **Verify after** — confirm the change had the intended effect

## When to Use

- Inspecting a project's database schema (tables, columns, indexes, foreign keys)
- Running exploratory `SELECT` queries to understand data shape
- Adding or modifying columns, indexes, or constraints
- Debugging slow queries or connection issues
- Repairing data (correcting values, cleaning orphans)
- Setting up a new database or migration

Do NOT use for:
- NoSQL / document stores (MongoDB, Redis) — different paradigms
- SaaS databases accessed via REST API (use `airtable` or `notion` skills instead)
- Data monitoring / alerting pipelines (use `data-monitoring` skill)

## Connection Discovery

### 1. Auto-Detect the Database

Before running any command, discover what database the project uses. Scan in this order:

```bash
# SQLite: look for .db / .sqlite / .sqlite3 files
find . -maxdepth 3 \( -name "*.db" -o -name "*.sqlite" -o -name "*.sqlite3" \) 2>/dev/null

# PostgreSQL / MySQL: check .env and environment
grep -E '^(DATABASE_URL|PGHOST|PGDATABASE|MYSQL_HOST|DB_)\w*=' .env 2>/dev/null || true
env | grep -E '^(DATABASE_URL|PGHOST|PGDATABASE|MYSQL_HOST)' || true
```

### 2. Verify the Connection

```bash
# SQLite
sqlite3 path/to/db.db "SELECT 1 AS health_check;"

# PostgreSQL (if DATABASE_URL or PG* vars found)
psql "$DATABASE_URL" -c "SELECT 1 AS health_check;" 2>&1
# or
PGPASSWORD="${PGPASSWORD}" psql -h "${PGHOST}" -U "${PGUSER}" -d "${PGDATABASE}" -c "SELECT 1;"

# MySQL
mysql -h "${MYSQL_HOST}" -u "${MYSQL_USER}" -p"${MYSQL_PASSWORD}" -e "SELECT 1 AS health_check;"
```

Always verify the connection before proceeding. If it fails, report the error — don't guess credentials.

## Schema Exploration

### List All Tables with Row Counts

```bash
# SQLite — list tables
sqlite3 path/to/db.db << 'SQL'
SELECT name AS table_name FROM sqlite_master
WHERE type='table' AND name NOT LIKE 'sqlite_%'
ORDER BY name;
SQL

# SQLite — count rows per table (shell loop; one sqlite3 call per table)
for t in $(sqlite3 path/to/db.db "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%';"); do
  echo "$t: $(sqlite3 path/to/db.db "SELECT COUNT(*) FROM \"$t\";")"
done
```

```bash
# PostgreSQL
psql "$DATABASE_URL" -c "\dt"
# Row counts
psql "$DATABASE_URL" -c "
SELECT schemaname, relname, n_live_tup AS estimated_rows
FROM pg_stat_user_tables ORDER BY n_live_tup DESC;"
```

```bash
# MySQL (replace the vars with your actual connection values)
mysql -h "${MYSQL_HOST}" -u "${MYSQL_USER}" -p"${MYSQL_PASSWORD}" "${MYSQL_DATABASE}" \
  -e "SELECT table_name, table_rows FROM information_schema.tables WHERE table_schema='${MYSQL_DATABASE}';"
```

### Inspect a Specific Table

```bash
# SQLite — full DDL
sqlite3 path/to/db.db ".schema --indent users"

# SQLite — column details
sqlite3 path/to/db.db "PRAGMA table_info('users');"

# SQLite — indexes
sqlite3 path/to/db.db "SELECT name, sql FROM sqlite_master WHERE type='index' AND tbl_name='users';"

# PostgreSQL
psql "$DATABASE_URL" -c "\d+ users"

# MySQL (replace vars with actual connection values)
mysql -h "${MYSQL_HOST}" -u "${MYSQL_USER}" -p"${MYSQL_PASSWORD}" "${MYSQL_DATABASE}" \
  -e "SHOW CREATE TABLE users\\G"
mysql -h "${MYSQL_HOST}" -u "${MYSQL_USER}" -p"${MYSQL_PASSWORD}" "${MYSQL_DATABASE}" \
  -e "DESCRIBE users;"
```

### Find Foreign Key Relationships

```bash
# SQLite
sqlite3 path/to/db.db "PRAGMA foreign_key_list('orders');"

# PostgreSQL
psql "$DATABASE_URL" -c "
SELECT conname, conrelid::regclass AS table, a.attname AS column,
       confrelid::regclass AS references, af.attname AS ref_column
FROM pg_constraint c
JOIN pg_attribute a ON a.attnum = ANY(c.conkey) AND a.attrelid = c.conrelid
JOIN pg_attribute af ON af.attnum = ANY(c.confkey) AND af.attrelid = c.confrelid
WHERE contype = 'f';"
```

### Find Which Code References a Table

```bash
# Search project source for table name references
grep -rn '"users"\|:users\|table.*users' --include="*.py" --include="*.go" --include="*.sql" . | head -20
```

## Safe Query Patterns

### Read-Only Queries (Always Safe)

```bash
# SQLite — open in read-only mode (prevents accidental writes)
sqlite3 "file:path/to/db.db?mode=ro" "SELECT * FROM users LIMIT 10;"

# With column headers
sqlite3 -header -column "file:path/to/db.db?mode=ro" "SELECT id, name, email FROM users LIMIT 10;"
```

### Write Operations — 3-Step Safety Protocol

**Step 1: Preview impact.** Use read-only mode to guarantee no accidental writes:

```bash
sqlite3 "file:path/to/db.db?mode=ro" "SELECT COUNT(*) AS rows_affected FROM users WHERE email IS NULL;"
```

**Step 2: Backup.** Snapshot before mutation:

```bash
# SQLite — simple file copy
cp path/to/db.db "path/to/db.db.backup.$(date +%Y%m%d_%H%M%S)"

# PostgreSQL — dump
pg_dump "$DATABASE_URL" > "backup_$(date +%Y%m%d_%H%M%S).sql"

# MySQL — dump
mysqldump -h "$MYSQL_HOST" -u "$MYSQL_USER" -p"$MYSQL_PASSWORD" "$MYSQL_DATABASE" \
  > "backup_$(date +%Y%m%d_%H%M%S).sql"
```

**Step 3: Execute + verify:**

```bash
sqlite3 path/to/db.db "UPDATE users SET email = 'fixed@example.com' WHERE email IS NULL;"
sqlite3 path/to/db.db "SELECT COUNT(*) AS still_null FROM users WHERE email IS NULL;"
# Expected: 0
```

**Never skip the backup step.** The user must explicitly approve skipping it.

> **Transaction safety:** For multi-table writes or multiple ALTER statements, wrap everything in `BEGIN TRANSACTION` / `COMMIT` (or `ROLLBACK` on error). SQLite auto-commits every DML/DDL statement — without an explicit transaction, a failed multi-step operation can leave the database in a partially-updated, inconsistent state.
>
> ```bash
> sqlite3 path/to/db.db << 'SQL'
> BEGIN TRANSACTION;
> UPDATE accounts SET balance = balance - 100 WHERE id = 1;
> UPDATE accounts SET balance = balance + 100 WHERE id = 2;
> -- Verify, then commit
> SELECT 'OK' AS status WHERE (SELECT balance FROM accounts WHERE id = 1) >= 0;
> COMMIT;
> SQL
> ```

## Migration Patterns

### Adding a Column

```bash
# SQLite
sqlite3 path/to/db.db "ALTER TABLE users ADD COLUMN status TEXT NOT NULL DEFAULT 'active';"

# Verify
sqlite3 path/to/db.db "PRAGMA table_info('users');" | grep status
```

### Adding an Index

```bash
# First check if it already exists
sqlite3 path/to/db.db "SELECT name FROM sqlite_master WHERE type='index' AND tbl_name='users' AND name='idx_users_email';"

# Create (only if missing)
sqlite3 path/to/db.db "CREATE INDEX IF NOT EXISTS idx_users_email ON users(email);"

# Verify it's used
sqlite3 path/to/db.db "EXPLAIN QUERY PLAN SELECT * FROM users WHERE email = 'test@test.com';"
```

### Schema Drift Detection

Compare code-defined models with actual database schema:

```bash
# SQLite: dump schema, compare with model definitions
sqlite3 path/to/db.db ".schema" > /tmp/actual_schema.sql
# Then use search_files to find model definitions and compare manually
grep -rn "class User\|CREATE TABLE.*users" --include="*.py" --include="*.go" .
```

## Performance Debugging

### Find Slow Queries (SQLite)

```bash
# Enable timing
sqlite3 path/to/db.db << 'SQL'
.timer on
EXPLAIN QUERY PLAN SELECT * FROM orders WHERE user_id = 42 AND status = 'pending';
SQL
```

### Missing Index Detection

```bash
# SQLite: find queries that would benefit from an index
sqlite3 path/to/db.db << 'SQL'
SELECT * FROM sqlite_master WHERE type='index' AND tbl_name='orders';
-- If a WHERE clause column isn't indexed, suggest creating one
SQL
```

### Connection / Lock Issues

```bash
# SQLite: check for busy/locked state
sqlite3 path/to/db.db "PRAGMA busy_timeout;"
sqlite3 path/to/db.db "PRAGMA journal_mode;"

# PostgreSQL: active connections
psql "$DATABASE_URL" -c "SELECT state, COUNT(*) FROM pg_stat_activity GROUP BY state;"

# PostgreSQL: long-running queries
psql "$DATABASE_URL" -c "
SELECT pid, now() - pg_stat_activity.query_start AS duration, query
FROM pg_stat_activity WHERE state != 'idle' ORDER BY duration DESC LIMIT 5;"
```

## Data Integrity Checks

```bash
# SQLite: run integrity check (may be slow on large DBs)
sqlite3 path/to/db.db "PRAGMA integrity_check;"

# SQLite: faster alternative for large databases
sqlite3 path/to/db.db "PRAGMA quick_check;"

# SQLite: enable foreign keys (often disabled by default in Python)
sqlite3 path/to/db.db "PRAGMA foreign_keys;"

# Find orphan rows (example pattern)
sqlite3 path/to/db.db << 'SQL'
SELECT o.id, o.user_id FROM orders o
LEFT JOIN users u ON o.user_id = u.id
WHERE u.id IS NULL;
SQL
```

## Common Pitfalls

1. **Connecting to the wrong database.** Always verify the path/DATABASE_URL with a `SELECT 1` health check before running queries. In monorepos with multiple databases, be explicit about which one you're targeting.

2. **SQLite foreign keys disabled by default.** Python's `sqlite3` module and many ORMs disable `PRAGMA foreign_keys` by default. Check with `PRAGMA foreign_keys;` before trusting referential integrity.

3. **Running writes without backup.** On SQLite, a `cp` takes milliseconds and can save hours of recovery. Make it a hard rule: backup before any DDL or multi-row DML.

4. **Assuming `information_schema` works on SQLite.** SQLite uses `sqlite_master` and `PRAGMA` statements instead. Don't use MySQL/PG introspection queries on SQLite.

5. **Forgetting WAL mode on SQLite.** SQLite in WAL mode allows concurrent reads during writes. If a project is hitting "database is locked" errors, check `PRAGMA journal_mode;` — it should be `wal`, not `delete`.

6. **Using `SELECT *` on large tables without LIMIT.** Always add `LIMIT 10` (or a manageable number) for exploratory queries. Pipe through `| head -20` as a second defense.

7. **Interpolating shell variables into SQL without quoting.** Use heredocs (`<< 'SQL'`) with single-quoted delimiter to prevent shell expansion, or use `sqlite3 -cmd ".param set"` for parameterized queries.

8. **`PRAGMA integrity_check` on large or corrupt databases.** On a multi-GB database or a DB with corruption, `PRAGMA integrity_check;` can take minutes and may hang the process. Consider `PRAGMA quick_check;` for a faster (but less thorough) alternative, or run integrity checks during off-peak hours.

9. **Missing client tools on macOS.** PostgreSQL (`psql`, `pg_dump`) and MySQL (`mysql`, `mysqldump`) may not be pre-installed on macOS. Install with `brew install libpq mysql-client` and follow brew's `--link` or PATH instructions. SQLite (`sqlite3`) is pre-installed on both macOS and Linux.

## Verification Checklist

- [ ] Database type and connection verified with `SELECT 1`
- [ ] Schema explored before any data modification
- [ ] Backup created before DDL or multi-row DML
- [ ] Write operations previewed with a `SELECT COUNT(*)` first
- [ ] Changes verified with a follow-up query
- [ ] No `SELECT *` without `LIMIT` on large tables
- [ ] Foreign keys enabled (SQLite: `PRAGMA foreign_keys=ON`)
