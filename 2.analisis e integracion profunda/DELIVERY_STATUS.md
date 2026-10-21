# Entrega Axx residente Windows 0.20.4

Estado: **Instalado con funciones pendientes**. Instalación NSIS final completada, registro y ambos accesos directos verificados, EXE instalado y backend privado iniciados. El movimiento ya está activo y observado en la copia instalada: se desmarcó «Movimiento reducido» mediante la UI de Axx, se cerraron sus paneles, Windows confirmó desplazamiento físico y dos observaciones posteriores mostraron cuerpo animado y posición diferente. Axx permanece abierto.

## Instalación real

- Ejecutable: `C:\Users\luigi\AppData\Local\Programs\Axx\Axx.exe`. PID verificado al iniciar: 25976.
- Instalador publicado: [Axx_0.20.4_x64-setup.exe](<C:/Users/luigi/Desktop/Axx assistant/dist/windows/Axx_0.20.4_x64-setup.exe>), 242,454,418 bytes, SHA256 `AC6FE03FD25323F6C03227E31CA9FBB7E313C653B41E0DB52D4A3C653BD28BC8`.
- EXE instalado SHA256 `2670d8cfbaf8567c57d669b0c238b7086dbc25410086d876e0821982dc0a8d20`. Se admite exclusivamente la transformación de3bytes del marcador Tauri UNK→NSS respecto a la release; no se toleran otros cambios binarios.
- El arranque final utilizó EXE instalado, cwd instalado, UseShellExecute=false, PATH limitado a Windows y sin PYTHONPATH/PYTHONHOME/VIRTUAL_ENV. Los accesos Desktop y menú Inicio apuntan al EXE y no llevan argumentos; el acceso Desktop ya lanzó la versión0.20.3 en la comprobación anterior.
- Servicio propio descendiente del host, puerto loopback privado, identidad UUID y autenticación confirmadas por el host. Una petición sin token devolvió401. No se publica el token en el diagnóstico.
- Evidencia: [archivos](<C:/Users/luigi/Desktop/Axx assistant/evidence/resident-20261019/installed-files.json>), [arranque instalado](<C:/Users/luigi/Desktop/Axx assistant/evidence/resident-20261019/installed-runtime.json>), [diagnóstico nativo inicial](<C:/Users/luigi/Desktop/Axx assistant/evidence/resident-20261019/installed-native-runtime.json>), [recibo de build](<C:/Users/luigi/Desktop/Axx assistant/evidence/resident-20261019/build-result.json>).

## Movimiento y superficie residente

Respiración, balanceo, inclinación y atención amortiguada al cursor se aplican a la proyección del cuerpo, sin sustituir su material/cámara ni la identidad `axx-studio-v2`. Se conservan24formas y9paletas. El desplazamiento nativo usa tiempo real, velocidad limitada y objetivo de paseo dentro de64pxCSS del centro temporal. Se pausa con paneles, escritura, arrastre, trabajo propio y voz; pausa20s tras arrastre; pin y movimiento reducido. Esc desactiva el paseo. Un clamp al abrir paneles puede desplazar el cuerpo respecto al centro temporal; al reanudarse regresa suavemente, siempre dentro del área de trabajo.

Observación de la instalada: cuerpo líquido visible sobre otras aplicaciones, transparencia real y herramientas compactas que abren. No se grabó video, por instrucción del usuario. Los controles se observaron mediante Computer Use; cambios de foco/entrada y el click-through del punto anterior bloquearon algunos intentos de interacción.

Estado final: `reducedMotion:false`, `roam:true`, `pinned:false`, `mode:roam`; `automaticSteps:1` y `roamSteps:1` certifican el primer cambio físico observado por el host. El diagnóstico se escribe al primer paso y cambios de modo, no cada frame; esos contadores persistidos no son el total en vivo. Dos lecturas posteriores de Computer Use mostraron origen `(3366,505)` y `(3301,483)`, ambas ventana304×304, sin entradas intermedias y con deformación visible. El ancla manual permaneció `(3488.798625,663)` en el primer paso. [Movimiento instalado](<C:/Users/luigi/Desktop/Axx assistant/evidence/resident-20261019/MOVIMIENTO_INSTALADO.md>), [diagnóstico después](<C:/Users/luigi/Desktop/Axx assistant/evidence/resident-20261019/installed-motion-after-enable.json>).

La causa previa fue `settings.reducedMotion:true` de Axx; `studio.living` ya era true y staticMode false. Se cambió únicamente la preferencia interna mediante sus controles, sin editar la base de datos directamente ni los ajustes de animación de Windows. Ruta de ajustes: Herramientas → Todas las herramientas → buscar «datos» → Datos y sistema. Esc detiene el paseo; la sección «Movimiento de Axx» permite reactivarlo o fijar la posición.

## Verificaciones y límites

| Comprobación | Resultado y alcance |
|---|---|
| Backend congelado |45/45 pruebas; sidecar real8/8: ai-memory/MCP y reinicio, receta con segundo artefacto, Blender, SAPI, ASR local y error tipado sin credenciales. Backend sin cambios en0.20.4: `8312CE40F16DB6B024CF2A8BAC1268B0AE15F867E089002138E1F16884D909AC`. |
| Frontend0.20.4 |Barrido24formas aprobado con renderer final;19/19 contratos restantes después. Fixtures IPC, no hardware. [Informe](<C:/Users/luigi/Desktop/Axx assistant/evidence/resident-20261019/FRONTEND_LIVENESS.md>). |
| Nativo0.20.4 |cargo check correcto;15 pruebas aprobadas,0fallos,1helper interno ignorado. Auditoría del contexto Tauri: HTML/voz descomprimidos coinciden byte a byte y SHA con fuentes finales. [Log](<C:/Users/luigi/Desktop/Axx assistant/evidence/resident-20261019/0.20.4-native-tests.log>), [assets](<C:/Users/luigi/Desktop/Axx assistant/evidence/resident-20261019/0.20.4-embedded-assets.json>). |
| Datos |SQLite integrityok,2operaciones/0recetas/0versiones conservadas; providers.json sin cambios. Las preferencias de posición sí cambiaron durante uso de la UI. [Comparación](<C:/Users/luigi/Desktop/Axx assistant/evidence/resident-20261019/user-data-after-0.20.4.json>). |
| Baseline |20aserciones originales aprobadas;7archivos del manifiesto original preservados. No se regeneró el manifiesto histórico. |
| Inferencia remota |Pendiente de credencial configurada y respuesta real. No hay prueba de OpenRouter/Ollama cloud autenticado. `allow_paid:false`; sin claves prestadas ni respuesta inventada. |
| Inicio con Windows |El control está deshabilitado y etiquetado como no implementado; no se creó autoarranque. |
| Hardware/escritorio |Pendientes micrófono/altavoz físicos y aceptación completa de click-through, rueda, foco, atajos, monitores y escritorios virtuales. SAPI/ASR empaquetados sí procesaron WAV sintético real. |

## Fuente, datos y recuperación

Fuente reproducible: [snapshot aislado](<C:/Users/luigi/Desktop/Axx assistant/build/resident-release-0.20.3>), carpeta histórica con versión interna0.20.4. HTML final `EBB78A1B865EE818A4A2DD432839E6BE7304ADFCA58326880695C5B501722554`. El checkout canónico conserva el trabajo de biblioteca de comandos del otro chat; no se mezcló con este backend por las regresiones reproducidas de Blender/navegador/órdenes locales. [Compatibilidad](<C:/Users/luigi/Desktop/Axx assistant/evidence/resident-20261019/COMPATIBILIDAD_COMANDOS.md>).

Datos en `%LOCALAPPDATA%/Axx`, perfil WebView en `%LOCALAPPDATA%/com.axx.desktop`. Respaldo previo a esta instalación: `%LOCALAPPDATA%/Axx/backups/resident-20261019/before-0.20.4-install`, con SQLite consistente, configuración y EXE anterior. También se conservan respaldos de0.20.3 y la entrega inicial.

El router referencia variables de entorno en providers.json; no se implementó DPAPI nuevo. OpenRouter `openrouter/free` configurado no equivale a cuenta/cuota verificadas; Gemini2.0 retirado permanece deshabilitado. Hey Axx y escucha permanente siguen **FUTURO · NO ACTIVO**. No se habilitaron pagos ni publicación externa.
