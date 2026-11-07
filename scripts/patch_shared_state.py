from pathlib import Path

p = Path('C:/Users/luigi/Desktop/axx2/backend/mobile/shared_state.py')
s = p.read_text(encoding='utf-8')
target = "db.execute('INSERT INTO shared_messages VALUES(?,?,?,?,?,?,?)',"
replacement = "db.execute('INSERT INTO shared_messages(id, role, text, at, source, status, conversation_id) VALUES(?,?,?,?,?,?,?)',"
assert target in s
s = s.replace(target, replacement)
p.write_text(s, encoding='utf-8')
print("Updated shared_state.py successfully")
