# External primary database

BSS Time Collection uses SQLAlchemy and PostgreSQL through `DATABASE_URL`. The default Docker Compose deployment uses the local `db` service, but production can point the API, worker and Alembic migrations to a managed external PostgreSQL service without changing application code.

Administration > Database displays the active database endpoint without exposing its password. When `DATABASE_ADMIN_TEST_ENABLED=true`, administrators on a trusted network can validate host, port, database, username, password and PostgreSQL SSL mode. Submitted credentials are used only for the connection test and are not persisted by the application.

The application deliberately does not switch its primary database live from the browser. The primary database is bootstrap infrastructure: credentials must remain outside the application database and a switch requires schema migration, controlled restart and rollback planning.

Production change procedure:

1. Back up the current database.
2. Create the target PostgreSQL database and least-privilege application account.
3. Validate network/TLS connectivity from Administration or from the deployment host.
4. Set `DATABASE_URL` in the deployment secret/environment.
5. Run `alembic upgrade head` against the target database.
6. Migrate application data if this is a move rather than a new installation.
7. Restart/redeploy API and worker and verify readiness, event capture and worker state.
8. Keep the previous database and configuration available for rollback until validation is complete.

`DATABASE_ADMIN_TEST_ENABLED` defaults to `false` because the current administration interface does not yet provide authentication. Enable it only on a trusted administration network.

Microsoft SQL Server is not currently supported as a production primary database. The current schema, migrations and driver stack are validated for PostgreSQL. SQL Server should be added as a separate compatibility block rather than treated as a connection-string-only change.

This administration feature is diagnostic and deployment-oriented; it never persists database passwords or performs a live database cutover.
