# Movimiento instalado de Axx 0.20.4

Fecha: 19 de octubre de 2026. Estado: **VALIDADO_WINDOWS para el desplazamiento y la animación observados**.

## Resultado comprobado

El ejecutable instalado `C:\Users\luigi\AppData\Local\Programs\Axx\Axx.exe`, PID 25976, mostró únicamente el cuerpo del avatar en una ventana transparente compacta y se desplazó de forma autónoma. El operador de la prueba observó mediante Sky deformación visible del cuerpo y dos posiciones posteriores distintas de la ventana: `(3366,505)` y `(3301,483)`, conservando un tamaño de `304×304`.

La preferencia anterior `reducedMotion:true` bloqueaba el movimiento. El operador la desmarcó mediante la interfaz normal: enfocó el control y pulsó Espacio; después cerró el panel sin usar Esc, que detiene el paseo. Esta revisión de evidencia no modificó fuentes, preferencias, procesos ni la interfaz.

## Evidencia nativa

`installed-motion-after-enable.json`, capturado a las **2026-10-19T23:39:03.162Z**, registra:

| Campo | Valor observado |
|---|---|
| Versión y PID | `0.20.4`, `25976` |
| Backend y superficie | `backendReady:true`, `desktop.ready:true`, `windowVisible:true` |
| Movimiento | `mode:roam`, `roam:true`, `pinned:false`, `reducedMotion:false` |
| Desplazamiento confirmado | `automaticSteps:1`, `roamSteps:1` |
| Posición real de ventana | `x:3338`, `y:511` |
| Ancla actual | `3489.525839929346, 663.1596725296312` |
| Base manual | `3488.798625063489, 663.0` |
| Tamaño y escala | `304×304` CSS px, escala `1.0` |

El contador aumenta únicamente tras una operación de posicionamiento exitosa y una lectura de posición nativa distinta. El archivo es un checkpoint de arranque/cambio de estado/primer paso, no una telemetría escrita en cada frame; las dos observaciones posteriores de Sky acreditan que el desplazamiento continuó.

La lectura de `C:\Users\luigi\AppData\Local\Axx\native-window.json` mantuvo la base guardada en `3488.798625063489,663.0` en `DISPLAY2`. El paseo observado no sobrescribió esa base manual.

## Persistencia comprobada en lectura

Consulta SQLite con `mode=ro`, limitada a la fila `identity_preferences.key='axx-studio-v2'` de `C:\Users\luigi\AppData\Local\Axx\state.db`:

- Versión de identidad: `12`; actualización: `2026-10-19T23:38:52.570964+00:00`.
- `settings.reducedMotion:false`.
- `settings.staticMode:false`.
- `studio.living:true`.
- `layout['axx.resident-motion-v1']` ausente: no existe una copia persistida específica de ese ajuste en esta fila. El estado nativo comprobado confirma que el paseo estaba habilitado y la posición no estaba fijada.

## Fuentes de evidencia

- `evidence/resident-20261019/installed-runtime.json`: instalación y arranque del ejecutable instalado, backend descendiente y respuesta HTTP 401 sin autorización.
- `evidence/resident-20261019/installed-motion-before-enable.json`: estado anterior, con movimiento reducido y cero pasos automáticos.
- `evidence/resident-20261019/installed-motion-after-enable.json`: checkpoint del primer desplazamiento físico confirmado.
- `C:\Users\luigi\AppData\Local\Axx\logs\native-runtime.json`: diagnóstico local del host, sin tokens ni contenido de conversaciones.
- Dos observaciones visuales posteriores mediante Sky, informadas por el operador de la prueba. No se generó una grabación de vídeo.

## Límites

- No se midieron FPS, latencia ni rendimiento sostenido.
- Esta prueba no valida micrófono, altavoces, cámara ni otros periféricos físicos.
- No constituye una validación exhaustiva del click-through en todas las formas, paneles, monitores o aplicaciones.
- El código limita el objetivo del paseo a 64 CSS px de su centro efímero y la velocidad a 22 CSS px/s. Un clamp al abrir paneles puede desplazar temporalmente el ancla fuera de ese círculo antes de su retorno; esta sesión no midió exhaustivamente ese caso.
- Las fuentes y los binarios permanecen congelados; este informe añade únicamente evidencia documental.
