# Resultados de regresión — 2026-11-21

Base auditada: PR #6, `2f177eae1891efb6097f8dd319872745c37e0f51`. Cambios revisables: [Draft PR #7](https://github.com/luigilaxmaster-coder/AXX/pull/7). Los logs/capturas quedan en `build/evolution-audit/`, excluidos de Git. No contienen evidencia pública sustituible por una afirmación de release.

| Verificación | Resultado observado | Límite |
|---|---|---|
| Baseline de Evolution | 44 tests originales pasan | No detectaban STEP/MP4 falsos ni controles desconectados |
| Evolution ampliado + integración HTTP | 58 tests pasan | Incluye suite funcional adicional; el job CI tiene 56 tests tras agregar D24 |
| CAD/OpenCascade | 4 tests pasan | Reimportación STEP, volúmenes, bounds y geometría binaria GLB; no UI CAD empaquetada |
| Connect | 135 tests, 1 omitido | No sustituye login/logout/errores reales del servicio |
| Rust | 42 pasan, 2 ignored | `TAURI_CONFIG` de pruebas sin recursos del instalador |
| Magic Pen legacy | 19 casos pasan, además spatial/technical/explode | Sin hardware del pen/captura |
| Companion | PASS final, inputs coincidentes | 15 contratos, 113 backend (1 skip), 58 navegador, 8 selectores; hashes comparados con fuente |
| Monaco con servicio real | PASS tras generar módulos `.js` | IPC nativo simulado en navegador, archivos/HTTP/SQLite reales |
| Nativa aislada WebView2 | PASS tras D23 | Fuente debug, 9 capturas, guardado CRLF real; no instalación/frozen backend |
| Inferencia Codex | Respuestas reales, streaming, continuidad tras recrear proveedor, cancelación y cambio sol→terra | No se alteró sesión global ni se revocó acceso |
| Dependencias npm | 0 avisos conocidos | Sanitizer 3.4.18 incluido mediante build fuente; no garantía de ausencia de fallos desconocidos |

## CI local y remoto

Se reprodujo secuencialmente el contenido del workflow `version-consistency.yml`, sin omitir sus regresiones posteriores al fallo inicial: 42 pasos aprobados, un fallo de entorno resuelto en repetición y 5 preparaciones locales. El replay comenzó antes de los dos últimos ajustes; sus pruebas dirigidas se repitieron sobre la fuente corregida. Comandos y resultados individuales: `build/evolution-audit/ci/results.json`. Preparación de dependencias se realizó previamente en entornos aislados; no se presenta como instalación idéntica al runner hospedado.

La primera pasada local del paso 22 falló porque el redirector del virtualenv Windows tiene PID distinto al proceso Python anfitrión. La repetición con `AXX_TEST_PYTHON` apuntando a Python instalado mantuvo la aserción estricta y aprobó 21 verificaciones (`ci/22-direct-python.log`, `ci/22-recheck.json`). No se debilitó el test.

CI remoto de `45e3100`: Author policy aprobado en push y PR. Desktop version consistency falló en la carga real de Monaco (`44949881476`, `44949876976`); corregido en D23, pendiente de resultado del nuevo HEAD. El resultado de un commit anterior no acredita el HEAD posterior. Consultar los checks enlazados en el PR para el estado exacto vigente; no se declara todo CI aprobado mientras alguno esté pendiente.

## Repetición dirigida

```powershell
npm ci --ignore-scripts
npm run prepare:renderer
python -m pip install -r requirements-cad.txt
python -m unittest backend.tests.test_code_studio_ui backend.tests.test_evolution_audit_http -v
python -m unittest backend.tests.test_cad_studio backend.tests.test_motion_studio -v
python -m unittest discover -s backend/connect/tests -q
python scripts/validate_companion.py --output build/companion-validation.json
```

Se requieren los otros requisitos existentes del backend y Playwright/Chromium para suites de navegador; el workflow fija sus versiones. La candidata nativa usa identificador y perfil distintos, nunca instalación sobre los datos habituales.

## No comprobado

Installer/frozen backend con kernel CAD, Android físico, audio de micrófono/altavoz, visión de proveedor, multi-monitor, carga prolongada/GPU y autenticación nueva/revocada contra servicios externos. Los drivers de UIA/browser/background, estudios v2 y rutinas pendientes se detallan en DEFECT-REGISTER.md. Dictamen: **NOT_RELEASE_READY**.

La revalidación tras actualizar package.json se guarda en `companion-validation-final.json`; la evidencia anterior no debe usarse como recibo de publicación. El cierre final de CI y regresiones se registra también en el cuerpo del PR sin alterar el código ensayado.

D24: suite de Core/Pro/UI/HTTP aprobada tras reproducir el bypass Git. Inferencia adicional real: axx_status emitido por gpt-6.1-sol y procesado por ConnectService.dispatch, executor=ready. Companion final terminó con PASS y validate_receipt comprobó todos sus hashes. El cierre remoto se registra en el PR.
