# Axx 20 · Próximas actualizaciones

Esta lista es un plan; no habilita capacidades ni permisos nuevos. Las tareas marcadas FUTURO no se consideran implementadas porque aparezcan en una interfaz.

## Prioridad P0: comprobación del equipo real

Abrir el mismo servidor/origen en Windows, guardar forma/estilo, cerrar, reabrir, navegar por todas las herramientas y comprobar persistencia real sin fixtures. Validar micrófono, ruido, motor de traducción, permiso de pantalla, carpeta real, apertura de aplicaciones e instalación de extensión. Medir una sesión de al menos 30 minutos con música, dictado y paneles sin apagar el renderer en el test.

Ampliar accesibilidad: zoom 200–400 %, lector de pantalla, foco al cerrar, alto contraste, teclado virtual y recuperación multimonitor. Las medidas comprobadas en esta entrega no equivalen a cubrir todas las combinaciones.

## Hey Axx — FUTURO · NO ACTIVO

**Objetivo:** con el proyecto ejecutándose, decir «Hey Axx», recibir una señal de escucha, pedir una acción sin tocar y escuchar una respuesta. Devolverlo a reposo después, sin abrir Herramientas obligatoriamente.

### Flujo propuesto

```text
Activar manos libres explícitamente
→ detector de palabra de activación
→ “Hey Axx” detectado
→ señal visible/sonora permitida
→ ventana corta de reconocimiento de la orden
→ validar capacidad y destino
→ ejecutar una orden permitida o pedir confirmación
→ respuesta por voz y estado real
→ vuelta a reposo
```

El detector debe ser un componente intercambiable del runtime, preferentemente local. Antes de elegirlo se evaluarán precisión, falsos positivos, idiomas, consumo, licencia y soporte Windows. No se incluye una dependencia de voz inventada ni se instala un modelo silenciosamente.

### Reglas de implementación

- Desactivado por defecto. Configuración explícita del micrófono, indicador siempre visible y un interruptor para detener la escucha. Cerrar la aplicación debe liberar los recursos que le pertenezcan.
- Separar detector, reconocimiento de orden, motor de respuestas, síntesis, control de tareas y permisos. No reinterpretar frases de música, vídeos o documentos como órdenes autorizadas.
- La palabra de activación no autentica al usuario. Identificar una voz no será una contraseña ni permiso para borrar, enviar, pagar o ejecutar un comando arbitrario.
- Comandos iniciales acotados: llamar, volver, pausar/continuar actividad conocida, temporizador, notas, leer y dictar a un destino explícito. Envío de mensajes y acciones externas sensibles requieren una autorización específica.
- Controlar eco, salida de Axx y mezcla de música. Las interrupciones de voz y funcionamiento de audio bidireccional necesitan pruebas de latencia reales, no un bucle de respuestas predefinidas.
- Tiempo máximo de escucha por orden, cancelación, desconexión de dispositivo y recuperación de permisos. Nada de escucha indefinida invisible por un error.
- No enviar audio a un proveedor remoto sin informar y obtener permiso. Preservar el modo de pulsar para hablar como alternativa.

**Aceptación:** invocar con voz desde otra aplicación permitida, escuchar una orden real, pausar y continuar una tarea existente, pedir aprobación para enviar texto, decir cancelar, retirar el permiso y comprobar que no quedan capturas. Medir falsos disparos, latencia, ruido y consumo con hardware físico.

## Otras líneas de mejora

| Prioridad | Trabajo | Criterio de aceptación |
|---|---|---|
| P1 | Overlay y atajos globales reales | Invocar/volver desde otra aplicación, varios monitores, sin rectángulos que bloqueen clics. |
| P1 | Inserción fuera de Axx | Adaptador de pestaña o nativo autorizado, selección y conflicto protegidos, sin envío accidental. |
| P1 | Escritura continua y recuperación de grabaciones | Guardar fragmentos durables sin retener todo el vídeo en RAM; recuperar tras cierre imprevisto. |
| P1 | Captura/halo nativos | Perímetro del monitor correcto y exclusión de la captura cuando la API lo permita. |
| P1 | Validación musical externa | OAuth/dispositivo Spotify, vídeo YouTube y extensión instalados realmente; no confundir contratos con sesiones reales. |
| P1 | Transcripción audiovisual y voz bidireccional | ASR real con tiempos y errores medidos; interrupción de voz y subtítulos generados desde audio. |
| P2 | Fusión artística de torso y brazos | Unión geométrica continua y colisiones sin perforar paneles; no solo continuidad de color. |
| P2 | Galería/gestos más amplia | Formas nuevas distinguibles y transiciones revisadas desde varias orientaciones, manteniendo el estilo aprobado. |
| P2 | Ajuste visual por actividad | Presets explícitos, nunca una modificación silenciosa de la identidad del usuario. |
| P2 | Worker de rasterizado | Menos bloqueo del hilo de UI con el mismo fotograma; demostrar beneficio antes de sustituir el motor. |

Los nuevos estilos y formas de Axx 20 sí son parte del HTML; esta lista no los vuelve a presentar como trabajo futuro.
