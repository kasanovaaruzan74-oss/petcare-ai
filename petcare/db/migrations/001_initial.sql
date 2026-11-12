BEGIN IMMEDIATE;
CREATE TABLE IF NOT EXISTS owners (
 id INTEGER PRIMARY KEY, name TEXT NOT NULL, email TEXT NOT NULL UNIQUE,
 salt BLOB NOT NULL, password_hash BLOB NOT NULL,
 demo_installed INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS sessions (
 token_hash BLOB PRIMARY KEY, owner_id INTEGER NOT NULL REFERENCES owners(id) ON DELETE CASCADE,
 expires_at INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS password_resets (
 owner_id INTEGER PRIMARY KEY REFERENCES owners(id) ON DELETE CASCADE,
 salt BLOB NOT NULL, code_hash BLOB NOT NULL, expires_at INTEGER NOT NULL,
 attempts INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS pets (
 id INTEGER PRIMARY KEY, owner_id INTEGER NOT NULL REFERENCES owners(id) ON DELETE CASCADE,
 name TEXT NOT NULL, species TEXT NOT NULL, breed TEXT NOT NULL DEFAULT '',
 birth_date TEXT NOT NULL, sex TEXT NOT NULL, weight_kg REAL NOT NULL CHECK(weight_kg > 0),
 photo_path TEXT NOT NULL DEFAULT '', notes TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS pets_owner ON pets(owner_id);
CREATE TABLE IF NOT EXISTS care_tasks (
 id INTEGER PRIMARY KEY, pet_id INTEGER NOT NULL REFERENCES pets(id) ON DELETE CASCADE,
 task_type TEXT NOT NULL, title TEXT NOT NULL, scheduled_at TEXT NOT NULL,
 status TEXT NOT NULL DEFAULT 'planned' CHECK(status IN ('planned','done'))
);
CREATE INDEX IF NOT EXISTS tasks_pet_time ON care_tasks(pet_id,scheduled_at);
CREATE TABLE IF NOT EXISTS events (
 id INTEGER PRIMARY KEY, owner_id INTEGER NOT NULL REFERENCES owners(id) ON DELETE CASCADE,
 created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now')),
 action TEXT NOT NULL, detail TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS events_owner ON events(owner_id,id);
PRAGMA user_version=1;
COMMIT;

