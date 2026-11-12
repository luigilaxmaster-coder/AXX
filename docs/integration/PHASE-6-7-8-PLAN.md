# Plan de integraciÃ³n AXX Â· Fases 6 + 7 + 8

Estado actual: **INTEGRATED_TESTING**; merge revisado `4b20abaac2934b96f19ef1ce9320e7fb581bb189`. El plan histórico siguiente queda como referencia de las decisiones y pruebas exigidas.

Estado inicial: **PLAN_ONLY**. Rama propia `codex/axx-phase-6-7-8-integration`, nacida del
cierre aceptado de Fase 7. No contiene un merge de Handy ni afirma aceptaciÃ³n
conjunta. Las ramas originales permanecen independientes. Esta rama se prepara
en el worktree propio de Codex existente, sin otro checkout ni copia de pesos.

## Referencias bloqueadas

| Fuente | SHA completo |
| --- | --- |
| Fase 6, informes y base compartida | `a7503624cbefaa9a125331ef3bdcc3b3afdf0101` |
| Fase 6, cÃ³digo validado | `4f4e18bffb22096b0dec380b29630464e0fc1d09` |
| Fase 7, congelaciÃ³n propia | `9f87f7fcaa1ecb06ec87747c233308d1aa7b8c13` |
| Fase 7, fuente nativa empaquetada | `a1eb51d76978c99185d0dfc43cda7e6f51930b9d` |
| Fase 7, cierre de aceptaciÃ³n y base de esta rama | `d18f8272112b2f3434491497da9add8d6221e539` |
| Fase 8, cÃ³digo Handy | `b5bbaca0590700a5d090520ee544e558c7b34ec2` |
| Fase 8, handoff final | `898df5f48f236b23148d203fc558f9ea0e80c0b1` |

La base comÃºn de Fases 7 y 8 es Fase 6: no se debe aplicar dos veces. Fase 7
tiene dictamen **READY_WITH_LIMITATIONS** para la candidata visual; Fase 8
sigue **NOT_READY** para entrega por su aceptaciÃ³n fÃ­sica pendiente. El dictamen
visual no levanta esos bloqueantes de voz.

## Conflictos comprobados sin mezclar ramas

`git merge-tree --write-tree --name-only <cierre-7> <handoff-8>` devolviÃ³ 1,
exactamente dos archivos conflictivos. No se modificaron Ã­ndice ni worktree.
El Ã¡rbol virtual con marcadores no es cÃ³digo integrado ni candidato compilable.
Salida conservada en `build/phase7/integration-merge-tree.txt` y hasheada en el
recibo final. No se ejecutÃ³ `git merge`.

| Archivo | ResoluciÃ³n que debe revisarse e implementar despuÃ©s |
| --- | --- |
| `1.AXX/Axx.html` | Conservar todas las cargas existentes, aÃ±adir dictation-engine antes de phase7-ui, mantener phase7-ui como Ãºltimo script. Preservar la clave efectiva de dimensiones del cierre y los rÃ³tulos/agrupaciÃ³n de Fase 7. No resolver el tail escogiendo solo un lado. |
| `src-tauri/src/lib.rs` | Unificar phase7_data_path/application_data_path conservando rutas de producciÃ³n y namespaces com.axx.phase7/com.axx.phase8. Mantener ambos casos de prueba. Conservar mÃ³dulos/handlers/hooks/captura y cancelaciÃ³n nativos de Fase 8 y el aislamiento de procesos previo. |

## Conflictos semÃ¡nticos a comprobar

- **DOM y propietarios:** Fase 7 mueve nodos sin clonarlos. Dictado monta su
  details en `voice-panel-controls`; debe existir una sola instancia tras
  navegar/reabrir las cinco pestaÃ±as. Conservar IDs, handlers, MutationObservers
  y estados del dueÃ±o. No duplicar controles o crear paneles paralelos.
- **Preferencias:** preservar panelPositions sin migraciones destructivas.
  Navegar no guarda tamaÃ±os. Fuente/tema/forma pertenecen a sus dueÃ±os actuales;
  modelo ASR, idioma, perfil, diccionario y atajo pertenecen al dictado. Elegir
  ASR no cambia proveedor/modelo del chat ni activa el micrÃ³fono.
- **Voz:** captura comÃºn con lease y confirmaciÃ³n nativa de cierre; dictado,
  comando y conversaciÃ³n conservan comportamientos y permisos separados.
  Dictado inserta texto sin Enter/envÃ­o; comandos solo ejecutan acciones
  autorizadas; conversaciÃ³n usa el proveedor elegido y TTS segÃºn sus ajustes.
  No recuperar automÃ¡ticamente un micrÃ³fono preemptado ni aceptar generaciones
  antiguas; parada/cancelaciÃ³n conserva pending recuperable sin historial.
- **Atajos/destinos:** mantener reservas y rechazo de colisiones, UIA de campos,
  exclusiÃ³n de contraseÃ±as/terminales y lÃ­mites de foco. Nunca convertir un
  timeout o cambio de ventana en inserciÃ³n automÃ¡tica en un destino nuevo.
- **Dependencias/empaquetado:** conservar transcribe-cpp/transcribe-cpp-sys en las
  versiones exactas probadas por Fase 8 (ambos =0.4.0 compatibles), features
  Windows y Cargo.lock. Verificar ABI real del sidecar, JSON del worker, DLLs,
  licencias e inventario del backend onedir. Pesos/audio/credenciales no son
  recursos distribuibles del instalador. Ambas configs privadas deben coexistir.
- **Modelos por tarea:** mantener Parakeet V3 y Whisper Small seleccionables,
  idioma explÃ­cito donde el motor lo soporte y polÃ­tica de cifras por perfil.
  No imponer ganador con tres muestras sintÃ©ticas inglesas. Comparar nÃºmeros,
  fechas, cantidades, cÃ³digo y ES/EN/Spanglish con el corpus humano pendiente;
  aÃ±adir francÃ©s al corpus antes de afirmar aceptaciÃ³n francesa. No transformar
  cifras ambiguas ni significado mediante postproceso LLM implÃ­cito.
- **MÃ³vil:** conservar `/v1`, pairing, permisos, borradores y operation IDs.
  No regenerar design-baseline.json para esconder cambios. Android conserva
  versiÃ³n y firma; una futura entrega de APK tiene su aceptaciÃ³n separada.

## Secuencia de implementaciÃ³n y validaciÃ³n

1. Confirmar SHA/estado de los tres orÃ­genes y respaldos privados. Mantener los
   commits de cierre como referencias; integrar el SHA bloqueado de Fase 8 solo
   en esta rama, resolviendo a mano los dos conflictos revisados arriba.
2. Revisar el diff completo contra Fase 7, no solo los conflictos textuales.
   No introducir funciones adicionales, nuevos proveedores por defecto, cambios
   de versiÃ³n o cambios del avatar. NingÃºn archivo personal se importa.
3. Ejecutar contratos DOM y tres ajustes de Fase 7 (29 checks), navegaciÃ³n real
   de cada pestaÃ±a, tamaÃ±os RAM/localStorage, drag/resize, guardado/descartar,
   contraste y capturas de ambos temas. Repetir desktop 42 con Chromium 1248,
   las 12 suites UI y Magic Pen. Comparar los cinco fallos preexistentes con el
   mismo baseline; todo fallo nuevo se investiga antes de aceptar.
4. Ejecutar pruebas de dictado/captura/cancelaciÃ³n y postproceso de Fase 8,
   Python voz/modelos (baseline 32), Rust (baseline 27 + fixtures Win32), worker
   C++/ABI, backend empaquetado y disponibilidad/preparar/transcribir/liberar
   ambos motores. AÃ±adir el assert combinado de namespace de Fase 7.
5. Ejecutar `python scripts/validate_companion.py --output
   build/companion-validation.json` sobre la fuente integrada final. El recibo
   de Fase 7 no vale para otra fuente: comprobar hashes y conservar los 15 /
   112 (1 omisiÃ³n previa) / 58 / 8. No sustituye aceptaciÃ³n fÃ­sica de telÃ©fono.
6. Construir otra candidata combinada con identidad/datos/registro propios,
   desde un Ãºnico SHA limpio. Verificar instalador, host instalado (marcador
   NSIS), backend/worker y assets. Arrancar WebView2 real con IPC y proveedor
   local genuinos; repetir los 11 grupos de aceptaciÃ³n nativa visual y probar
   voz simultÃ¡neamente con navegaciÃ³n/persistencia. Mantener separados recibos
   de host simulado, WebView instrumentado y entrada OS/fÃ­sica.
7. Completar micrÃ³fono fÃ­sico, corpus 50+ frases, sesiones de 10 min, carga de
   UI, bloqueo/suspensiÃ³n, modificadores/hold y matriz de campos/aplicaciones.
   Verificar silencio/inactivo al iniciar y cierre real del micrÃ³fono; nunca
   interpretar texto dictado como permiso de acciÃ³n. Reintentar ratÃ³n OS,
   GPU y DPI fÃ­sicos pendientes de Fase 7; documentar quÃ© hardware se usÃ³.
8. Dictaminar integraciÃ³n con hashes, capturas, logs y regresiones comparadas.
   Mientras falte aceptaciÃ³n fÃ­sica de voz, no declararla READY para entrega.
   No hay autorizaciÃ³n de push, main, publicaciÃ³n ni instalaciÃ³n personal.

## ConservaciÃ³n y reversiÃ³n

DueÃ±o Ãºnico de cualquier empaquetado/versionado posterior. Usar release.py sync
solo cuando se autorice un cambio de versiÃ³n; no publicar estos debug 0.22.46.
Revertir una integraciÃ³n fallida en esta rama propia mediante commits, sin
resetear Claude/Handy ni limpiar perfiles. Detener solo PIDs y jobs de candidata.
La desinstalaciÃ³n privada, si se solicita, se dirige Ãºnicamente a su producto y
ruta verificados; no se borran modelos ni configuraciones para reparar fallos.

Handoff Handy conservado: `docs/phase-8/*` en el SHA 898df5f y bundle incremental
privado verificado en `build/phase7/recovery/handy-898df5f.bundle`; requiere la
base a750362. Los documentos adjuntos se usaron como propuesta tÃ©cnica; las
autorizaciones vigentes proceden de las instrucciones explÃ­citas del usuario.
