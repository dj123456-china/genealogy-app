from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import make_url
from sqlalchemy.dialects.mysql import TEXT, TINYTEXT
from sqlalchemy.orm import DeclarativeBase, sessionmaker
import pymysql
from app.core.config import settings


class Base(DeclarativeBase):
    pass


engine = create_engine(settings.database_url, pool_pre_ping=True, pool_recycle=3600, future=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)
_schema_added_columns: dict[int, set[tuple[str, str]]] = {}


def ensure_database() -> None:
    url = make_url(settings.database_url)
    if not url.database or url.drivername != 'mysql+pymysql':
        return
    connection = pymysql.connect(host=url.host or '127.0.0.1', port=url.port or 3306, user=url.username, password=url.password, charset='utf8mb4', autocommit=True)
    try:
        database = '`' + url.database.replace('`', '``') + '`'
        connection.cursor().execute(f'CREATE DATABASE IF NOT EXISTS {database} CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci')
    finally:
        connection.close()


def ensure_schema() -> None:
    """兼容已有 SQLite / MySQL 数据库；仅添加列、回填标识，不重建业务表。"""
    inspector = inspect(engine)
    tables = set(inspector.get_table_names())
    definitions = {
        'users': {
            'phone': 'VARCHAR(11) NULL', 'active_family_id': 'INTEGER NULL',
            'notifications_enabled': 'BOOLEAN NOT NULL DEFAULT 1',
            'system_notifications_enabled': 'BOOLEAN NOT NULL DEFAULT 0',
            'privacy_updated_at': 'DATETIME NULL',
            'sessions_valid_after': 'DATETIME NULL',
        },
        'families': {'revision': 'INTEGER NOT NULL DEFAULT 0', 'personal_owner_id': 'INTEGER NULL'},
        'family_members': {'client_id': "VARCHAR(64) NOT NULL DEFAULT ''", 'death_date': 'VARCHAR(10) NULL',
                           'birth_year': 'INTEGER NULL', 'birth_month': 'INTEGER NULL',
                           'birth_approximate': 'BOOLEAN NOT NULL DEFAULT 0',
                           'history_links': 'TEXT NULL', 'relationship_note': "VARCHAR(500) NOT NULL DEFAULT ''",
                           'parent_roles': "TEXT NOT NULL DEFAULT '[]'" if engine.dialect.name != 'mysql' else 'TEXT NULL'},
        'reminders': {'client_id': "VARCHAR(64) NOT NULL DEFAULT ''", 'calendar': "VARCHAR(16) NOT NULL DEFAULT 'solar'",
                      'lunar_month': 'INTEGER NULL', 'lunar_day': 'INTEGER NULL', 'lunar_leap': 'BOOLEAN NOT NULL DEFAULT 0'},
        'invitations': {'invitee_user_id': 'INTEGER NULL', 'role': "VARCHAR(16) NOT NULL DEFAULT 'EDITOR'", 'expires_at': 'DATETIME NULL'},
        'file_assets': {'storage_path': "VARCHAR(512) NOT NULL DEFAULT ''", 'size_bytes': 'INTEGER NOT NULL DEFAULT 0', 'sha256': "VARCHAR(64) NOT NULL DEFAULT ''"},
        'audit_logs': {'changes': 'TEXT NULL'},
        'notification_records': {'source_fingerprint': 'VARCHAR(64) NULL', 'family_id': 'INTEGER NULL', 'title': "VARCHAR(128) NOT NULL DEFAULT ''",
                                 'body': "TEXT NOT NULL DEFAULT ''" if engine.dialect.name != 'mysql' else 'TEXT NULL',
                                 'due_date': 'VARCHAR(10) NULL', 'dedupe_key': 'VARCHAR(128) NULL',
                                 'read_at': 'DATETIME NULL', 'delivery_error': 'VARCHAR(1000) NULL', 'delivered_at': 'DATETIME NULL',
                                 'push_status': "VARCHAR(32) NOT NULL DEFAULT 'DISABLED'", 'push_attempted_at': 'DATETIME NULL', 'push_error': 'VARCHAR(500) NULL',
                                 'mobile_status': "VARCHAR(32) NOT NULL DEFAULT 'DISABLED'", 'mobile_attempted_at': 'DATETIME NULL', 'mobile_error': 'VARCHAR(500) NULL'},
        'push_subscriptions': {'session_id': 'INTEGER NULL', 'updated_at': 'DATETIME NULL'},
        'user_sessions': {'accepted_terms_version': 'VARCHAR(32) NULL', 'terms_accepted_at': 'DATETIME NULL'},
        'mobile_push_devices': {'session_id': 'INTEGER NULL'},
    }
    statements = []
    # 每张表只读取一次列定义：除了减少生产数据库往返，也兼容迁移测试中的
    # 单次 inspector 快照；后续所有判断均使用同一份快照。
    columns_by_table = {
        table: inspector.get_columns(table)
        for table in definitions
        if table in tables
    }
    known_added = _schema_added_columns.setdefault(id(engine), set())
    family_columns = {c['name'] for c in columns_by_table.get('families', [])}
    personal_added = ('families' in tables and 'owner_id' in family_columns and
                      'personal_owner_id' not in family_columns and
                      ('families', 'personal_owner_id') not in known_added)
    for table, columns in definitions.items():
        if table not in tables:
            continue
        existing = {column['name']: column for column in columns_by_table.get(table, [])}
        if table == 'families' and engine.dialect.name == 'mysql':
            avatar = existing.get('avatar')
            if avatar and type(avatar['type']) in {TEXT, TINYTEXT}:
                statements.append('ALTER TABLE families MODIFY COLUMN avatar MEDIUMTEXT NOT NULL')
            # 没有 owner_id 说明这是极简测试替身/尚未建表快照，不能据此
            # 推断完整业务表并追加一批迁移语句。
            if 'owner_id' not in existing:
                continue
        for name, definition in columns.items():
            if name not in existing:
                statements.append(f'ALTER TABLE {table} ADD COLUMN {name} {definition}')
    with engine.begin() as connection:
        for statement in statements:
            connection.execute(text(statement))
        for table, columns in definitions.items():
            existing = {column['name'] for column in columns_by_table.get(table, [])}
            for name in columns:
                if name not in existing:
                    known_added.add((table, name))
        if 'family_members' in tables:
            # MySQL 旧版本不支持 TEXT 字面量默认值，迁移时显式回填；
            # 后续成员写入由 ORM 的 [] 默认值及业务保存保证。
            connection.execute(text("UPDATE family_members SET parent_roles='[]' WHERE parent_roles IS NULL"))
            connection.execute(text("UPDATE family_members SET history_links='[]' WHERE history_links IS NULL"))
        if personal_added:
            connection.execute(text('UPDATE families SET personal_owner_id=owner_id'))
    migrate_family_ownership()
    with engine.begin() as connection:
        # 老版本没有稳定 ID；按数据库 ID 回填，保留所有成员、提醒和关联资料。
        for table, prefix in [('family_members', 'member'), ('reminders', 'reminder')]:
            if table not in tables:
                continue
            rows = connection.execute(text(f'SELECT id, family_id, client_id FROM {table} ORDER BY id')).mappings().all()
            used = set()
            for row in rows:
                client_id = row['client_id']
                if not client_id or (row['family_id'], client_id) in used:
                    client_id = f'{prefix}-{row["id"]}'
                    while (row['family_id'], client_id) in used:
                        client_id = client_id + '-legacy'
                    connection.execute(text(f'UPDATE {table} SET client_id=:client WHERE id=:id'), {'client': client_id, 'id': row['id']})
                used.add((row['family_id'], client_id))
        if 'family_memberships' in tables:
            connection.execute(text("UPDATE family_memberships SET role='EDITOR' WHERE role='MEMBER'"))
            if 'families' in tables:
                connection.execute(text("UPDATE family_memberships SET role='OWNER' WHERE EXISTS (SELECT 1 FROM families f WHERE f.id=family_memberships.family_id AND f.owner_id=family_memberships.user_id)"))
                connection.execute(text("INSERT INTO family_memberships (family_id,user_id,role) SELECT f.id,f.owner_id,'OWNER' FROM families f WHERE NOT EXISTS (SELECT 1 FROM family_memberships m WHERE m.family_id=f.id AND m.user_id=f.owner_id)"))
        if 'notification_records' in tables:
            connection.execute(text("UPDATE notification_records SET body='' WHERE body IS NULL"))
        if 'push_subscriptions' in tables:
            connection.execute(text('UPDATE push_subscriptions SET updated_at=created_at WHERE updated_at IS NULL'))
    # 索引幂等创建。旧数据中的重复 membership/session 暂保留；先由业务读取兼容，
    # 没有重复时启用数据库唯一约束，不以迁移为由删除历史资料。
    unique_indexes = {
        'families': ('uq_family_personal_owner', ['personal_owner_id']),
        'family_members': ('uq_member_family_client', ['family_id', 'client_id']),
        'reminders': ('uq_reminder_family_client', ['family_id', 'client_id']),
        'family_memberships': ('uq_membership_family_user', ['family_id', 'user_id']),
        'user_sessions': ('uq_user_session_token_hash', ['token_hash']),
        'notification_records': ('uq_notification_dedupe_key', ['dedupe_key']),
        'push_subscriptions': ('uq_push_subscription_endpoint_hash', ['endpoint_hash']),
        'mobile_push_devices': ('uq_mobile_push_device_client_hash', ['client_hash']),
    }
    fresh_inspector = inspect(engine)
    for table, (name, columns) in unique_indexes.items():
        if table not in tables:
            continue
        indexes = fresh_inspector.get_indexes(table)
        constraints = fresh_inspector.get_unique_constraints(table)
        if not isinstance(indexes, (list, tuple)) or not isinstance(constraints, (list, tuple)):
            continue
        if any(index.get('unique') and index.get('column_names') == columns for index in indexes) or any(constraint.get('column_names') == columns for constraint in constraints):
            continue
        column_list = ', '.join(columns)
        with engine.begin() as connection:
            duplicates = connection.execute(text(f'SELECT {column_list} FROM {table} WHERE {columns[-1]} IS NOT NULL GROUP BY {column_list} HAVING COUNT(*) > 1 LIMIT 1')).first()
            if duplicates:
                continue
            connection.execute(text(f'CREATE UNIQUE INDEX {name} ON {table} ({column_list})'))
    index_inspector = inspect(engine)
    for table, column in [('push_subscriptions', 'session_id'), ('mobile_push_devices', 'session_id'),
                          ('notification_records', 'family_id'), ('invitations', 'invitee_user_id')]:
        indexes = index_inspector.get_indexes(table) if table in tables else []
        if not isinstance(indexes, (list, tuple)):
            continue
        if table in tables and not any(index.get('column_names') == [column] for index in indexes):
            with engine.begin() as connection:
                connection.execute(text(f'CREATE INDEX ix_{table}_{column} ON {table} ({column})'))


def migrate_family_ownership():
    """个人谱保持每人一份，允许受让多份共享谱。旧 owner_id 唯一索引不再适用。"""
    inspector = inspect(engine)
    if 'families' not in inspector.get_table_names():
        return
    indexes = inspector.get_indexes('families')
    constraints = inspector.get_unique_constraints('families')
    if not isinstance(indexes, (list, tuple)):
        indexes = []
    if not isinstance(constraints, (list, tuple)):
        constraints = []
    unique_owner = [i for i in indexes if i.get('unique') and i.get('column_names') == ['owner_id']]
    unique_constraints = [i for i in constraints if i.get('column_names') == ['owner_id']]
    if engine.dialect.name == 'mysql':
        names = {i['name'] for i in unique_owner + unique_constraints if i.get('name')}
        with engine.begin() as connection:
            for name in names:
                safe = name.replace('`', '``')
                connection.execute(text(f'ALTER TABLE families DROP INDEX `{safe}`'))
            if names:
                connection.execute(text('CREATE INDEX ix_family_owner_lookup ON families (owner_id)'))
    elif engine.dialect.name == 'sqlite' and (unique_owner or unique_constraints):
        # SQLite 不能删除 UNIQUE 表约束；事务内保留所有列和行，重建这一张无外键的表。
        import re
        with engine.begin() as connection:
            original = connection.execute(text("SELECT sql FROM sqlite_master WHERE type='table' AND name='families'")).scalar_one()
            revised = re.sub(r',?\s*(?:CONSTRAINT\s+\w+\s+)?UNIQUE\s*\(\s*owner_id\s*\)', '', original, flags=re.I)
            revised = revised.replace('CREATE TABLE families', 'CREATE TABLE families_ownership_migration', 1)
            revised = revised.replace('CREATE TABLE "families"', 'CREATE TABLE families_ownership_migration', 1)
            if revised == original:
                raise RuntimeError('无法安全迁移 families 唯一约束')
            saved_indexes = [r[0] for r in connection.execute(text("SELECT sql FROM sqlite_master WHERE type='index' AND tbl_name='families' AND sql IS NOT NULL")) if r[0]]
            connection.execute(text(revised))
            connection.execute(text('INSERT INTO families_ownership_migration SELECT * FROM families'))
            connection.execute(text('DROP TABLE families'))
            connection.execute(text('ALTER TABLE families_ownership_migration RENAME TO families'))
            for sql in saved_indexes:
                if not re.search(r'UNIQUE.*\(\s*owner_id\s*\)', sql, re.I):
                    connection.execute(text(sql))


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
