# Candidata de integración local · fase 4

La rama codex/axx-phase-4 incorpora 7eb0f792b5db127b843f3e4b18c047daea8a3481 sobre dfe3d5a27e2830eb7cf1cb3a2aa0707d4e117dc4. Escritorio 0.22.46 con su versión existente. Android conserva 0.2.14 y versionCode 35.

La rama local incluye integración, tests y evidencia de ejecución. El candidato se valida como código y binario de prueba aislado. El instalador y los artefactos de distribución quedan pendientes. Se conservan la instalación activa y el remoto.

El barrido general final aprobó 1664 casos con 14 omisiones y cero fallos o errores. Connect completó 131 casos con una omisión. Las tres mutaciones fueron detectadas y el recibo PC/móvil coincide con el código integrado.

## Estados de entrega

- Autoridad del canal, permisos y recibos. PASS en fixtures HTTP/TLS. Telegram de producción y Android físico quedan en MANUAL_REQUIRED.
- Herramientas de chat. PASS en Chromium, transporte simulado y ejecución real con Ollama. El recibo de telemetría confirmó poscondiciones.
- Recuperación Windows. PASS para caída, reconciliación de tareas, reconexión y segunda caída acotada en la copia de prueba indicada en PHASE4-REGRESSION-RESULTS.md.
- Build de distribución, firma, instalación del paquete y verificación de hash publicado quedan pendientes. El script de build incorpora commit y limpieza de árbol. El de instalación incorpora versión del EXE y hash comprobado.
- Fusión a main, push y publicación requieren autorización separada.

## Reproducción y reversión

Usar el worktree de la rama y los logs de build/phase4. La ruta de compatibilidad es python scripts/validate_companion.py --output build/companion-validation.json. El recibo PASS comprueba hashes de las entradas y su SHA-256 es 0f032c1a1e3524eb5c938dac068a75790866fc0d8ac00a6fc657df002993b15b.

La reversión durante la fase de integración consiste en volver a la rama o worktree anterior. Si se autoriza una entrega posterior, conservar el binario anterior y su evidencia de instalación. La ruta existente genera el respaldo SQLite de migración cuando falta. No usar la reversión para limpiar datos de usuario.
