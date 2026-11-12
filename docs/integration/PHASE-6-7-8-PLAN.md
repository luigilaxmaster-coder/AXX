# Integración AXX · Fases 6 + 7 + 8

Estado actual: **INTEGRATED_NOT_READY**. Integración real `4b20abaac2934b96f19ef1ce9320e7fb581bb189`; fuente de la candidata `bb523221b68fc68cdf43caf37dea4051cd59525b`. Ver [informe final](FINAL-INTEGRATION-ACCEPTANCE.md) y PHASE-6-7-8-SOURCES.json para pruebas y bloqueantes físicos.

## Plan histórico previo a la autorización

El texto siguiente conserva el plan inicial de d4a7dff. Sus referencias a PLAN_ONLY y a trabajo sin mezclar describen aquel estado anterior; el informe final documenta la ejecución posterior.

# Plan de integración AXX · Fases 6 + 7 + 8

Estado: **PLAN_ONLY**. Rama propia `codex/axx-phase-6-7-8-integration`, nacida del
cierre aceptado de Fase 7. No contiene un merge de Handy ni afirma aceptación
conjunta. Las ramas originales permanecen independientes. Esta rama se prepara
en el worktree propio de Codex existente, sin otro checkout ni copia de pesos.

## Referencias bloqueadas

| Fuente | SHA completo |
| --- | --- |
| Fase 6, informes y base compartida | `a7503624cbefaa9a125331ef3bdcc3b3afdf0101` |
| Fase 6, código validado | `4f4e18bffb22096b0dec380b29630464e0fc1d09` |
| Fase 7, congelación propia | `9f87f7fcaa1ecb06ec87747c233308d1aa7b8c13` |
| Fase 7, fuente nativa empaquetada | `a1eb51d76978c99185d0dfc43cda7e6f51930b9d` |
| Fase 7, cierre de aceptación y base de esta rama | `d18f8272112b2f3434491497da9add8d6221e539` |
| Fase 8, código Handy | `b5bbaca0590700a5d090520ee544e558c7b34ec2` |
| Fase 8, handoff final | `898df5f48f236b23148d203fc558f9ea0e80c0b1` |

La base común de Fases 7 y 8 es Fase 6: no se debe aplicar dos veces. Fase 7
tiene dictamen **READY_WITH_LIMITATIONS** para la candidata visual; Fase 8
sigue **NOT_READY** para entrega por su aceptación física pendiente. El dictamen
visual no levanta esos bloqueantes de voz.

## Conflictos comprobados sin mezclar ramas

`git merge-tree --write-tree --name-only <cierre-7> <handoff-8>` devolvió 1,
exactamente dos archivos conflictivos. No se modificaron índice ni worktree.
El árbol virtual con marcadores no es código integrado ni candidato compilable.
Salida conservada en `build/phase7/integration-merge-tree.txt` y hasheada en el
recibo final. No se ejecutó `git merge`.

| Archivo | Resolución que debe revisarse e implementar después |
| --- | --- |
| `1.AXX/Axx.html` | Conservar todas las cargas existentes, añadir dictation-engine antes de phase7-ui, mantener phase7-ui como último script. Preservar la clave efectiva de dimensiones del cierre y los rótulos/agrupación de Fase 7. No resolver el tail escogiendo solo un lado. |
| `src-tauri/src/lib.rs` | Unificar phase7_data_path/application_data_path conservando rutas de producción y namespaces com.axx.phase7/com.axx.phase8. Mantener ambos casos de prueba. Conservar módulos/handlers/hooks/captura y cancelación nativos de Fase 8 y el aislamiento de procesos previo. |

## Conflictos semánticos a comprobar

- **DOM y propietarios:** Fase 7 mueve nodos sin clonarlos. Dictado monta su
  details en `voice-panel-controls`; debe existir una sola instancia tras
  navegar/reabrir las cinco pestañas. Conservar IDs, handlers, MutationObservers
  y estados del dueño. No duplicar controles o crear paneles paralelos.
- **Preferencias:** preservar panelPositions sin migraciones destructivas.
  Navegar no guarda tamaños. Fuente/tema/forma pertenecen a sus dueños actuales;
  modelo ASR, idioma, perfil, diccionario y atajo pertenecen al dictado. Elegir
  ASR no cambia proveedor/modelo del chat ni activa el micrófono.
- **Voz:** captura común con lease y confirmación nativa de cierre; dictado,
  comando y conversación conservan comportamientos y permisos separados.
  Dictado inserta texto sin Enter/envío; comandos solo ejecutan acciones
  autorizadas; conversación usa el proveedor elegido y TTS según sus ajustes.
  No recuperar automáticamente un micrófono preemptado ni aceptar generaciones
  antiguas; parada/cancelación conserva pending recuperable sin historial.
- **Atajos/destinos:** mantener reservas y rechazo de colisiones, UIA de campos,
  exclusión de contraseñas/terminales y límites de foco. Nunca convertir un
  timeout o cambio de ventana en inserción automática en un destino nuevo.
- **Dependencias/empaquetado:** conservar transcribe-cpp/transcribe-cpp-sys en las
  versiones exactas probadas por Fase 8 (ambos =0.4.0 compatibles), features
  Windows y Cargo.lock. Verificar ABI real del sidecar, JSON del worker, DLLs,
  licencias e inventario del backend onedir. Pesos/audio/credenciales no son
  recursos distribuibles del instalador. Ambas configs privadas deben coexistir.
- **Modelos por tarea:** mantener Parakeet V3 y Whisper Small seleccionables,
  idioma explícito donde el motor lo soporte y política de cifras por perfil.
  No imponer ganador con tres muestras sintéticas inglesas. Comparar números,
  fechas, cantidades, código y ES/EN/Spanglish con el corpus humano pendiente;
  añadir francés al corpus antes de afirmar aceptación francesa. No transformar
  cifras ambiguas ni significado mediante postproceso LLM implícito.
- **Móvil:** conservar `/v1`, pairing, permisos, borradores y operation IDs.
  No regenerar design-baseline.json para esconder cambios. Android conserva
  versión y firma; una futura entrega de APK tiene su aceptación separada.

## Secuencia de implementación y validación

1. Confirmar SHA/estado de los tres orígenes y respaldos privados. Mantener los
   commits de cierre como referencias; integrar el SHA bloqueado de Fase 8 solo
   en esta rama, resolviendo a mano los dos conflictos revisados arriba.
2. Revisar el diff completo contra Fase 7, no solo los conflictos textuales.
   No introducir funciones adicionales, nuevos proveedores por defecto, cambios
   de versión o cambios del avatar. Ningún archivo personal se importa.
3. Ejecutar contratos DOM y tres ajustes de Fase 7 (29 checks), navegación real
   de cada pestaña, tamaños RAM/localStorage, drag/resize, guardado/descartar,
   contraste y capturas de ambos temas. Repetir desktop 42 con Chromium 1248,
   las 12 suites UI y Magic Pen. Comparar los cinco fallos preexistentes con el
   mismo baseline; todo fallo nuevo se investiga antes de aceptar.
4. Ejecutar pruebas de dictado/captura/cancelación y postproceso de Fase 8,
   Python voz/modelos (baseline 32), Rust (baseline 27 + fixtures Win32), worker
   C++/ABI, backend empaquetado y disponibilidad/preparar/transcribir/liberar
   ambos motores. Añadir el assert combinado de namespace de Fase 7.
5. Ejecutar `python scripts/validate_companion.py --output
   build/companion-validation.json` sobre la fuente integrada final. El recibo
   de Fase 7 no vale para otra fuente: comprobar hashes y conservar los 15 /
   112 (1 omisión previa) / 58 / 8. No sustituye aceptación física de teléfono.
6. Construir otra candidata combinada con identidad/datos/registro propios,
   desde un único SHA limpio. Verificar instalador, host instalado (marcador
   NSIS), backend/worker y assets. Arrancar WebView2 real con IPC y proveedor
   local genuinos; repetir los 11 grupos de aceptación nativa visual y probar
   voz simultáneamente con navegación/persistencia. Mantener separados recibos
   de host simulado, WebView instrumentado y entrada OS/física.
7. Completar micrófono físico, corpus 50+ frases, sesiones de 10 min, carga de
   UI, bloqueo/suspensión, modificadores/hold y matriz de campos/aplicaciones.
   Verificar silencio/inactivo al iniciar y cierre real del micrófono; nunca
   interpretar texto dictado como permiso de acción. Reintentar ratón OS,
   GPU y DPI físicos pendientes de Fase 7; documentar qué hardware se usó.
8. Dictaminar integración con hashes, capturas, logs y regresiones comparadas.
   Mientras falte aceptación física de voz, no declararla READY para entrega.
   No hay autorización de push, main, publicación ni instalación personal.

## Conservación y reversión

Dueño único de cualquier empaquetado/versionado posterior. Usar release.py sync
solo cuando se autorice un cambio de versión; no publicar estos debug 0.22.46.
Revertir una integración fallida en esta rama propia mediante commits, sin
resetear Claude/Handy ni limpiar perfiles. Detener solo PIDs y jobs de candidata.
La desinstalación privada, si se solicita, se dirige únicamente a su producto y
ruta verificados; no se borran modelos ni configuraciones para reparar fallos.

Handoff Handy conservado: `docs/phase-8/*` en el SHA 898df5f y bundle incremental
privado verificado en `build/phase7/recovery/handy-898df5f.bundle`; requiere la
base a750362. Los documentos adjuntos se usaron como propuesta técnica; las
autorizaciones vigentes proceden de las instrucciones explícitas del usuario.
