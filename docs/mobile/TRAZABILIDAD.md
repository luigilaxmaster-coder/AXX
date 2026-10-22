# Trazabilidad M01–M34 / V01–V72

Latest checks: the user confirmed optical QR pairing on Samsung. Native permission denial/recovery and TLS synchronization were exercised. Windows hook delay was reproduced and corrected; see [pairing verification](PAIRING-VERIFICATION.md) and [input performance](INPUT-PERFORMANCE.md). These checks do not close a milestone.

Estado de ejecución: MO-1 en curso. Ningún hito cerrado. Los tests unitarios no equivalen a aceptación en Android.

| ID | Característica | Estado | Evidencia y pendiente |
|---|---|---|---|
| M01 | Continuidad | Implementado parcialmente | Historia compartida y envío idempotente en código; continuidad Android/PC pendiente. |
| M02 | Perfiles por PC | Pendiente | Sin recorrido móvil integrado/verificado todavía. |
| M03 | Dictado corregible | Implementado parcialmente | Captura Android, Whisper existente y revisión en PC integrados; prueba hablada y edición en teléfono pendientes. Ver VOZ-REMOTA.md. |
| M04 | Trackpad | Implementado parcialmente | Integración nativa, permiso input.control, lease, interfaz de pantalla completa y pruebas de contrato. Aceptación física completa en curso: CONTROL-REMOTO.md. |
| M05 | Portapapeles | Pendiente | Sin recorrido móvil integrado/verificado todavía. |
| M06 | Compartir y transferir | Pendiente | Sin recorrido móvil integrado/verificado todavía. |
| M07 | Cámara y escáner | Pendiente | Sin recorrido móvil integrado/verificado todavía. |
| M08 | Pantalla bajo demanda | Pendiente | Sin recorrido móvil integrado/verificado todavía. |
| M09 | Tareas y resultados | Implementado parcialmente | Consulta de operaciones reales; recorrido Android pendiente. |
| M10 | Widgets | Implementado parcialmente | Acceso 1×1 transparente colocado y tocado en Samsung: abre MainActivity. Widgets de estado/acciones de la ficha pendientes. |
| M11 | Presentación | Pendiente | Sin recorrido móvil integrado/verificado todavía. |
| M12 | Multimedia | Pendiente | Sin recorrido móvil integrado/verificado todavía. |
| M13 | Ratón por orientación | Pendiente | Sin recorrido móvil integrado/verificado todavía. |
| M14 | Recuperación | Implementado parcialmente | Journal de admisión y outcome_unknown; faltan cursor/retención y pruebas de red reales. |
| M15 | Accesibilidad y consumo | Implementado parcialmente | Corrección de recorte con fuentes grandes; lector de pantalla/consumo pendientes. |
| M16 | Catálogo real | Implementado parcialmente | Catálogo existente conectado por gateway; aceptación nativa pendiente. |
| M17 | Instancias compartidas | Pendiente | Sin recorrido móvil integrado/verificado todavía. |
| M18 | Personaje y paneles | Implementado parcialmente | Renderizador original extraído de Axx.html; copia de apariencia del PC; validación en curso. |
| M19 | Escritorio remoto | Pendiente | Sin recorrido móvil integrado/verificado todavía. |
| M20 | Aplicaciones y ventanas | Pendiente | Sin recorrido móvil integrado/verificado todavía. |
| M21 | Cola y dependencias | Pendiente | Sin recorrido móvil integrado/verificado todavía. |
| M22 | Decisiones | Pendiente | Sin recorrido móvil integrado/verificado todavía. |
| M23 | Cesión del control | Implementado parcialmente | Integración nativa, permiso input.control, lease, interfaz de pantalla completa y pruebas de contrato. Aceptación física completa en curso: CONTROL-REMOTO.md. |
| M24 | Configuración por ámbito | Pendiente | Sin recorrido móvil integrado/verificado todavía. |
| M25 | Proveedores | Pendiente | Sin recorrido móvil integrado/verificado todavía. |
| M26 | Memoria | Pendiente | Sin recorrido móvil integrado/verificado todavía. |
| M27 | Rutinas | Pendiente | Sin recorrido móvil integrado/verificado todavía. |
| M28 | Archivos del PC | Pendiente | Sin recorrido móvil integrado/verificado todavía. |
| M29 | Contexto y cámara | Pendiente | Sin recorrido móvil integrado/verificado todavía. |
| M30 | Diagnóstico | Pendiente | Sin recorrido móvil integrado/verificado todavía. |
| M31 | Vinculación por QR y administración de dispositivos | Implementado parcialmente | QR visible desde menú del muñeco, TLS y Keystore. Enrolamiento por enlace probado en Samsung; escaneo físico del QR y administración completa pendientes. |
| M32 | Micrófono del teléfono y conversación hablada | Implementado parcialmente | Atajo global registrado y captura/ASR/dispatch integrados; recorrido con frase humana y resultado aún no acreditado. |
| M33 | Teclado remoto, texto y atajos | Implementado parcialmente | Integración nativa, permiso input.control, lease, interfaz de pantalla completa y pruebas de contrato. Aceptación física completa en curso: CONTROL-REMOTO.md. |
| M34 | Conexión local, remota y diagnóstico de red | Pendiente | Sin recorrido móvil integrado/verificado todavía. |

## Escenarios

| ID | Escenario | Resultado esperado | Hito | Estado | Evidencia |
|---|---|---|---|---|---|
| V01 | Vinculación inicial | PC y teléfono muestran misma identidad y ámbitos | MO-1 | Pendiente | No ejecutado en teléfono real. |
| V02 | Cliente sin permiso intenta herramienta | Rechazo en ejecutor, aunque la UI lo intente | MO-1 | Pendiente | No ejecutado en teléfono real. |
| V03 | QR vencido | No emite credencial | MO-2 | Pendiente | No ejecutado en teléfono real. |
| V04 | QR consumido dos veces concurrentemente | Sólo una vinculación válida | MO-2 | Pendiente | No ejecutado en teléfono real. |
| V05 | Nombre de PC igual, certificado distinto | Rechazo o nueva vinculación explícita | MO-2 | Pendiente | No ejecutado en teléfono real. |
| V06 | Revocar dispositivo con socket abierto | Entrada y nuevas operaciones bloqueadas | MO-2 | Pendiente | No ejecutado en teléfono real. |
| V07 | Scope de observar intenta escribir | Denegación específica | MO-2 | Pendiente | No ejecutado en teléfono real. |
| V08 | ACK perdido tras admisión, incluso con plazo vencido al consultar | Recupera task_id original sin nueva admisión | MO-2 | Pendiente | No ejecutado en teléfono real. |
| V09 | Mismo command_id con payload distinto | Conflicto, sin sustitución | MO-2 | Pendiente | No ejecutado en teléfono real. |
| V10 | Evento durante descarga de snapshot | Sin hueco al aplicar cursor | MO-2 | Pendiente | No ejecutado en teléfono real. |
| V11 | Eventos duplicados/fuera de orden | Estado coherente, sin repetir efectos | MO-2 | Pendiente | No ejecutado en teléfono real. |
| V12 | Cursor fuera de retención | Nuevo snapshot | MO-2 | Pendiente | No ejecutado en teléfono real. |
| V13 | Reinicio del ejecutor | Nuevo boot; leases inválidos; consulta del command_id previo recupera tarea sin ejecutar otra vez | MO-2 | Pendiente | No ejecutado en teléfono real. |
| V14 | Caída después de un efecto, antes del journal final | Verificación o outcome_unknown, sin repetición ciega | MO-2 | Pendiente | No ejecutado en teléfono real. |
| V15 | Cambiar reloj del teléfono | No extiende QR ni lease | MO-2 | Pendiente | No ejecutado en teléfono real. |
| V16 | PC sin micrófono | Voz móvil llega al Axx real | MO-3 | Pendiente | No ejecutado en teléfono real. |
| V17 | STT parcial cambia varias veces y emite final | Una intención sólo con cierre válido de turno; ninguna parcial ejecutada | MO-3 | Pendiente | No ejecutado en teléfono real. |
| V18 | Micrófono denegado | Teclado y funciones independientes siguen | MO-3 | Pendiente | No ejecutado en teléfono real. |
| V19 | Llamada entrante | Estado de interrupción y recuperación visible | MO-3 | Pendiente | No ejecutado en teléfono real. |
| V20 | Cambio de ruta Bluetooth | Fuente/salida efectivas conocidas | MO-3 | Pendiente | No ejecutado en teléfono real. |
| V21 | Cortar red durante frase; STT emite final al cerrar audio | Turno interrumpido queda como borrador; no ejecuta al reconectar | MO-3 | Pendiente | No ejecutado en teléfono real. |
| V22 | Interrumpir TTS durante tarea | Audio se detiene; tarea conserva estado | MO-3 | Pendiente | No ejecutado en teléfono real. |
| V23 | Cambiar PC durante dictado | Turno conserva destino o se cancela explícitamente | MO-3 | Pendiente | No ejecutado en teléfono real. |
| V24 | Insertar dictado | Texto correcto, sin enviar formulario | MO-3 | Pendiente | No ejecutado en teléfono real. |
| V25 | Cortar red durante arrastre | Watchdog caduca y recupera entrada | MO-4 | Pendiente | No ejecutado en teléfono real. |
| V26 | Canal fiable cae, vídeo sigue; llegan heartbeats antiguos | Lease invalidado; desafíos viejos no extienden vencimiento | MO-4 | Pendiente | No ejecutado en teléfono real. |
| V27 | Paquete de época anterior | Descartado | MO-4 | Pendiente | No ejecutado en teléfono real. |
| V28 | Movimiento intermedio perdido | Acumuladores conservan movimiento vigente sin salto tardío | MO-4 | Pendiente | No ejecutado en teléfono real. |
| V29 | Movimiento 100, clic en 100, movimiento 110 con reordenamiento | Un único acumulador; después del clic aplica 10 o cancela si el orden es irreconciliable | MO-4 | Pendiente | No ejecutado en teléfono real. |
| V30 | Dos móviles solicitan control | Un propietario efectivo | MO-4 | Pendiente | No ejecutado en teléfono real. |
| V31 | Usuario físico interviene | Se suspende control remoto | MO-4 | Pendiente | No ejecutado en teléfono real. |
| V32 | Solapamiento con modificador físico | No liberación indiscriminada; recuperación explícita | MO-4 | Pendiente | No ejecutado en teléfono real. |
| V33 | Giro o background durante gesto | No clic ni tecla residual | MO-4 | Pendiente | No ejecutado en teléfono real. |
| V34 | Español, CJK, emoji y composición IME | Texto final íntegro, sin duplicación | MO-4 | Pendiente | No ejecutado en teléfono real. |
| V35 | Foco cambia antes de insertar | Texto conservado, no insertado en destino errado | MO-4 | Pendiente | No ejecutado en teléfono real. |
| V36 | Proceso elevado/UAC/bloqueo | Límite detectado, sin éxito fingido | MO-4 | Pendiente | No ejecutado en teléfono real. |
| V37 | Segundo monitor a la izquierda con DPI distinto | Transformación validada en puntos conocidos | MO-4 | Pendiente | No ejecutado en teléfono real. |
| V38 | Hotplug, rotación y cambio de escala | Geometry revision renovada; clic viejo rechazado | MO-4 | Pendiente | No ejecutado en teléfono real. |
| V39 | Bandas negras, recorte y zoom local | Coordenada dentro del contenido correcto | MO-4 | Pendiente | No ejecutado en teléfono real. |
| V40 | Frame demasiado antiguo | Refresco antes de actuar | MO-4 | Pendiente | No ejecutado en teléfono real. |
| V41 | Caída de UI con tecla activa | Broker/watchdog responde según garantía declarada | MO-4 | Pendiente | No ejecutado en teléfono real. |
| V42 | Saturar transferencia mientras se detiene control | Colas acotadas; watchdog sigue operativo | MO-4/MO-5 | Pendiente | No ejecutado en teléfono real. |
| V43 | Cerrar ficha del convertidor | Misma tarea sigue en PC | MO-5 | Pendiente | No ejecutado en teléfono real. |
| V44 | Pen, grabador y remoto a la vez | Composición y consumidores independientes | MO-5 | Pendiente | No ejecutado en teléfono real. |
| V45 | Cerrar sólo vista remota | Grabación continúa | MO-5 | Pendiente | No ejecutado en teléfono real. |
| V46 | Transferencia interrumpida | Reanuda bloques válidos y verifica archivo único | MO-5 | Pendiente | No ejecutado en teléfono real. |
| V47 | Archivo origen cambia | Reanudación anterior invalidada | MO-5 | Pendiente | No ejecutado en teléfono real. |
| V48 | Carpeta llena o revocada | Error recuperable; original intacto | MO-5 | Pendiente | No ejecutado en teléfono real. |
| V49 | Colisión de nombre y ruta con escapes | Política aplicada y alcance respetado | MO-5 | Pendiente | No ejecutado en teléfono real. |
| V50 | Presentación pierde foco | No avanza una ventana diferente | MO-5 | Pendiente | No ejecutado en teléfono real. |
| V51 | Copia temporal del portapapeles y cambio del usuario | No restauración sobre contenido nuevo | MO-5 | Pendiente | No ejecutado en teléfono real. |
| V52 | Dos clientes responden una decisión; cancelación desde espera o cola | Una resolución vigente; cancelación sigue la tabla de estados y conserva efectos ya ocurridos | MO-6 | Pendiente | No ejecutado en teléfono real. |
| V53 | Configuración modificada simultáneamente | Conflicto conservando ambas propuestas | MO-6 | Pendiente | No ejecutado en teléfono real. |
| V54 | Rutina cambia durante ejecución | Trabajo usa versión admitida | MO-6 | Pendiente | No ejecutado en teléfono real. |
| V55 | Proveedor cloud cae con LAN disponible | Diagnóstico separado; control local viable | MO-6 | Pendiente | No ejecutado en teléfono real. |
| V56 | Reiniciar Axx caído sin supervisor | Indisponibilidad honesta | MO-6 | Pendiente | No ejecutado en teléfono real. |
| V57 | Widget con estado antiguo | Antigüedad visible y consulta al abrir | MO-7 | Pendiente | No ejecutado en teléfono real. |
| V58 | Detener desde widget sin conectividad | No afirma confirmación de PC | MO-7 | Pendiente | No ejecutado en teléfono real. |
| V59 | Audio desde app y desde widget/Intent | Pruebas separadas por OS y permisos | MO-7 | Pendiente | No ejecutado en teléfono real. |
| V60 | Android 17 con target 37 | Red local concedida/denegada/revocada verificadas | MO-7 | Pendiente por plataforma | SDK objetivo 36; teléfono disponible API31. Requiere SDK/dispositivo API37. |
| V61 | iPhone sin Dynamic Island o actividad desactivada | Funciones principales disponibles en app | MO-7 | Fuera de alcance | iOS no forma parte de esta ejecución. |
| V62 | Bloqueo, force-stop y reinicio móvil | No escucha ni control fantasma | MO-7 | Pendiente | No ejecutado en teléfono real. |
| V63 | Cámara denegada o escáner ausente | Importación de archivos sigue disponible | MO-7 | Pendiente | No ejecutado en teléfono real. |
| V64 | Texto grande y lector de pantalla | Controles y estados utilizables | MO-7 | Pendiente | No ejecutado en teléfono real. |
| V65 | Ahorro de energía/temperatura | Degradación visual antes de perder controles esenciales | MO-7 | Pendiente | No ejecutado en teléfono real. |
| V66 | Actualizar PC/móvil en orden diferente | Compatibilidad negociada y datos conservados | MO-7 | Pendiente | No ejecutado en teléfono real. |
| V67 | Identidad restaurada en teléfono distinto | Nuevo enrolamiento cuando corresponda | MO-7 | Pendiente | No ejecutado en teléfono real. |
| V68 | Cambiar Wi-Fi/datos con control activo | Entrada invalidada; reconexión sin replay | MO-8 | Fuera de alcance | MO-8 no forma parte de esta ejecución. |
| V69 | NAT restrictivo y ruta TURN | Ruta real visible, autenticada y medida | MO-8 | Fuera de alcance | MO-8 no forma parte de esta ejecución. |
| V70 | Revocación remota con PC incomunicada | Pendiente y caducidad según autoridad | MO-8 | Fuera de alcance | MO-8 no forma parte de esta ejecución. |
| V71 | Cortar WAN manteniendo LAN | Capacidades locales realmente disponibles | MO-2/MO-8 | Pendiente | No ejecutado en teléfono real. |
| V72 | App instalada y acceso habitual del escritorio | El módulo funciona en la instalación real, no sólo en demo | Todos | Pendiente | No ejecutado en teléfono real. |
