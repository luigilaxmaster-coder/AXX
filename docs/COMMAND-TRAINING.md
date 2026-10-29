# Práctica y aceptación de comandos

Los escenarios reproducibles ejercitan reconocimiento, planificación, aprobación,
ejecución y comprobación. Cada caso exige un resultado observable; una respuesta
del modelo o un catálogo válido por sí solos no acreditan una acción realizada.

| Serie | Casos | Criterio |
| --- | --- | --- |
| Entrada rápida | Intro, botón Enviar, segunda orden, cierre de otro panel, tarea pendiente y borrador | Un envío por gesto. Conserva el foco para la siguiente orden. Un bloqueo muestra su motivo en el widget y conserva el texto. |
| Lenguaje | «y», «luego», «después,», comas, líneas y «primero» | Mantiene cláusulas y orden; no incorpora el segundo mandato al buscador del primero. |
| Contenido literal | Comillas, apóstrofos, negación y texto para escribir | Las palabras de un texto no conceden autoridad para ejecutar otras órdenes. La cláusula de escritura conserva su contenido restante. |
| Planificación | Parámetros ausentes y secuencia nueva | El proveedor seleccionado recibe las cláusulas completas y las herramientas disponibles. |
| Autocorrección | Acciones omitidas, parámetros inválidos o respuesta sin JSON | El modelo recibe las restricciones del ejecutor y puede corregir una vez, dentro del presupuesto existente de dos inferencias. Si sigue inválido o incompleto, ningún paso se ejecuta. |
| Resultado final | Comprobación inventada, texto contradictorio y archivo enlazado al paso previo | Rechaza comprobaciones sin archivo declarado antes de ejecutar; conserva la evaluación independiente del contenido. Un enlace completo permite omitir inputs vacío sin inventar valores. |
| Ejecución | Escritura de prueba, fallo intermedio, tercera acción | El tercer efecto no ocurre tras el fallo. Consultar o repetir el ID no vuelve a ejecutar efectos. |
| Aislamiento | Cambio de chat, cancelación y pérdida de respuesta | Conserva origen, parámetros y recibos; no convierte incertidumbre en éxito. |
| Windows | Clic inicial sobre barra transparente y arrastre | Ajusta la recepción antes de entregar el clic. Fuera de Axx se conserva el paso al escritorio. |

## Repetición local

Desde la raíz del repositorio, con las dependencias del proyecto instaladas:

```powershell
python -m unittest backend.tests.test_command_language backend.tests.test_command_sequences backend.tests.test_action_learning backend.tests.test_commands_http
node 1.AXX/scripts/test-command-library.cjs
node scripts/test-quick-reply.cjs
cargo test --manifest-path src-tauri/Cargo.toml --lib
```

Los tests de Python usan archivos temporales. Las pruebas de navegador usan
contratos controlados y no accionan las aplicaciones del usuario. Los resultados
de Windows se guardan aparte en los recibos privados de `build/release-*`.

## Aceptación instalada

1. Abrir Escribir y enviar una consulta de lectura desde la barra pequeña.
2. Verificar tanto Intro como el botón y observar la respuesta compacta.
3. Enviar la secuencia autorizada de abrir YouTube y buscar Faint de Linkin Park.
4. Revisar sus dos parámetros, aprobar el plan concreto y comprobar sus recibos
   ordenados. Apertura de enlace, contenido visible y reproducción son resultados
   diferentes.
5. Mantener la publicación en borrador si falla la instalación o esta aceptación.

La comprobación del número de pasos detecta omisiones simples; no demuestra por
sí sola que el modelo entendió todo el objetivo. Se conservan los esquemas,
aprobaciones, límites, postcondiciones y revisión del resultado. No se garantiza
la disponibilidad permanente de modelos o aplicaciones externas.

La recepción selectiva sigue la política de ventanas por capas de
[Windows](https://learn.microsoft.com/en-us/windows/win32/winmsg/window-features).
El callback de ratón usa el hilo de mensajes existente, no guarda contenido y
siempre continúa la cadena descrita por
[LowLevelMouseProc](https://learn.microsoft.com/en-us/windows/win32/winmsg/lowlevelmouseproc).
