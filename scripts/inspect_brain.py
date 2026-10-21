import re
import sys

sys.stdout.reconfigure(encoding='utf-8')
with open('1.AXX/Axx.html', 'r', encoding='utf-8', errors='ignore') as f:
    text = f.read()

# Find HTML around ai-provider
idx = text.find('id="ai-provider"')
if idx != -1:
    print("=== HTML around ai-provider ===")
    print(text[max(0, idx - 400):min(len(text), idx + 800)])

# Find JS BrainClient full class
match = re.search(r'class\s+BrainClient\s*\{.*?\n    \}', text, re.DOTALL)
if match:
    print("\n=== BrainClient class ===")
    print(match.group(0))
