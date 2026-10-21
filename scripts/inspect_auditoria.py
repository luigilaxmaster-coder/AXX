import sys
sys.stdout.reconfigure(encoding='utf-8')

with open('Axx_Integraciones_Auditoria_2026-10-19 (1).md', 'r', encoding='utf-8', errors='ignore') as f:
    for line in f:
        if line.startswith('#'):
            print(line.strip())
