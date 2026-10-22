# Módulo 04 — integración y registro de ejecución

Plan autorizado: MO-1 a MO-7, Android Capacitor, LAN; Android mínimo 29, objetivo 36. MO-8 e iOS fuera de ejecución. Este documento describe el código inspeccionado, no acredita aceptación.

## Componentes y cambios necesarios

| Área | Autoridad existente | Integración y brecha |
|---|---|---|
| Shell e identidad | `1.AXX/Axx.html`, Tauri `src-tauri/src/lib.rs` | Conservar muñeco, órbita y paneles; añadir tarjeta móvil a ajustes mediante IPC autenticado. |
| Conversación | Companion/localStorage, BrainClient, InferenceAdapter y CodexProvider | La historia actual es local al WebView. Hace falta persistencia compartida con importación conservadora por ID y revisión; no basta reenviar chat. |
| Herramientas y tareas | ActionExecutor, CommandService, ConnectService | Exponer catálogo/operaciones reales. Mantener aprobaciones del ejecutor, IDs y estados. |
| Permisos | Token privado del host, aprobaciones de CommandService | Nuevo registro SQLite de dispositivos/ámbitos y gateway TLS optativo; host permanece en loopback. |
| Voz | WindowsSpeechService y OfflineTranscriptionService | Captura Android → STT existente → borrador explícito; parciales nunca son órdenes. |
| Captura | ScreenRecordingService, MagicPenService y comandos Tauri | Separar consumidores; no sustituir captura por ejemplos o imágenes antiguas. |
| Entrada | Comandos nativos de escritorio | Hace falta árbitro único con lease/watchdog y preempción física; no publicar entrada hasta comprobarlo. |
| Archivos | Workspace del ActionExecutor y ConverterService | Recursos seleccionados, referencias autorizadas, bloques e integridad; nunca rutas arbitrarias del cliente. |
| Magic Pen | MagicPenService + `scripts/magic-pen.js` | Controlar la sesión de escritorio; eliminar editor móvil independiente del build operativo. |
| Convertidor | ConverterService + `scripts/converter.js` | Consultar/controlar trabajos con sus mismos IDs y recursos. |
| Memoria/rutinas | ProceduralMemory, AiMemoryAdapter, CommandService | Adaptadores de permisos y revisiones sobre servicios actuales. |
| Configuración | provider_settings, IdentityStore, prefs de Companion | Separar teléfono/PC, redactar secretos, verificar revisiones antes de escribir. |

## Preservación y recuperación

El árbol tenía cambios del usuario en package.json, evidencias y prototipo mobile antes de comenzar. Se trabaja sobre ese árbol sin restablecerlos. El build operativo usa `mobile/client.html` y copia los estilos/avatar existentes; el prototipo original se conserva. No se publican los controladores simulados en el APK.

Las nuevas tablas son aditivas en SQLite. Antes de instalar escritorio: copia consistente de SQLite, respaldo del directorio de datos y frontend local; comprobar firma del instalador existente y entrante. Nunca desinstalar para forzar actualización. El gateway nace desactivado, se apaga con el proceso host y sólo usa rutas fijas del backend existente.

## Registro

- 2026-10-22: inspección de Tauri 2.12.3/Axx 0.20.11, SDK Android 35/36, Node 24.14.0. Teléfono Samsung SM-A217M conectado por ADB inalámbrico, API 31.
- Pruebas locales de trust_store y TLS: 4/4 pasan; son pruebas automatizadas con dependencias aisladas, no validación móvil ni cierre MO-1.
- Ruling: conservar prototipo original y empaquetar un entrypoint operativo separado — el original contiene éxitos fabricados — coste: mantener clara la diferencia entre demo y cliente instalado.
- MO-1 en curso; ningún hito cerrado. Hay APK Android y actualización del escritorio instalados. Ver `RESULTADOS-20261022.md` para la evidencia real y las limitaciones.

## Fuentes del entorno

[Capacitor 8: migración](https://capacitorjs.com/docs/updating/8-0) fija compileSdk/targetSdk 36. [Entorno](https://capacitorjs.com/docs/getting-started/environment-setup). V60 requiere SDK/dispositivo API37; no se acredita con el Samsung API31.
