"""Read-only fingerprint of all legacy database columns; contains no secrets."""
import hashlib
import json
from sqlalchemy import text
from app.db.session import engine

with engine.connect() as connection:
    tables = connection.execute(text("SELECT table_name FROM information_schema.tables WHERE table_schema='public' AND table_type='BASE TABLE' AND table_name NOT IN ('alembic_version') ORDER BY table_name")).scalars().all()
    results = {}
    for table in tables:
        columns = connection.execute(text("SELECT column_name FROM information_schema.columns WHERE table_schema='public' AND table_name=:table ORDER BY ordinal_position"), {'table': table}).scalars().all()
        columns = [c for c in columns if c not in ('show_on_terminal',)]
        # Polling a terminal updates only these diagnostic fields.
        if table == 'terminals':
            columns = [c for c in columns if c not in ('last_seen_at','last_ip','last_user_agent','updated_at')]
        quoted = ','.join('"'+c+'"' for c in columns)
        rows = connection.execute(text(f'SELECT row_to_json(t)::text FROM (SELECT {quoted} FROM "{table}") t')).scalars().all()
        results[table] = {'count': len(rows), 'sha256': hashlib.sha256('\n'.join(sorted(rows)).encode()).hexdigest()}
    print(json.dumps(results, indent=2, sort_keys=True))
