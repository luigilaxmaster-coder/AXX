import sys
sys.stdout.reconfigure(encoding='utf-8')

with open('Axx_Integraciones_Auditoria_2026-10-19 (1).md', 'r', encoding='utf-8', errors='ignore') as f:
    text = f.read()

idx = text.find('### Proveedores de modelos')
if idx != -1:
    print(text[idx:idx+2500])
