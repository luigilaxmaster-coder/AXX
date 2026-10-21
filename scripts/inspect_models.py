import re
import sys

sys.stdout.reconfigure(encoding='utf-8')
with open('1.AXX/Axx.html', 'r', encoding='utf-8', errors='ignore') as f:
    text = f.read()

matches = re.findall(r'id=["\']([^"\']*(?:model|provider|chat|dock|settings)[^"\']*)["\']', text, re.I)
print("Matched IDs in Axx.html:", set(matches))

# Also search for where BrainClient or chat messages or API requests are made
brain_matches = re.findall(r'class\s+BrainClient[^{]*\{.*?\n\}', text, re.DOTALL)
if brain_matches:
    print("Found BrainClient snippet:", brain_matches[0][:500])
else:
    # search for BrainClient references
    refs = [line.strip() for line in text.splitlines() if 'BrainClient' in line or 'chat' in line.lower() and 'fetch' in line.lower()]
    print("Refs to BrainClient or chat fetch:", refs[:10])
