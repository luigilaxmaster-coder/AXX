# Original User Request

## 2026-10-21T03:14:07Z

Usa el equipo completo con un único integrador. Mejora y reconstruye el funcionamiento de la aplicación de escritorio Axx existente (Tauri) de arriba abajo, apartado por apartado: ahora mismo la aplicación tiene un fallo funcional e interactivo total o casi total (al tocar el personaje/muñeco funciona fatal, y al tocar chat, dictar, música, grabar o cualquiera de las herramientas, nada funciona en ningún apartado). El objetivo es diagnosticar por qué las interacciones, eventos, clics/hit-testing, IPC/puentes Tauri-frontend-backend y módulos no responden o fallan, y rehacer/arreglar todo el funcionamiento e interacción de cada ventana, herramienta, personaje y detalle visual hasta lograr una app coherente, clara, fluida y realmente funcional de extremo a extremo, conservando la identidad visual aprobada (`reference\Axx_reference_v20.html`). No es una maqueta ni cambios cosméticos: todo debe funcionar de verdad al tocarlo.

Working directory: c:\Users\luigi\Desktop\Axx assistant
Integrity mode: development
HTML de referencia aprobado: `reference\Axx_reference_v20.html`

Decisiones del usuario:
- Estado actual crítico reportado por el usuario: al tocar chat, dictar, música, grabar y todas las herramientas, NADA funciona en ningún apartado; al tocar el muñeco/personaje funciona fatal. Hay que arreglar el funcionamiento de arriba abajo para que cada botón, herramienta, panel, arrastre, tentáculo y backend funcione realmente.
- Respaldo: el usuario ya tiene su propio respaldo (no crear copias ni git). Aun así, documentar cómo revertir cada cambio (lista de archivos modificados).
- Instalaciones: CERO. Compilar y probar en modo dev/portable; NO instalar. Si hace falta instalar, detenerse, conservar el trabajo preparado y pedir autorización. Un único integrador compila; no ejecutar instalaciones/compilaciones simultáneas ni sobrescribir trabajo ajeno (comprobar si otro proceso modifica el proyecto).
- Alcance: solo interfaz y módulos de escritorio (src-tauri, UI, backend de voz/música/grabación/temporizador/archivos). NO tocar Axx Connect (`evidence/axx-connect`, `plugins`, integraciones externas) salvo para resolver un bloqueo, documentándolo.
- Evidencia: capturas comparativas antes/después, vídeo corto de las interacciones realmente probadas, y pruebas de escala 100/125/150/200 % solo si el entorno lo permite (si no, marcar como pendiente; no cambiar la escala de Windows sin restaurarla).
- Orden de ataque: 1) arranque, bloqueos y por qué nada responde al clic/interacción (hit-testing, ventana transparente, eventos, conexión backend/IPC, personaje y menú radial), 2) ventanas movibles + tentáculos/recortes, 3) conversación y comandos, 4) voz/dictado/traducción, 5) grabación, temporizador y música, 6) archivos y configuración, 7) pulido visual y accesibilidad.
- Pruebas reales permitidas: micrófono, captura de pantalla y audio de prueba, guardando solo en una carpeta de evidencia; nada se envía a servicios externos reales sin avisar al usuario.
- Archivos reales: pueden probarse sobre las carpetas reales del usuario (Escritorio/Documentos) SOLO EN LECTURA. Cualquier escritura, borrado, movimiento o ejecución se prueba únicamente en una carpeta de pruebas dedicada, con confirmación para acciones destructivas.
- Parada (/goal): iterar hasta cumplir todos los criterios, aunque tarde muchas horas. Única excepción: bloqueo externo o necesidad de autorización (p. ej. instalar), donde se detiene y conserva el trabajo.

## Requirements

### R1. Auditoría previa, diagnóstico de fallo total e inventario (antes de modificar)
Localizar código real, HTML de referencia (`reference\Axx_reference_v20.html`) y versión instalada; revisar cambios pendientes y procesos activos (p. ej. instancias colgadas de Axx o backend Python que bloqueen puertos o la UI). Diagnosticar primero por qué al tocar el muñeco, chat, dictar, música, grabar y las herramientas no funciona nada. Inventario de TODOS los apartados existentes (personaje, menú radial, conversación, herramientas, dictado, traducción, música, grabación, temporizador, archivos, comandos, configuración, ventanas secundarias, menús, ayudas, estados de error) con: problema observado, causa comprobada o hipótesis, archivos implicados, corrección propuesta y prueba de aceptación. No inventar funciones ni causas sin inspección.

### R2. Identidad visual, personaje fluido y sistema de diseño
Mantener el personaje 3D de materia líquida, cromo oscuro iridiscente, sin rostro, con la silueta y paleta del diseño aprobado (`reference\Axx_reference_v20.html`), y las herramientas distribuidas radialmente alrededor del personaje (no bandeja rectangular, dashboard ni cuadrícula lateral). Hacer que la interacción con el personaje (clic, arrastre, apertura/cierre de menú radial, respuesta visual) sea inmediata, suave y sólida. Mejorar materiales, profundidad, reflejos, bordes, iluminación y transiciones sin perjudicar la lectura ni recargar. Definir y aplicar un sistema visual consistente (tipografía, tamaños, espaciados, radios, iconos, sombras, superficies, colores de estado) a todos los apartados y controles.

### R3. Ventanas movibles y redimensionables
Cada panel se abre al tocar su herramienta radial y se mueve y redimensiona de forma independiente de Axx y de los demás arrastrándolo desde su cabecera; mover un panel no arrastra al personaje ni a otras ventanas. Foco y z-order correctos; escribir, seleccionar texto, desplazar contenido o usar un botón nunca inicia un arrastre accidental; arrastre estable aunque el cursor salga del panel y cierre limpio si se pierde el foco. Tamaños mínimos útiles, adaptación del contenido y scroll interno. Conservar posición y tamaño por panel tras cerrar y reiniciar sin escribir en disco en cada fotograma. Recuperar ventanas dentro del área visible si cambia monitor/resolución/escala, y ofrecer opción clara para restablecer la distribución.

### R4. Tentáculos y recortes
Cada tentáculo permanece conectado al cuerpo y al punto de anclaje de su panel durante movimiento y redimensionado, ajustando longitud, curvatura y grosor con transiciones suaves y sin saltos al invertir dirección. Investigar y resolver recortes reales (límites de la ventana nativa, canvas, viewport, contenedores, máscaras, overflow, orden de capas) sin intentar corregir con CSS lo causado por límites de ventana nativa. Respetar áreas transparentes y paso de clics (click-through) al escritorio sin bloquear clics sobre Axx, el menú radial ni los paneles. Los tentáculos no tapan texto, no bloquean botones ni interceptan clics. Representación estática con movimiento reducido activado.

### R5. Simplificación por apartado sin quitar capacidades
Cada ventana responde claramente: para qué sirve, qué puedo hacer ahora y qué está ocurriendo. Una acción principal por contexto; opciones avanzadas en secciones desplegables; ayudas breves en vez de explicaciones permanentes repetitivas. Iconos comprensibles con etiquetas o tooltips, textos concretos y estados inequívocos diferenciados visualmente (reposo, escucha, procesamiento, ejecución, espera de autorización, éxito, cancelación, error) con animaciones distintas. Conversación minimalista (mensajes y barra principal para preguntas y comandos; proveedor, modelo y ajustes técnicos en un menú discreto). Mensajes de error claros sobre qué falló y qué hacer, sin secretos ni respuestas inventadas.

### R6. Funciones reconstruidas y verificadas de extremo a extremo
- Conversación y comandos: verificar y arreglar el recorrido completo desde la entrada hasta la herramienta y su resultado observable (no basta un mensaje del modelo); diferenciar capacidades realmente implementadas.
- Voz, dictado y traducción: estado real del micrófono y transcripción; cancelar sin enviar ni ejecutar resultado tardío; conservar original y traducción; no presentar «Hey Axx» ni escucha permanente como funcional si no está implementado y probado.
- Música: estado real de la fuente y controles reales de reproducción, pausa y siguiente donde estén disponibles; la animación no finge audio.
- Grabación: selección de área, indicador visible, tiempo, pausa, reanudación, parada y archivo final generado y verificado en disco.
- Temporizador: inicio, pausa, reanudación, cancelación y finalización con tiempo real exacto independiente de animaciones.
- Archivos y acciones: destinos, permisos, resultados, errores y cancelación verificados; sin ejecución indiscriminada de toda la biblioteca ni interpretación de texto de documentos como órdenes autorizadas.
- Configuración: cada ajuste cambia realmente el comportamiento correspondiente, persiste y puede restablecerse.

### R7. Ciclos acotados, rendimiento, accesibilidad y estabilidad
Trabajar apartado por apartado (capturar estado inicial y reproducir defectos → corregir estructura/funcionamiento/interacciones → refinar estética/legibilidad/jerarquía → probar casos normales/límites/errores → revisión independiente → corregir defectos y repetir pruebas). Priorizar fluidez, medir antes y después sin inventar cifras, evitar procesos duplicados, eventos sin liberar, repintados innecesarios y animaciones costosas en paneles ocultos. Comprobar navegación por teclado, foco visible, contraste, etiquetas accesibles, movimiento reducido, textos largos/idiomas, atajos existentes y parada de emergencia.

### R8. Evidencia y entrega
Probar cada panel al abrir, mover, redimensionar, superponer, cerrar, reabrir y reiniciar la aplicación, incluyendo errores, contenido vacío, cargas largas, pérdida de foco y cambios de resolución. Entregar lista de apartados corregidos, archivos modificados, capturas comparativas, vídeo breve de las interacciones realmente probadas y guía de reversión, separando pruebas automatizadas, manuales, simulaciones y pendientes.

## Acceptance Criteria

### Proceso
- [ ] Existe un inventario completo (todos los apartados de R1) con los cinco campos por apartado, creado ANTES de cualquier modificación.
- [ ] Un único integrador compila; ningún instalador ejecutado (verificable en logs); si hubo necesidad de instalar, el equipo se detuvo y lo reportó.
- [ ] Cada apartado tiene registro de ciclo: estado inicial capturado → corrección → prueba → revisión independiente por un agente distinto del implementador → defectos corregidos → pruebas repetidas.
- [ ] Ningún archivo de Axx Connect/plugins modificado sin justificación documentada.

### Funcional (revisión independiente con evidencia)
- [ ] Tocar el personaje, el menú radial y cada uno de los botones de herramientas (chat, dictar, traducción, música, grabar, temporizador, archivos, comandos, configuración) responde de inmediato y abre/ejecuta su panel y función real.
- [ ] Cada panel: abrir, mover, redimensionar, superponer, cerrar, reabrir y reiniciar app conserva posición/tamaño; mover un panel no mueve a Axx ni a otros paneles.
- [ ] Escribir, seleccionar texto, scroll y pulsar botones nunca inician arrastre; el arrastre continúa fuera del panel y termina al perder foco.
- [ ] Con monitor/resolución simulados distintos, ningún panel queda fuera del área visible; «restablecer distribución» funciona.
- [ ] Capturas durante mover/redimensionar muestran cada tentáculo conectado al cuerpo y al ancla, sin recortes por bordes de ventana, sin tapar texto ni bloquear clics (prueba de clic a través de zonas transparentes y sobre controles).
- [ ] Con movimiento reducido activado, los tentáculos son estáticos y las animaciones se detienen.
- [ ] Para cada función de R6 hay una prueba con resultado observable (archivo generado, tiempo real medido, estado de audio real, transcripción/traducción, comando ejecutado, ajuste persistido); ninguna función declarada exitosa por solo texto del modelo; controles decorativos = 0 o listados como pendientes.
- [ ] Grabación: el archivo final existe, tiene tamaño > 0 y se abre; temporizador: duración medida coincide con la configurada dentro de tolerancia documentada.
- [ ] Parada de emergencia y atajos existentes siguen funcionando (probados).

### Calidad
- [ ] Teclado: todos los controles alcanzables con foco visible; contraste y etiquetas comprobados y reportados.
- [ ] Mediciones de rendimiento antes/después reportadas (o marcadas como no medidas).
- [ ] Entregables: capturas comparativas, vídeo corto de las interacciones realmente probadas, lista de archivos modificados y guía de reversión.
- [ ] El informe final separa automatizado / manual / simulado / pendiente y NO declara «todo arreglado» si quedan fallos críticos o verificaciones pendientes.
