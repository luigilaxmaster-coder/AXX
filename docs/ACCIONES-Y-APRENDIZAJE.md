# Acciones reales y aprendizaje de Axx

Las peticiones reconocidas llegan al ejecutor de Windows antes del chat. Por ejemplo:

- `abre youtube y búscame un vídeo de gatitos`
- `/search youtube afraid`
- `busca afraid` conserva el buscador abierto en esta sesión.
- `abre` seguido del nombre de una aplicación instalada; `mis aplicaciones` muestra los nombres disponibles.

Una búsqueda abre los resultados en el navegador. La aceptación de Windows no certifica que la página haya cargado ni que un vídeo esté reproduciéndose.

## Acciones nuevas

Cuando Axx no reconoce una petición de acción, consulta el modelo seleccionado. También se puede usar `/aprende <petición>`. El modelo propone hasta ocho pasos con las herramientas existentes; Axx valida sus parámetros y muestra el plan antes de ejecutarlo.

Tras pulsar **Aprobar y ejecutar**, el ejecutor realiza cada paso y comprueba su resultado. Si alguno falla, se detiene y conserva los resultados de los pasos anteriores. No guarda el plan como aprendido. Cancelar tampoco deshace pasos ya realizados.

Si todos los pasos se verifican, Axx guarda la acción en su base SQLite local. Se puede repetir la petición original, usar `/accion <nombre>` o elegirla en **Mis acciones aprendidas** (`/acciones`). Las repeticiones usan los pasos guardados sin otra llamada al modelo y vuelven a mostrar los parámetros para revisión. Las rutas y contenidos son valores concretos; cambiar la petición no cambia silenciosamente una acción guardada.

Las respuestas del modelo no son comprobantes de ejecución. No pueden habilitar herramientas inventadas, ejecutar scripts de PowerShell ni convertir instrucciones importadas en código. El comando explícito `/powershell` conserva su flujo separado de texto escrito y aprobación.

## Instrucciones importadas

`resources/procedure-library.zip` contiene 7.566 procedimientos completos de la carpeta **Instrucciones Axx**: todos los 7.562 registros anteriores y cuatro adicionales. Se inventariaron 1.078 archivos de contenido, con hashes en `evidence/action-instructions-20261022/source-audit.json`. Las revisiones marcadas como borrador se excluyen; el estado de ejecución de un documento nunca otorga permisos.

La biblioteca muestra requisitos, pasos, comandos de referencia, comprobaciones y recuperación. La planificación puede consultar procedimientos relevantes. Los procedimientos de SHA256 y comparación de archivos tienen implementaciones locales; los demás solo se ejecutan si pueden expresarse con las herramientas realmente disponibles. Importar instrucciones no instala ni automatiza por sí solo Word, CAD, editores u otros programas.

## Comprobación

Las funciones propias se controlan por texto o desde **Orden voz** (`Alt+Mayús+V`): «abre chat», «abre dictar», «empieza a dictar», «termina el dictado», «abre grabar», «graba la pantalla», «pausa/reanuda/finaliza la grabación», «pausa/continúa la música», «inicia/pausa el cronómetro» y «inicia/pausa/cancela el temporizador». «Abre» muestra el apartado; «empieza» activa su controlador. También se reconoce «abre» seguido del nombre completo de cualquier función del catálogo de Axx.

Estas órdenes usan los mismos controladores que los botones y tienen prioridad sobre el buscador de Windows y el modelo. Despiertan la interfaz cuando está aparcada. Dictar conserva el permiso de micrófono y el destino de texto; si falta un campo visible, ofrece el bloc local. Grabar abre el selector de área. La música depende de los controles que publique el reproductor en Windows. Los requisitos pendientes o errores no se anuncian como ejecución completada. La escucha de órdenes es puntual, sin escucha permanente; el dictado normal escribe texto y no lo convierte en órdenes.

- Backend: `py -3.14 -m unittest discover -s backend/tests -q`.
- Interfaz y condiciones de aprobación: `node 1.AXX/scripts/test-command-library.cjs`.
- Funciones propias y entrada de voz con HTML completo: `node 1.AXX/scripts/test-internal-actions.cjs` (IPC y micrófono controlados; no prueba de reconocimiento acústico).
- HTML completo, modelo de prueba, backend empaquetado y efectos reales: `node 1.AXX/scripts/test-action-learning.cjs`.
- Prueba con proveedor real: `scripts/verify_live_action_model.py`; solo admite ejecutar la creación exacta de un archivo de prueba en una carpeta temporal.

La prueba real con Ollama Cloud y `gpt-oss:120b` produjo un plan válido, creó el archivo, verificó el contenido y guardó la acción. No certifica que todos los modelos produzcan planes correctos para cualquier tarea.
