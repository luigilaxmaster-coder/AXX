# 14 — Preservación del código, entrega y rollback

## 14.1 Aislamiento de trabajo

`main` es referencia protegida. Crear branch `feature/axx-evolution-3-phase-XX` desde SHA conocido; antes de modificar, `git status` y detectar cambios de otros worktrees/sesiones. Si usuario tiene modificaciones no committed, preservarlas y no hacer reset/clean/stash automático. Un único integrador coordina cambios en archivos compartidos como `backend/server.py`, el HTML raíz, `AGENTS.md`, metadatos de versión y scripts de release. Scope pequeño por PR.

## 14.2 Compatibilidad y feature flags

Feature flags separados: `agent_profiles_v1`, `team_chat_v1`, `code_studio_v1`, `code_execution_v1`, `computer_background_v1`, `computer_vm_v1`, `magic_scene_v2`, `asset_gate_mcp_v1`, `diorama_v1`, `cad_worker_v1`, `motion_worker_v1`, `openvino_worker_v1`. Defaults OFF salvo aprobaciones por fase. Deshabilitar flag corta nuevas ejecuciones; no mata ciegamente una operación ya despachada. `command_mode` y permisos persistentes siguen siendo autoridad; flag UI no concede privilegios.

Los flags se agregan en configuración canónica existente donde sea viable; no crear tres archivos de prefs divergentes. Documentar renovación de context IDs al cambiar contexto/instrucciones por proveedor.

## 14.3 Backups y secretos

- Backup consistente SQLite con API SQLite backup / checkpoint de WAL adecuado.
- Manifiesto de rutas/volumen/sha256/datos y capacidad de restauración sobre perfil de prueba.
- Export de perfiles, skills y artefactos con cifrado/permiso de usuario; excluir claves y voces.
- No subir DB real, capturas privadas, carpetas de modelos, tokens, sesiones de navegador a GitHub/CI.
- Priorizar restore verificable y procedimientos, no mera existencia de ZIP.

## 14.4 Migration forward y rollback

1. Verificar estado de fuente y DB, versiones y espacio.
2. Backup + restore test del conjunto mínimo.
3. Aplicar migración aditiva con transaction y schema ledger.
4. Ejecutar legacy tests y feature OFF.
5. Encender feature por rollout/local opt-in, medir.
6. En fallo: desactivar feature, terminar nuevos runs, reconciliar operaciones desconocidas; volver a build anterior compatible con DB (sin DROP de tablas ni datos nuevos).
7. Si build antiguo no abre DB, restaurar backup **solo tras preservar los nuevos artefactos y confirmación de usuario**. Revisión de forward recovery cuando es posible.

## 14.5 Publicación Windows/Android

`AGENTS.md` exige: no atribución IA, version sync con `python scripts/release.py sync --version X.Y.Z`, `docs/RELEASING.md`, build, instalador, verificación real, push, hash, GitHub release y validación companion. Android tiene release/versionCode/signing independientes. Evitar «listo» cuando solo se compiló. No cambiar `mobile/design-baseline.json` para hacer pasar un cambio no aprobado. `/v1` y pairing siguen compatibles. Ejecutar `python scripts/validate_companion.py --output build/companion-validation.json` en integración final y asociar el recibo a la fuente que se publica.

## 14.6 Plan de fallo

| Situación | Acción segura | No hacer |
|---|---|---|
| Crash del worker | reconciliar journal/leases, conservar artefactos | repetir comando `unknown` |
| GPU hang | aislar/cerrar renderer nuevo, preservar avatar y voz | reset global de preferencias |
| DB mal migrada | restaurar backup de pruebas, feature OFF, plan restore | DROP datos reales sin autorización |
| Error en nuevo chat agent | deshabilitar UI/feature, chats legacy intactos | migrar conversaciones a otra DB |
| VM insegura/indisponible | deshabilitar modo isolated, reportar blocked | utilizar host foreground silenciosamente |
| API externa en fallo | mantener modelo manual, mostrar error | facturar otro proveedor por fallback no autorizado |
| Licencia de asset problemática | bloquear distribución, mantener referencia y crédito | copiar asset a instalador sin derechos |
| Pruebas instaladas fallan | detener publicación, conservar logs y branch | afirmar publish basándose en CI fuente |

## 14.7 Handoff entre agentes desarrolladores

Antes de ceder tarea, escribir manifest `task_id`, branch/base SHA, files owned, tests run, known diffs, conflicts, flags, rollback y siguiente paso. Un integrador evalúa cambios de otro agente por diff; no sustituye módulos enteros sin revisar. No fusionar resultados concurrentes que modifican la misma línea sin resolución humana/técnica documentada.

## 14.8 Nota de release exacta

Formato: `Implementado` (código), `Verificado` (pruebas), `Instalado` (Windows), `Publicado` (asset hash confirmado), `Pendiente` y `Limitaciones`. Registros de fuentes/proveedores que recibieron datos. No inventar commit/release/entregables ni afirmar certificación de apps no probadas.
