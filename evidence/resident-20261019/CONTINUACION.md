# ContinuaciÃ³n Axx residente â€” 0.20.4

El usuario autorizÃ³ terminar la instalaciÃ³n sin grabaciÃ³n y coordinar el chat Â«Integrar comandos en AxxÂ». Ãšltima instrucciÃ³n: que Axx se mueva y sea vivo.

## Estado actual

- 0.20.3 se instalÃ³ realmente en `%LOCALAPPDATA%/Programs/Axx/Axx.exe`; el usuario la cerrÃ³. No confundir el error del verificador antiguo (readyfile efÃ­mero eliminado por diseÃ±o) con un fallo de arranque.
- Snapshot de entrega: `build/resident-release-0.20.3`, nombre histÃ³rico y versiÃ³n interna **0.20.4**. Fuentes congeladas; no restaurar ni mezclar el checkout canÃ³nico.
- HTML final EBB78A1B865EE818A4A2DD432839E6BE7304ADFCA58326880695C5B501722554. Backend estable 8312CE40F16DB6B024CF2A8BAC1268B0AE15F867E089002138E1F16884D909AC, sin cambios. Voz E61076C5081F8C442C054097731A7A15A25A1817E8035C6DAABEDB7594537555.
- Frontend: barrido de24 formas aprobado y19/19 contratos restantes; host:15 unitarias aprobadas,1 auxiliar interno ignorado,1 auditorÃ­a exacta de recursos aprobada. Evidencia en FRONTEND_LIVENESS.md, 0.20.4-native-tests.log, 0.20.4-embedded-assets.json y 0.20.4-source-freeze.json.
- Paseo limitado64pxCSS, suavizado por tiempo real, pausa20s tras arrastre, pausa durante trabajo/paneles/teclado/voz, pin y movimiento reducido. Nunca persiste por cuadro el ancla manual. RespiraciÃ³n y reacciÃ³n al cursor sin cambiar identidad.
- NSIS0.20.4 en compilaciÃ³n con builder del snapshot y -SkipBackend; sesiÃ³n76970. Log raÃ­z final-0.20.4-package-command.log y log NSIS del snapshot. No compilar en paralelo el mismo target.
- Respaldo actual: `%LOCALAPPDATA%/Axx/backups/resident-20261019/before-0.20.4-install`, state.db integrityok,2 operaciones,0 recetas/versions. Ver user-data-before-0.20.4.json.
- Verificador actualizado usa native-runtime.json saneado y persistente, PID/version/UUID/hash/descendencia y HTTP401; ejecuta EXE instalado con PATHWindows y sin PYTHONHOME/PYTHONPATH/VIRTUAL_ENV. Shortcuts se validan aparte.

## Cierre de esta entrega

Instalación0.20.4, publicación, hashes, registro, shortcuts, servicio privado401 y conservación de datos verificados. Movimiento reducido se desmarcó mediante UI normal con permiso de disponer30s de Axx; se cerró el panel sinEsc. Diagnóstico23:39:03Z: reducedfalse/roamtrue/pinnedfalse/moderoam, primerpaso físico confirmado. Dos observaciones posteriores mostraron origen3366,505 y3301,483, ventana304x304, cuerpo animado y ningún panel abierto. Axx quedó abierto.

Ver DELIVERY_STATUS.md, MOVIMIENTO_INSTALADO.md e installed-motion-after-enable.json. No grabación de video. Pendientes credencial/inferencia remota, hardware audio, aceptación exhaustiva de entradas/atajos/monitores/escritorios virtuales y autoarranque no implementado. No inventar esas validaciones.

Coordinación final entregada con éxito al chat de comandos tras errores iniciales AbsolutePathBuf. Liberada solo copia aislada para corregir tres regresiones; no checkout/adopción, instalación, datos, recursos, snapshot, versión ni recibos. Detalle COORDINACION_FINAL.md. No revertir su trabajo canónico ni instalar backend90e704 por accidente.
