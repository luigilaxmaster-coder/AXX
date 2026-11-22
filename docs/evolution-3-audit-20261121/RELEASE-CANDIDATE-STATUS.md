Fecha: 2026-11-21. Base: `2f177ea` (PR #6). Rama: `codex/axx-evolution-3-audit-visual-3d-chatgpt`. Mejoras: [Draft PR #7](https://github.com/luigilaxmaster-coder/AXX/pull/7).

# Estado de candidata

**NOT_RELEASE_READY.** [Draft PR #7](https://github.com/luigilaxmaster-coder/AXX/pull/7), apilado sobre PR #6. Implementaciones y límites por fase en AUDIT-ARGON.md; errores abiertos en DEFECT-REGISTER.md.

- Fuente: Windows 0.22.52; Android 0.2.14/code 35, independientes. No se incrementaron versiones porque no se autorizaron instalación/publicación en los documentos de la tarea.
- Compilación nativa debug aislada: ejecutada, 9 vistas capturadas, edición/guardado CRLF con IPC y disco verificados. No equivale a paquete congelado ni a app instalada.
- Rust: 42 pass y 2 ignored. Evolution/integración: 58 pass. Companion: PASS final con validate_receipt y hashes coincidentes; ver REGRESSION-RESULTS.md y cierre del PR.
- GitHub CI: consultar el estado exacto del HEAD del PR y REGRESSION-RESULTS.md; no inferir aprobación a partir de fuentes subidas.
- Pendientes de producto: estudios v2 en UI, agentes/equipos con inferencia por perfil, scheduler/dispatcher de rutinas, LSP/DAP/drivers background, drafts tras cierre, empaquetado de kernel y rendimiento sostenido.
- Pendientes externos: hardware Android/audio/visión/múltiples monitores, SIWC registrado, API autorizada y ChatGPT web/túnel.

## Ejecución de desarrollo

`npm ci --ignore-scripts`, `npm run prepare:renderer`; instalar requisitos existentes y `python -m pip install -r requirements-cad.txt` en el Python seleccionado. Code Studio se abre desde Personalizar AXX/Personalidad y ofrece opt-in local. Las pruebas dirigidas están en REGRESSION-RESULTS.md. El build Windows exige el kernel y prepara Monaco; nunca obtiene código desde CDN en la WebView.

## Rollback

No se modificaron main, worktree de Argon ni instalador habitual: la instalación actual sigue siendo el rollback de aplicación. Para la candidata, cerrar únicamente el PID y ruta registrados en `build/evolution-audit/native-candidate.json`; conservar su perfil aislado y sus artefactos. Deshabilitar flags corta nuevos despachos y permite cleanup. No eliminar tablas, credenciales o pairing. En integración futura, revertir commits revisados en una rama, nunca reset/clean de datos ni de trabajo ajeno. Una vuelta de instalador requiere aceptación y respaldo consistente de DB; no se ensayó aquí una migración binaria final.

Cierre adicional del 22 de noviembre: 21 regresiones dirigidas Core/Pro/UI/HTTP/mutaciones y tres funcionales integradas aprobadas tras D26–D28. El job Evolution incluye ahora 64 tests. Persiste el límite de commit de varios archivos ante crash; no se declara resuelto por el bloqueo de proceso ni por el readback. Matriz del nuevo panel añadida a SCREEN-STUDY-20261029.md. El PR registra CI y paquete de la fuente final sin atribuir resultados de otra revisión.
