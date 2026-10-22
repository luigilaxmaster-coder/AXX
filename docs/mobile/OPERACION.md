# Axx Android — revisión de integración MO-1

Esta revisión todavía no cierra MO-1–MO-7. Usa la instalación de escritorio existente y no sustituye sus datos, proveedores, Magic Pen ni convertidor.

## Vinculación local

1. Haz clic derecho sobre el muñeco de Axx en la PC → **Conectar teléfono · QR**. La sección **Acceso móvil · red local** aparece al principio de Ajustes. Pulsa **Activar / nuevo QR**. Conservar historial debe estar activado para compartir la conversación.
2. Abre Axx Mobile en Android, pulsa el equipo de la cabecera y **Escanear QR del PC**. También puedes pegar el enlace alternativo mostrado por Axx.
3. Confirma **Vincular**. El QR es de un solo uso y caduca a los 120 segundos. El teléfono verifica el certificado recibido en ese QR; las credenciales se guardan cifradas mediante Android Keystore.
4. La animación y el texto indican la recepción de la apariencia y la conversación. Solo aparece **sincronizado** después de recibirlos. La animación respeta el movimiento reducido del sistema.

El gateway se activa desde Axx, usa HTTPS en la IP privada y no publica el backend loopback. Consulta y voz son los alcances iniciales; la presencia de un permiso no significa que todos sus recorridos estén implementados. Internet no está habilitado.

## Muñeco e inicio del teléfono

- El cliente compila el renderizador original de `1.AXX/Axx.html`. Recibe forma, paleta, acabado, cámara, parámetros del estudio y estado del escritorio.
- El estado distingue la actividad del PC y la presentación local animada, estática o con movimiento reducido.
- Toca el muñeco para una reacción local. **Girar Axx** permite arrastrarlo; los márgenes siguen permitiendo desplazar la página. Enter/espacio y las flechas ofrecen acceso por teclado.
- **Movimiento** permite seguir al sistema, animar o pausar localmente. Las preferencias del escritorio que impiden animar siguen aplicándose.
- En **Escritorio → Añadir Axx a inicio**, Android solicita un widget 1×1 con el PNG transparente del muñeco. Confirma **Añadir** en el launcher. Si ya existe, se actualiza sin duplicarlo. Un toque abre la app; no ejecuta herramientas ni activa el micrófono.
- En el Samsung probado, Gaming Hub oculta el acceso normal de la aplicación. El widget permite abrir Axx desde Inicio sin cambiar la visibilidad de otros juegos. Si el diseño de Inicio está bloqueado, desbloquéalo para añadirlo y vuelve a bloquearlo después.
- Al **Guardar cambios** en Apariencia de la PC, el teléfono conectado actualiza el muñeco y el PNG del widget. La cámara y la animación no generan escrituras continuas del icono. Se conserva la última imagen sin conexión y se actualiza al volver a abrir/conectar la app; no hay un servicio permanente en segundo plano. El icono base del cajón de aplicaciones sigue siendo el recurso incluido en el APK: el acceso dinámico es el widget del inicio.
- El PNG fuente del icono de esta revisión está en `mobile/icons/axx-character.png`, exportado del renderizador con forma 19, paleta 1 y acabado prismático. Los launchers pueden aplicar su propia máscara al icono de aplicación.

## Recuperación y límites actuales

El borrador se guarda localmente. Un envío lleva un ID persistido antes de la petición. **Consultar envío pendiente** consulta el mismo comando; una respuesta desconocida no provoca una nueva ejecución automática.

El gateway se apaga tras perder contacto con el teléfono. Si la PC se cierra o el acceso se desactiva, actívalo y genera otro QR desde la PC. La reconexión con dirección renovada y los perfiles múltiples siguen pendientes de MO-2.

El chat móvil actual usa la conexión API elegida en el escritorio. Axx Connect/ChatGPT todavía no está integrado con el aislamiento de herramientas requerido. La consulta de catálogo y operaciones usa los servicios existentes; entrada remota, transferencias y gran parte de los hitos continúan pendientes. La implementación de voz remota y su aceptación pendiente se describen en `VOZ-REMOTA.md`.

## Compilación

Desde `mobile`: `npm ci`, `npm run sync`; con JDK 21, desde `mobile/android`: `gradlew.bat assembleDebug testDebugUnitTest lintDebug`.

APK: `mobile/android/app/build/outputs/apk/debug/app-debug.apk`. Instalar como actualización con `adb install --no-streaming -r`; no desinstalar para resolver incompatibilidades.

Escritorio: `scripts/build-windows.ps1`. Antes de actualizar, ejecutar `scripts/backup-mobile-upgrade.py`, comprobar las firmas de ambos ejecutables y conservar la copia verificada. El informe de cada compilación está en su carpeta de evidencia.

Los tests de navegador usan un transporte de prueba aislado; no acreditan aceptación Android. Los resultados del dispositivo y los pendientes están separados en la matriz y en los informes de evidencia.
