# MySQL Operations Tips

Source: local ISUCON MySQL notes PDF provided by the user.

These are tactics, not default actions. Apply them only when benchmark evidence supports the change.

## Split MySQL To Another Instance

Use only after `docs/resource-scaling-policy.md` says a split is justified.

### App Host

Update the app DB host in the runtime environment file, commonly `/home/isucon/env.sh`.

```diff
- MYSQL_HOST=127.0.0.1
+ MYSQL_HOST=192.168.0.12
  MYSQL_PORT=3306
```

Also confirm DB name, user, and password variables:

```bash
MYSQL_USER=isucon
MYSQL_DBNAME=isucondition
MYSQL_PASS=isucon
```

Use the actual variable names from the target application; ISUCON problems differ.

### DB Host

Allow MySQL to listen on a non-loopback address.

Common config paths:

- `/etc/mysql/mysql.conf.d/mysqld.cnf`
- `/etc/mysql/mariadb.conf.d/50-server.cnf`

Example:

```diff
- bind-address = 127.0.0.1
+ bind-address = 0.0.0.0
```

Prefer a private-network bind address or security-group restriction when possible. Do not expose MySQL publicly.

Create or verify the app user can connect remotely:

```sql
CREATE USER IF NOT EXISTS 'isucon'@'%' IDENTIFIED BY 'isucon';
GRANT ALL PRIVILEGES ON *.* TO 'isucon'@'%' WITH GRANT OPTION;
```

Restart MySQL and verify from the app host:

```bash
mysql -h <db-private-ip> -u isucon -p
```

## Connection Pool Settings

If the app is bottlenecked on connection churn or MySQL has capacity, tune the Go connection pool.

Example:

```go
db.SetConnMaxLifetime(10 * time.Second)
db.SetMaxIdleConns(512)
db.SetMaxOpenConns(512)
```

Match this with MySQL `max_connections`.

```diff
- #max_connections = 100
+ max_connections = 1024
```

Do not blindly raise connection counts. Check MySQL CPU, memory, lock contention, and connection errors during bench.

## Schema And Query Tactics

### Add Derived Columns

When repeated parsing or classification is expensive, add a derived column and backfill it.

```sql
ALTER TABLE target_table ADD COLUMN condition_level VARCHAR(10);

UPDATE target_table
SET condition_level = CASE
  WHEN condition = '...' THEN 'info'
  ELSE 'warning'
END;
```

Keep init SQL and live DB aligned.

### Groupwise Maximum

For "latest row per group" queries, use a join against grouped max values.

```sql
SELECT a1.*
FROM a a1
JOIN (
  SELECT id, MAX(val) AS val
  FROM a
  GROUP BY id
) a2
  ON a1.id = a2.id
 AND a1.val = a2.val;
```

Always validate with `EXPLAIN` and slowlog total time.

### Upsert Patterns

Use `INSERT ... ON DUPLICATE KEY UPDATE` or `REPLACE` only after checking table constraints and side effects.

## Go MySQL Driver Tip

Consider `interpolateParams=true` when prepared statement overhead is visible.

Example DSN option:

```text
interpolateParams=true&collation=utf8mb4_bin
```

Benchmark before and after. Do not keep it only because it looks faster in theory.
