import difflib

with open('reference/Axx_reference_v20.html', 'r', encoding='utf-8', errors='ignore') as f:
    ref_lines = f.readlines()
with open('1.AXX/Axx.html', 'r', encoding='utf-8', errors='ignore') as f:
    curr_lines = f.readlines()

diff = list(difflib.unified_diff(ref_lines, curr_lines, fromfile='ref', tofile='curr', n=2))
print(f"Total diff lines: {len(diff)}")

# Show diff summary of blocks
current_hunk = []
hunks = []
for line in diff:
    if line.startswith('@@'):
        if current_hunk:
            hunks.append(current_hunk)
            current_hunk = []
    current_hunk.append(line)
if current_hunk:
    hunks.append(current_hunk)

print(f"Total hunks: {len(hunks)}")
for i, hunk in enumerate(hunks[:15]):
    header = hunk[0].strip()
    added = sum(1 for l in hunk if l.startswith('+') and not l.startswith('+++'))
    removed = sum(1 for l in hunk if l.startswith('-') and not l.startswith('---'))
    sample = [l.strip() for l in hunk[1:5] if l.startswith('+') or l.startswith('-')][:3]
    print(f"Hunk {i+1}: {header} (+{added}, -{removed}) -> Sample: {sample}")

if len(hunks) > 15:
    print(f"... and {len(hunks) - 15} more hunks.")
