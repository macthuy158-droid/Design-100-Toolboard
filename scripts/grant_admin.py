"""Server-only provisioning: bind admin access to exactly one existing username."""
import argparse
import sqlite3
from datetime import datetime, timezone
from pathlib import Path


def grant(db_path, username, backup_root, superadmin=False):
    db_path = Path(db_path).resolve()
    if not db_path.is_file():
        raise ValueError('Database does not exist')
    username = username.strip()
    if not username:
        raise ValueError('A login username is required')
    with sqlite3.connect(db_path, timeout=20) as conn:
        conn.row_factory = sqlite3.Row
        matches = conn.execute('SELECT id,username,active FROM community_users WHERE username=? COLLATE NOCASE', (username,)).fetchall()
        if len(matches) != 1 or not matches[0]['active']:
            raise ValueError('Exactly one active login username must match; display names are not used')
        stamp = datetime.now(timezone.utc).isoformat()
        backup = Path(backup_root) / datetime.now(timezone.utc).strftime('admin-%Y%m%d-%H%M%S-%f')
        backup.mkdir(parents=True, mode=0o700)
        with sqlite3.connect(backup / 'toolboard.db') as target:
            conn.backup(target)
        conn.execute('BEGIN IMMEDIATE')
        cols = {r['name'] for r in conn.execute('PRAGMA table_info(community_users)')}
        if 'is_admin' not in cols:
            conn.execute('ALTER TABLE community_users ADD COLUMN is_admin INTEGER NOT NULL DEFAULT 0')
        for field in ('is_superadmin','finance_enabled'):
            if field not in cols:
                conn.execute(f'ALTER TABLE community_users ADD COLUMN {field} INTEGER NOT NULL DEFAULT 0')
        conn.execute('''CREATE TABLE IF NOT EXISTS admin_access_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,user_id INTEGER NOT NULL,
            action TEXT NOT NULL,actor TEXT NOT NULL,created_at TEXT NOT NULL)''')
        # Recheck under lock, then use the verified immutable account ID.
        user = conn.execute('SELECT * FROM community_users WHERE id=?', (matches[0]['id'],)).fetchone()
        if not user or not user['active'] or user['username'].lower() != username.lower():
            raise ValueError('Account changed during provisioning')
        if not user['is_admin']:
            conn.execute('UPDATE community_users SET is_admin=1,updated_at=? WHERE id=?', (stamp,user['id']))
            conn.execute('INSERT INTO admin_access_events(user_id,action,actor,created_at) VALUES(?,?,?,?)',
                         (user['id'],'grant','server-cli',stamp))
        if superadmin and not user['is_superadmin']:
            conn.execute('UPDATE community_users SET is_admin=1,is_superadmin=1,updated_at=? WHERE id=?',(stamp,user['id']))
            conn.execute('INSERT INTO admin_access_events(user_id,action,actor,created_at) VALUES(?,?,?,?)',
                         (user['id'],'grant-superadmin','server-cli',stamp))
        return user['id'], user['username'], str(backup)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--database', required=True)
    parser.add_argument('--username', required=True)
    parser.add_argument('--backup-root', default='/var/backups/design100-admin')
    parser.add_argument('--superadmin', action='store_true', help='Provision an explicitly named primary administrator')
    args = parser.parse_args()
    try:
        uid, username, backup = grant(args.database,args.username,args.backup_root,args.superadmin)
    except (ValueError,sqlite3.Error) as error:
        parser.exit(1, 'ADMIN_BIND_FAILED: ' + str(error) + '\n')
    print('ADMIN_BOUND user_id=' + str(uid) + ' username=' + username)
    print('BACKUP=' + backup)
    if args.superadmin:
        print('SUPERADMIN_BOUND')
