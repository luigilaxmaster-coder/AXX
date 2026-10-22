# Control remoto de Axx — implementación local

## Integración

El teléfono utiliza `AxxTransport` (credenciales privadas en Keystore y certificado fijado por el QR). El gateway existente autentica cada petición. `RemoteControl` mantiene un único lease efímero; `WindowsInput` es el propietario nativo de la inyección, los hooks de prioridad local, el watchdog y la superposición. La voz conserva su coordinador independiente.

No hay un nuevo motor ni una réplica de herramientas. La inyección usa `SendInput`; las ventanas elevadas y el escritorio seguro pueden rechazarla. No se intenta eludir esa frontera de Windows. [Contrato de SendInput](https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-sendinput).

## Material del cursor

`remote-control.js` de escritorio obtiene `Axx.app.renderer.materialTable()`: tabla real 512×512 del renderizador del personaje, calculada a partir de paleta, acabado, rugosidad, exposición, dirección de luz y respuesta luminosa del estado. Se muestrea a 128×128 sin introducir una paleta alternativa. El backend aplica esa tabla a un contorno orgánico pequeño con centro transparente.

La ventana nativa usa `WS_EX_LAYERED`, `WS_EX_TRANSPARENT`, `WS_EX_NOACTIVATE` y `WS_EX_TOOLWINDOW`. Sigue `GetCursorPos` en coordenadas físicas, mantiene el cursor original y no intercepta sus eventos. La imagen se actualiza como máximo a 30 Hz; la posición se consulta en el bucle de entrada. El tamaño sigue el DPI de la ventana. Se respeta tanto la preferencia enviada desde Axx como la desactivación de animaciones de Windows. [Ventanas con capas](https://learn.microsoft.com/en-us/windows/win32/winmsg/window-features).

Concesión y liberación voluntaria: transición de 150 ms; clic: deformación breve; arrastre: estiramiento leve. Revocación, intervención local y caducidad: desaparición inmediata. Con movimiento reducido se suprimen las deformaciones y transiciones. El personaje original no cambia.

## Contratos reales

Todas las rutas del teléfono están bajo TLS y requieren la credencial de su dispositivo.

| Operación | Ruta / datos | Autorización |
|---|---|---|
| Consultar | GET `/v1/control/status` | `query`; oculta el ID del lease ajeno |
| Solicitar | POST `/v1/control/acquire` `{request_id: UUID, visible: true}` | `input.control`, concedido expresamente desde la PC |
| Renovar | POST `/v1/control/renew` `{lease_id, boot_id, visible: true}` | Propietario, permiso vigente, lease sin caducar |
| Entrada | POST `/v1/control/events` `{lease_id, boot_id, seq, events}` | Comprobación antes de admitir y antes de cada inyección |
| Liberar | POST `/v1/control/release` `{lease_id, boot_id}` | `query` y propiedad de la sesión |

Eventos admitidos: `move{x,y}`, `scroll{x,y}`, `button{button,down}`, `key{key,down}` y `text{text}`; todos llevan `type`. Máximo 16 eventos y 512 caracteres por paquete. Las teclas y campos se validan con listas cerradas.

Las rutas locales `/axx-api/mobile/control/status`, `control/material`, `control/cancel` e `input-permission` requieren la autenticación del host de Axx. No se publican como operaciones móviles genéricas.

Estados: sin control, solicitado en la interfaz, concedido, ocupado o liberado con motivo. TTL: 3 s de reloj monotónico; renovación de la interfaz cada 800 ms. Una secuencia repetida con el mismo hash del último paquete devuelve el estado sin reinyección. Secuencias alteradas, atrasadas, saltadas y épocas anteriores se rechazan. No se persisten eventos ni se recupera automáticamente un lease.

La parada descarta la cola del teléfono y revoca en la PC. Si la red no permite comunicarla, el watchdog nativo libera botones y teclas al vencer el lease. La intervención de cualquier entrada local no marcada como propia revoca el control; el evento físico continúa hacia la aplicación. Escape local funciona aunque no exista red. Se evita liberar el modificador o botón que el usuario físico acaba de tomar.

## Interfaz y fluidez

En **Escritorio → Trackpad / Teclado** se abre una vista que ocupa el WebView completo. Los controles del ratón tienen una superficie amplia; sensibilidad y scroll por botones quedan en ajustes. El teclado dispone de editor de texto, modificadores con estado visible y filas separadas para funciones y flechas. Cerrar la vista, salir de la aplicación o cambiar de sección libera el control. Cambiar entre trackpad y teclado conserva la sesión y termina cualquier arrastre.

El texto se envía sólo mediante **Enviar texto**, conservando el borrador. No se convierten fragmentos de composición IME en órdenes. Se utiliza la ventana activa de Windows; todavía no existe reserva verificable de foco para el escenario V35.

El transporte conserva en memoria nativa el perfil descifrado, el contexto TLS fijado a la identidad y las conexiones de entrada reutilizables. La cola de entrada está separada de voz/consultas; timeout de control 1,5 s, sin reenvío de eventos desde la interfaz. El gateway vuelve a autenticar cada petición de una conexión persistente y la rechaza si el acceso móvil fue desactivado. TCP_NODELAY evita retener paquetes pequeños. Los movimientos pendientes contiguos se acumulan; los clics mantienen su orden. Se conservan fracciones de desplazamiento y se evita aplicar una segunda curva de aceleración de Windows.

## Cobertura y límites

M04 y M33: implementados localmente. M23: arbitraje local y permiso explícito implementados. M13 por orientación, vídeo de escritorio, reserva de foco V35, desafíos de renovación V26 y recuperación completa de MO-2 siguen pendientes. Sólo hay un monitor físico de 1920×1080 a 96 DPI disponible; la transformación con origen negativo tiene prueba unitaria, no aceptación física multimonitor.

La evidencia de builds y pruebas se guarda en `evidence/mobile-20261022/remote-control`. No se considera cerrado MO-4 ni terminado el indicador sin la prueba del ejecutable instalado, Android real y captura/grabación del resultado. Las pruebas de navegador usan un transporte aislado y se identifican como tales.
