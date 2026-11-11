# Aceptación Telegram y Android

Código candidato: `b99d8bd4855e3d516bdcdc4653a4eba314b0dd63`. Rama local: `codex/axx-phase-5`. Fecha: 10 de noviembre de 2026, America/Santo_Domingo. Evidencia privada en `build/phase5/`; no se publica con los informes.

Resultado global: **MANUAL_REQUIRED** para los dispositivos/canales completos. Se distinguen contrato, transporte saliente real y aceptación de la candidata.

## Telegram real

El usuario autorizó elegir la prueba; se usó el bot ya configurado `Axx_xxbot` y exclusivamente su propietario configurado. Se verificó identidad con getMe y se envió un único mensaje identificado de prueba. Telegram devolvió message_id **76** y coincidencia del destinatario. `telegram-real.json` registra PASS de **REAL_TELEGRAM_BOT_OUTBOUND_ONLY**. Los hashes de account.dpapi/bot.dpapi permanecieron iguales.

No se secuestró el polling de la instalación actual, no se copiaron sesiones al perfil candidato y no se pidieron códigos ni claves. El transporte entrante de la candidata no quedó vinculado a una cuenta independiente. Un envío confirmado no acredita ida/vuelta, vinculación de candidata ni ejecución remota.

| Capacidad | Estado real | Evidencia / pendiente |
|---|---|---|
| Identidad de bot y propietario destinatario | PASS | getMe + sendMessage; `telegram-real.json` |
| Mensaje saliente de prueba | PASS | message_id 76; no acredita lectura del destinatario |
| Contratos de identidad, emparejamiento, catálogo y separación de permisos | PASS | `telegram-contracts.log`; 98 casos/28.495 s, fixtures locales, no cuenta remota E2E |
| Vinculación de cuenta → candidata | MANUAL_REQUIRED | Cuenta/worker de prueba independiente y propietario localmente verificado |
| Mensajes entrantes y respuestas de la candidata | NOT_TESTED | No se consumió getUpdates ni se cambió webhook/sesión actual |
| Herramientas autorizadas, ambigüedad y denegaciones desde Telegram real | NOT_TESTED | Contratos no sustituyen el recibo por Telegram y observación del efecto |
| Reconexión y cancelación por Telegram real | NOT_TESTED | Necesita worker candidato y sesión de prueba controlada |
| Llamadas | BLOCKED | No hay implementación/aceptación completa acreditada; un probe o grant no demuestra llamada |
| Transferencias de archivos por Telegram | BLOCKED | No se acredita una implementación aceptada de extremo a extremo |

Prueba preparada: configurar localmente cuenta de prueba independiente con propietario diferente de la cuenta de servicio; autorizar conversation y sólo los permisos elegidos. Vincular desde la candidata, verificar IDs autenticados, enviar saludo, pedir telemetría, comprobar recibo y respuesta; intentar comando ambiguo y escritura sin grant; conceder una escritura limitada en directorio de prueba y cancelar otra; desconectar/reconectar conservando operation_id y confirmar que no se repiten efectos. Mantener llamadas/archivos bloqueados. Guardar IDs de operación y timestamps, nunca credenciales en el informe.

## Android

APK debug construido y firmado para prueba: `com.axx.mobile`, 0.2.14-companion, versionCode 35, minSDK 29, target/compile SDK 36. No se cambió application ID ni se firmó una release con otra identidad. El APK release generado permanece sin firma y no se entrega como instalable aprobado.

Los 22 recursos públicos incluidos en cada APK coinciden byte a byte con mobile/www generado del renderer actual. `companion-validation.json` pasó contratos /v1, backend móvil, navegador y selector de archivos. La validación física es un recibo separado.

| Comprobación en teléfono | Estado | Requisito |
|---|---|---|
| Instalación limpia | MANUAL_REQUIRED | ADB no encontró teléfono autorizado |
| Actualización conservando datos | MANUAL_REQUIRED | Teléfono con instalación previa y firma autorizada; no limpiar datos |
| Emparejamiento con Windows | MANUAL_REQUIRED | Red accesible y QR/identidad de la candidata |
| /v1 en dispositivo real | MANUAL_REQUIRED | Contratos PASS; falta ejecución Android ↔ Windows física |
| Mensajería y comandos remotos | MANUAL_REQUIRED | Comprobar recibo y efecto PC, no sólo ACK |
| Permisos por dispositivo / recibos aislados | MANUAL_REQUIRED | Dos identidades de prueba; intentar lectura cruzada y denegación |
| Reconexión y recuperación | MANUAL_REQUIRED | Cortar red/backend y retomar mismo operation_id sin repetir efectos |
| Transferencias de archivos implementadas | MANUAL_REQUIRED | /v1/files y pruebas de selector existen; falta subida/bajada y hash en teléfono |
| Release firmada / actualización con identidad estable | BLOCKED | Firma del propietario, versionCode de nueva entrega y aceptación física |

Secuencia preparada: inventariar datos de prueba existentes, instalar debug sólo en dispositivo de prueba compatible con esa firma, registrar APK/certificado; emparejar y comprobar versión/protocolo; mensajes, comando permitido/denegado, cancelación y dos dispositivos; transferir un archivo sintético y comprobar hash a ambos lados; cortar red, reiniciar PC/teléfono y conservar grants/drafts/recibos. Actualizar sin desinstalar ni usar adb -r con firma distinta; si hay incompatibilidad de firma, detenerse y usar dispositivo/perfil de prueba limpio. No se tocó ningún teléfono.
