# Axx Transfer

Archivos integra copias entre Axx de Windows y Axx Mobile para Android, utilizando
el enlace HTTPS autenticado y fijado al certificado del QR existente. Funciona en
red local o entre redes distintas mediante una red privada Tailscale existente.

## Configuración

1. En Windows, abre Ajustes y elige **Misma red** o **Redes distintas · Tailscale**.
   Para la segunda opción, conecta Tailscale en PC y Android a la misma red privada
   de Tailscale. Genera entonces el QR de Axx y escanéalo desde Axx Mobile. Se
   conservan identidad y permisos al volver a enlazar el mismo teléfono.
2. Abre **Archivos** en Windows. Selecciona el teléfono y autoriza por separado
   lectura de carpetas concretas y recepción. El emparejamiento no concede estos
   permisos automáticamente. No selecciones un disco completo.
3. En Android, abre **Archivos** para buscar en la PC o elegir un documento mediante
   el selector de Android. Recibir copia al almacén privado de Axx; **Guardar** crea
   una copia externa en el destino que el usuario elige.
4. Para dictar, abre Chat y pulsa **Dictar**. El audio viaja al PC vinculado para
   transcripción local. Revisa el borrador y pulsa Enviar; el dictado no ejecuta
   acciones automáticamente.

Los originales se conservan. La búsqueda devuelve archivos de las carpetas
autorizadas y solicita una elección cuando hay varios resultados. Las referencias
de archivo se vuelven a validar al preparar la copia.

## Contrato y protección

- Un transporte: HTTPS entre el Android emparejado y la PC. La huella del
  certificado se obtiene del QR, sin omitir comprobaciones de identidad.
- Transferencias identificadas por UUID, ligadas al teléfono y al contenido.
  Repetir una operación con otro contenido se rechaza.
- Bloques de 256 KiB, tamaño máximo de archivo 5 GiB. No se carga el archivo
  completo en memoria. SHA-256 y tamaño se verifican antes de confirmar recepción.
- Almacenamiento privado cifrado por bloque con AES-GCM y nonce aleatorio.
  Metadatos cifrados; clave protegida por DPAPI en Windows y Android Keystore en
  Android. Los reintentos leen bloques persistidos, sin inventar progreso.
- Exportar descifra una copia mediante el destino elegido. Esa copia externa se
  rige por la protección del destino y no pertenece a la bandeja cifrada de Axx.
- Permisos verificados por solicitud; referencias y transferencias pertenecen a
  un dispositivo. No se permiten rutas propuestas por un comando remoto, saltos
  fuera de las raíces autorizadas ni sobrescrituras silenciosas en Windows.
- Pausar y reanudar conservan progreso. Cancelar no borra un archivo que ya fue
  recibido. El recibo del teléfono se acepta tras verificación y guardado local.
- Las búsquedas privadas de Archivos se procesan antes del proveedor de chat. El
  reconocimiento de voz usa el servicio Whisper local existente de Windows.

El cifrado entre estos dos extremos no implica anonimato de red ni protección de
un dispositivo comprometido. Axx no abre puertos públicos ni omite el certificado.
Tailscale decide entre conexión directa y relay cifrado según la red; requiere su
cliente conectado en ambos extremos. No hay buzón externo de archivos.

### Redes distintas

La opción Tailscale consulta su cliente local sin iniciar sesión ni modificar su
configuración. Solo admite una dirección propia activa dentro de `100.64.0.0/10`
y enlaza el servidor a esa interfaz concreta. Si falta la sesión, cambia la
dirección o no está disponible, muestra un error y no vuelve silenciosamente a
la red local. El teléfono mantiene la comprobación del certificado del QR en
ambos modos. Cambiar de red requiere generar/escanear el QR correspondiente.

La cuenta y reglas de acceso de Tailscale deben permitir que ambos equipos se
comuniquen. El modo remoto no enciende la PC ni descarga archivos nuevos con Axx
cerrado. La integración no crea cuentas, servicios de pago ni reglas de firewall.
Si una regla impide la comunicación, corrige únicamente el acceso necesario a
la interfaz privada; no desactives el firewall.

Referencias: [conexiones directas y relay](https://tailscale.com/docs/reference/connection-types),
[direcciones privadas](https://tailscale.com/docs/concepts/tailscale-ip-addresses).

## Interfaz y recuperación

Archivos utiliza el panel de Axx existente y conserva el personaje y material 3D.
Los gestos acompañan eventos reales y usan tarjetas de resultados; no se simula
identificar un icono de Explorer. El progreso y los controles siguen disponibles
si la animación no se puede renderizar. Se respeta movimiento reducido.

El teléfono debe mantener Axx visible para continuar el bucle de transferencia.
Tras una interrupción, consulta la transferencia y reanuda desde los bloques
confirmados. Cerrar o suspender Android no equivale a una entrega completada.

## Validación reproducible

Desde la raíz, con las dependencias del repositorio:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s backend/mobile/tests -v
node mobile/build.mjs
.\.venv\Scripts\python.exe -m unittest discover -s mobile/tests -v
```

Para Android usa JDK 21 y `mobile/android/gradlew.bat testDebugUnitTest assembleDebug`.
Las pruebas de protocolo y navegador no sustituyen una copia entre Windows y un
teléfono físico. Registra aparte dispositivos, tamaños, hashes, reinicios y red
utilizados en la aceptación.

## Límites pendientes

Un relay propio de Axx, buzón diferido, iOS, tareas Android de segundo plano, selección
real de Explorer, varios PCs, OCR, búsqueda semántica, paquetes CAD y devolución
automática de revisiones requieren integraciones y aceptación adicionales. Un PC
apagado no puede ejecutar una búsqueda nueva. No se anuncian esas capacidades
como implementadas por mostrar esta interfaz.
