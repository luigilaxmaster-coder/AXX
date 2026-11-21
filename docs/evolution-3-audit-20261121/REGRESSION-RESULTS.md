# Resultados de regresiÃ³n â€” 2026-11-21

Base auditada: PR #6, `2f177eae1891efb6097f8dd319872745c37e0f51`. Cambios revisables: [Draft PR #7](https://github.com/luigilaxmaster-coder/AXX/pull/7). Los logs/capturas quedan en `build/evolution-audit/`, excluidos de Git. No contienen evidencia pÃºblica sustituible por una afirmaciÃ³n de release.

| VerificaciÃ³n | Resultado observado | LÃ­mite |
|---|---|---|
| Baseline de Evolution | 44 tests originales pasan | No detectaban STEP/MP4 falsos ni controles desconectados |
| Evolution ampliado + integraciÃ³n HTTP | 58 tests pasan | Incluye suite funcional adicional; el job CI enumerado tiene 55 tests |
| CAD/OpenCascade | 4 tests pasan | ReimportaciÃ³n STEP, volÃºmenes, bounds y geometrÃ­a binaria GLB; no UI CAD empaquetada |
| Connect | 135 tests, 1 omitido | No sustituye login/logout/errores reales del servicio |
| Rust | 42 pasan, 2 ignored | `TAURI_CONFIG` de pruebas sin recursos del instalador |
| Magic Pen legacy | 19 casos pasan, ademÃ¡s spatial/technical/explode | Sin hardware del pen/captura |
| Companion | PASS anterior; revalidación final en curso | 15 contratos, 113 backend (1 skip), 58 navegador, 8 selectores; hashes comparados con fuente |
| Monaco con servicio real | PASS tras generar mÃ³dulos `.js` | IPC nativo simulado en navegador, archivos/HTTP/SQLite reales |
| Nativa aislada WebView2 | PASS tras D23 | Fuente debug, 9 capturas, guardado CRLF real; no instalaciÃ³n/frozen backend |
| Inferencia Codex | Respuestas reales, streaming, continuidad tras recrear proveedor, cancelaciÃ³n y cambio solâ†’terra | No se alterÃ³ sesiÃ³n global ni se revocÃ³ acceso |
| Dependencias npm | 0 avisos conocidos | Sanitizer 3.4.18 incluido mediante build fuente; no garantÃ­a de ausencia de fallos desconocidos |

## CI local y remoto

Se estÃ¡ reproduciendo secuencialmente el contenido del workflow `version-consistency.yml`, sin omitir sus regresiones posteriores al fallo inicial. Comandos y resultados individuales: `build/evolution-audit/ci/results.json`. PreparaciÃ³n de dependencias se realizÃ³ previamente en entornos aislados; no se presenta como instalaciÃ³n idÃ©ntica al runner hospedado.

La primera pasada local del paso 22 fallÃ³ porque el redirector del virtualenv Windows tiene PID distinto al proceso Python anfitriÃ³n. La repeticiÃ³n con `AXX_TEST_PYTHON` apuntando a Python instalado mantuvo la aserciÃ³n estricta y aprobÃ³ 21 verificaciones (`ci/22-direct-python.log`, `ci/22-recheck.json`). No se debilitÃ³ el test.

CI remoto de `45e3100`: Author policy aprobado en push y PR. Desktop version consistency fallÃ³ en la carga real de Monaco (`44949881476`, `44949876976`); corregido en D23, pendiente de resultado del nuevo HEAD. El resultado de un commit anterior no acredita el HEAD posterior. Consultar los checks enlazados en el PR para el estado exacto vigente; no se declara todo CI aprobado mientras alguno estÃ© pendiente.

## RepeticiÃ³n dirigida

```powershell
npm ci --ignore-scripts
npm run prepare:renderer
python -m pip install -r requirements-cad.txt
python -m unittest backend.tests.test_code_studio_ui backend.tests.test_evolution_audit_http -v
python -m unittest backend.tests.test_cad_studio backend.tests.test_motion_studio -v
python -m unittest discover -s backend/connect/tests -q
python scripts/validate_companion.py --output build/companion-validation.json
```

Se requieren los otros requisitos existentes del backend y Playwright/Chromium para suites de navegador; el workflow fija sus versiones. La candidata nativa usa identificador y perfil distintos, nunca instalaciÃ³n sobre los datos habituales.

## No comprobado

Installer/frozen backend con kernel CAD, Android fÃ­sico, audio de micrÃ³fono/altavoz, visiÃ³n de proveedor, multi-monitor, carga prolongada/GPU y autenticaciÃ³n nueva/revocada contra servicios externos. Los drivers de UIA/browser/background, estudios v2 y rutinas pendientes se detallan en DEFECT-REGISTER.md. Dictamen: **NOT_RELEASE_READY**.

La revalidación tras actualizar package.json se guarda en `companion-validation-final.json`; la evidencia anterior no debe usarse como recibo de publicación. El cierre final de CI y regresiones se registra también en el cuerpo del PR sin alterar el código ensayado.
