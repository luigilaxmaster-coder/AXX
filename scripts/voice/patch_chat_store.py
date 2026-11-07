from pathlib import Path

p = Path("backend/chat_store.py")
content = p.read_text(encoding="utf-8")

replacements = [
    (
        "db.execute('INSERT INTO chat_messages VALUES(?,?,?,?) ON CONFLICT(id) DO UPDATE SET payload=excluded.payload'",
        "db.execute('INSERT INTO chat_messages(id, conversation_id, at, payload) VALUES(?,?,?,?) ON CONFLICT(id) DO UPDATE SET payload=excluded.payload'"
    ),
    (
        "db.execute('INSERT OR REPLACE INTO chat_attachments VALUES(?,?,?,?)'",
        "db.execute('INSERT OR REPLACE INTO chat_attachments(conversation_id, name, text, at) VALUES(?,?,?,?)'"
    ),
    (
        "db.execute('INSERT INTO chat_groups VALUES(?,?)'",
        "db.execute('INSERT INTO chat_groups(id, title) VALUES(?,?)'"
    ),
    (
        "db.execute('INSERT INTO chat_context VALUES(?,?,?,?)'",
        "db.execute('INSERT INTO chat_context(id, group_id, text, at) VALUES(?,?,?,?)'"
    ),
    (
        "db.execute(\"INSERT OR REPLACE INTO chat_settings VALUES('agent_profile',?)\"",
        "db.execute(\"INSERT OR REPLACE INTO chat_settings(key, value) VALUES('agent_profile',?)\""
    ),
    (
        "db.execute(\"INSERT OR REPLACE INTO chat_settings VALUES('migration_v4',?)\"",
        "db.execute(\"INSERT OR REPLACE INTO chat_settings(key, value) VALUES('migration_v4',?)\""
    ),
    (
        "db.execute(\"INSERT OR REPLACE INTO chat_settings VALUES('default_mode',?)\"",
        "db.execute(\"INSERT OR REPLACE INTO chat_settings(key, value) VALUES('default_mode',?)\""
    ),
    (
        "db.execute('INSERT OR REPLACE INTO chat_links VALUES(?,?,?,?)'",
        "db.execute('INSERT OR REPLACE INTO chat_links(conversation_id, source_id, title, updated) VALUES(?,?,?,?)'"
    ),
    (
        "db.execute('INSERT INTO chat_link_messages VALUES(?,?,?,?,?)'",
        "db.execute('INSERT INTO chat_link_messages(conversation_id, source_id, message_id, at, payload) VALUES(?,?,?,?,?)'"
    ),
]

for old, new in replacements:
    if old in content:
        content = content.replace(old, new)
        print("Replaced:", old[:40])
    else:
        print("NOT FOUND:", old[:40])

p.write_text(content, encoding="utf-8")
print("Finished patching chat_store.py")
