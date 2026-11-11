# Gate final de release

Código candidato: `b99d8bd4855e3d516bdcdc4653a4eba314b0dd63`. Rama local: `codex/axx-phase-5`. Fecha: 10 de noviembre de 2026, America/Santo_Domingo. Evidencia privada en `build/phase5/`; no se publica con los informes.

**Recomendación: NOT_READY.** Hay un fallo reproducible del producto en el cambio de grupo/contexto, aceptación fallida de prompts de herramientas en el compositor y pruebas obligatorias pendientes. Los paquetes sirven para aceptación controlada; no acreditan producción aprobada.

## Integridad de la integración

Se leyeron los cinco informes: PHASE4-INTEGRATION-REPORT.md, PHASE4-MODEL-TOOLS-TESTS.md, PHASE4-REGRESSION-RESULTS.md, PHASE4-RELEASE-CANDIDATE.md y PHASE4-SECURITY-VALIDATION.md. En conjunto acreditan integración y pruebas acotadas, con teléfono, Telegram completo, voz física y distribución pendientes. El PASS anterior de herramientas no equivalía a probar todas las capacidades por chat.

`7eb0f792b5db127b843f3e4b18c047daea8a3481..f3443e7d6fbcdfaaa860709ebdec7cc09a79dbec` cambia **solamente esos cinco informes**: ningún archivo de código. El árbol estaba limpio al comenzar. Se creó la rama local de Fase 5 sin merge a main ni push.

La candidata se construyó desde `b99d8bd4855e3d516bdcdc4653a4eba314b0dd63`, árbol limpio al build. Frente a la Fase 4 se cambiaron: el namespace nativo derivado del identificador Tauri (con prueba real de mutex), el manejo de errores al capturar memoria en Capability Workshop y dos fixtures de navegador/UI. No hay cambio en el runtime Python. Se repitieron Rust y los tests de las partes modificadas, el gate móvil y la aceptación empaquetada. Los 1664 casos del barrido general anterior pertenecen a 7eb0f79: se conserva su procedencia y no se reetiquetan como una ejecución nueva en b99d8bd.

`package-validation.json` verificó los 273 hashes de entrada del build contra la fuente congelada y los 2095 archivos del backend instalado. Los recursos de los APK coinciden con los generados actuales. Los informes se entregan en un commit documental posterior: no cambian el código candidato. El cierre registra HEAD, diff documental y árbol limpio en `integrity-final.json`.

## Gate por entorno y capacidad

PASS significa únicamente la comprobación indicada; FAIL es una falla observada; BLOCKED falta dependencia/configuración; MANUAL_REQUIRED necesita aceptación física/autorización específica; NOT_TESTED no se ejecutó. La matriz detallada por cada ID/canal está en FINAL-CAPABILITY-MATRIX.md; sus rutas registradas no son pruebas E2E.

| Capacidad / entorno | Estado | Evidencia / duración | Pendiente para aprobar |
|---|---|---|---|
| Integridad de fuente y build Windows x64 | PASS | windows-final/build-result.json; 22:52:56–23:03:16, unos 620 s | Nuevo build si cambia código/versión |
| Rust / objetos Windows / lifecycle | PASS | rust-isolation.log; 21 PASS, 1 helper ignorado; 0.74 s | El helper no es una capacidad omitida adicional del barrido Python |
| Gate PC/Android /v1 | PASS | companion-validation.json; 15 contratos/21.597 s, 112 backend/47.132 s (1 omitida), 58 navegador/382.609 s, 8 selector/23.884 s | Validación física independiente |
| Doce opt-in antes omitidos | PASS | Native 20/57.211 s, browser inicial + correcciones 10/20.346 s | Alcance fixture/dependencia, no todos los canales |
| Dos fixtures con symlink físico | BLOCKED | Tabla individual inferior | Windows con permiso de crear symlinks/reparse fixtures |
| Windows instalado en paralelo / frontend / backend / cierre | PASS | windows-native.json, lifecycle, environment-final.json | Paquete estándar en Windows limpio |
| Chat con modelo / endpoint estructurado / MCP | PASS | real-model-native.json; 3 intentos/22.990 s; mcp-native.json/4.516 s | Calidad y uso desde compositor siguen separados |
| Compositor natural → herramienta | FAIL | windows-native.json; sin recibo, waiting_capacity/planificador | Aislar resolver/planificador y repetir frase→modelo→efecto real |
| Calidad conversacional del modelo 1b | FAIL | Saludo poco pertinente; REAL-MODEL-VALIDATION.md | Modelo/perfil aceptado y prueba de calidad |
| Grupo / contexto / borradores | FAIL | group-native.json; group_id persistido, UI anterior y HTTP 400; 2.790 s | Adoptar contexto nuevo antes de flush, regresión con datos preservados |
| Permisos, escritura y cancelación local | PASS | windows-native.json; archivo real + ausencia tras cancelación | No implica permiso remoto |
| UIA y aplicación propia | PASS | unified/installed-unified.json | Invoke conserva unknown; no elevar a efecto confirmado |
| Magic Pen captura y vídeo físico | PASS | capture-native.json, 10.999 s; vídeo 3.109 s/41 frames | Inferencia visual separada |
| Magic Pen visión / generación 2D/3D | BLOCKED | Sin perfil visual configurado | Proveedor/modelo autorizado y aceptación completa |
| Apariencia/avatar/materiales/tentáculos/paneles | PASS | appearance/, tentacles/, windows-native.json | No prueba todas las combinaciones de dispositivo/tema |
| Configuración, memoria, modelo y borrador tras reinstall | PASS | distribution-lifecycle.json y reinstalled-native.json; 15.197 s de comprobación final | Migración entre versiones distintas |
| ASR y TTS de fixture | PASS | SAPI sintético → ASR real, WAV privado | Micrófono/escucha acústica humanos |
| Voz física y otros dispositivos de audio | MANUAL_REQUIRED | No se grabó al usuario | Hardware/modelos/permiso y aceptación humana |
| Telegram contratos | PASS | telegram-contracts.log; 98 pruebas/28.495 s | No son tráfico E2E remoto |
| Telegram saliente real del bot | PASS | telegram-real.json, message_id 76 | No acredita entrada/respuesta de candidata |
| Telegram identidad entrante, permisos/ambiguos, reconexión, cancelación | MANUAL_REQUIRED | Cuenta/worker independiente pendientes | Preparación descrita en TELEGRAM-ANDROID-ACCEPTANCE.md |
| Telegram llamadas/archivos | BLOCKED | No aceptación completa acreditada | Implementación/contrato/aceptación antes de anunciarlas |
| Android construcción, firma debug, assets | PASS | android-final-build.log, android-signature.txt, package-validation.json | Debug no es firma de release |
| Android físico: instalación/upgrade/emparejamiento/mensajes/recibos/archivos | MANUAL_REQUIRED | Cero teléfonos ADB autorizados | Teléfono y firma/identidad correctas |
| Android release firmada | BLOCKED | APK release UNSIGNED, code35 | Firma del propietario y avance de code para release nueva |
| Instalador paralelo: actualizar/desinstalar/reinstalar | PASS | distribution-lifecycle.json; 13.922/2.531/11.422 s | No acredita corte eléctrico ni otra versión |
| Instalador estándar limpio, SmartScreen/WebView2 ausente | NOT_TESTED | No se toca instalación actual | VM/equipo Windows aislado |
| Rendimiento observado | PASS | resources-native.json; RSS hasta 2.39 GiB; rAF 49.63 FPS/10 s | Sólo medición corta, sin presupuesto aprobado |
| Estrés prolongado / GPU / batería / fugas | NOT_TESTED | Sin medición suficiente | Ensayo sostenido en hardware objetivo |

## Las 14 pruebas omitidas en el barrido de Fase 4

El log original terminó con 1664 casos, 14 skipped, cero fallos/errores, 1887.476 s. Los motivos pertenecen al entorno/opt-in de esa ejecución. En esta fase se ejecutaron realmente doce y continúan bloqueadas dos. El opt-in no se convierte automáticamente en PASS por habilitar una variable: cada caso debe aparecer aprobado en sus logs.

| # | Prueba | Motivo original | Estado Fase 5 | Evidencia / motivo actual |
|---|---|---|---|---|
| 1 | `test_application_catalog_ui.ApplicationCatalogUiTests.test_menu_filter_guides_and_exact_command_preparation` | requires isolated native Edge | PASS | previously-skipped-browser.log; caso individual aprobado con Edge real (el conjunto inicial tuvo dos incidencias corregidas) |
| 2 | `test_blender_scene.BlenderSceneTests.test_real_copy_transform_render_and_original_preserved` | Opt-in installed Blender | PASS | previously-skipped-native.log; dependencias reales, fixtures propios; 20 casos/57.211 s |
| 3 | `test_browser_bridge.PreparedBrowserNativeTests.test_real_isolated_browser_observation_navigation_and_redirect` | Opt-in isolated real browser fixture | PASS | browser-corrections.log; 10 casos/20.346 s tras correcciones de UI/fixture |
| 4 | `test_browser_download.BrowserDownloadContracts.test_native_download_identity_and_no_overwrite` | requires explicitly enabled isolated native Edge test | PASS | previously-skipped-browser.log; caso individual aprobado con Edge real (el conjunto inicial tuvo dos incidencias corregidas) |
| 5 | `test_capability_workshop_ui.CapabilityWorkshopUiTests.test_open_commands_retries_startup_failure_and_propose_still_generates_once` | requires isolated native Edge | PASS | browser-corrections.log; 10 casos/20.346 s tras correcciones de UI/fixture |
| 6 | `test_capability_workshop_ui.CapabilityWorkshopUiTests.test_real_review_revision_activation_calculation_and_revocation_through_ui` | requires isolated native Edge | PASS | browser-corrections.log; 10 casos/20.346 s tras correcciones de UI/fixture |
| 7 | `test_desktop_ocr_native.DesktopOcrNativeTests.test_observed_window_capture_to_local_ocr` | Opt-in visible owned OCR fixture | PASS | previously-skipped-native.log; dependencias reales, fixtures propios; 20 casos/57.211 s |
| 8 | `test_file_workflows.FileWorkflowsTests.test_actual_link_is_excluded_from_search_and_rejected_by_copy` | La cuenta Windows no puede crear el fixture de enlace simbólico. Mantener pendiente la prueba física de reparse points con ese privilegio. | BLOCKED | Windows deniega crear enlace simbólico (WinError 1314); falta privilegio del fixture; no se cambia la política del equipo |
| 9 | `test_goal_criteria.GoalCriteriaTests.test_linked_paths_are_rejected_without_following_them` | La cuenta Windows no puede crear el fixture de enlace simbólico. Mantener pendiente la prueba física de reparse points con ese privilegio. | BLOCKED | Windows deniega crear enlace simbólico (WinError 1314); falta privilegio del fixture; no se cambia la política del equipo |
| 10 | `test_local_ocr.LocalOcrTests.test_latin_model_preserves_spanish_numbers_units_and_negation` | requires private verified OCR models | PASS | previously-skipped-native.log; dependencias reales, fixtures propios; 20 casos/57.211 s |
| 11 | `test_mcp_ui.McpUiTests.test_existing_dock_entry_configuration_and_untrusted_catalog` | requires isolated native Edge | PASS | previously-skipped-browser.log; caso individual aprobado con Edge real (el conjunto inicial tuvo dos incidencias corregidas) |
| 12 | `test_office_workflows.OfficeWorkflowTests.test_native_excel_reopen_and_independent_verification` | Opt-in real private Excel instance | PASS | previously-skipped-native.log; dependencias reales, fixtures propios; 20 casos/57.211 s |
| 13 | `test_office_workflows.WordWorkflowTests.test_native_word_reopen_pdf_and_existing_instance_preservation` | Opt-in real private Word instance | PASS | previously-skipped-native.log; dependencias reales, fixtures propios; 20 casos/57.211 s |
| 14 | `test_powerpoint_workflow.PowerPointTests.test_native_copy_reopen_pdf_and_original_preservation` | Opt-in real private PowerPoint | PASS | previously-skipped-native.log; dependencias reales, fixtures propios; 20 casos/57.211 s |

Las pruebas Blender/Office/OCR usaron instancias/archivos propios y modelos verificados disponibles. Sus rutas de evidencia históricas se redirigieron a `native-fixtures/` para no sobrescribir recibos anteriores. Las variables de opt-in no se configuraron globalmente.

## Incidencias conservadas y cierre

El primer gate móvil falló una vez al contar renovaciones de control bajo carga. La prueba aislada pasó (48.022 s) y el gate completo posterior pasó sin cambiar código ni expectativas. Se conservan companion-validation-first.json/.log y control-failure-retry.log. Es evidencia de sensibilidad temporal del fixture; no se borra el resultado fallido.

La primera tanda browser tuvo un fallo del manejo de memoria al arrancar el workshop y un error al limpiar descendientes Edge. Se corrigieron el límite de error compartido y los fixtures con el process manager existente; diez casos posteriores pasaron. La fuente candidata incluye esas correcciones. No se introduce otro ejecutor.

El primer intento de recuperación tras el fixture de grupos encontró la UI con contexto eliminado/antiguo. Se recargó el perfil para una preparación válida y se ejecutó la recuperación real con backend y procesos propios; el recibo final PASS está separado de native-recovery-fixture-first.json. Esto no corrige ni oculta la falla de grupos: se reprodujo luego desde el botón real y bloquea este gate.

El namespace inicial mal escapado y la primera compilación con fuente cambiante no se aceptaron. Los paquetes descartados están separados de packages/. Sólo las huellas enumeradas en PACKAGING-VALIDATION.md son candidatas de esta fase.

Para abrir release: corregir grupo/contexto sin relajar aislamiento de memoria; cerrar la aceptación del compositor con herramientas y modelo adecuado; configurar/probar visión y 2D/3D; completar voz física, Telegram candidato y Android físico; usar firma/versiones de release apropiadas y probar el instalador estándar en Windows limpio. Si se cambia código o versión, reconstruir y repetir gates que cubran esos cambios sobre el commit nuevo.

No se realizó merge, push, publicación, instalación sobre el Axx actual ni actualización de credenciales. La ausencia de esos pasos es deliberada. Este trabajo completa la preparación/evaluación de Fase 5; **no concede autorización de producción**.
