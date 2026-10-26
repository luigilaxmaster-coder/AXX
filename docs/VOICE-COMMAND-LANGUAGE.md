# Comprensión de voz y comandos de Axx

## Objetivo y alcance

Convertir distintas formas de pedir una acción en el mismo ID y parámetros
tipados, conservando lo que el usuario quiere buscar, abrir o escribir.
Transcripción acústica, interpretación y ejecución son etapas distintas: ver
texto no demuestra que se entendió la intención, y preparar una acción no
demuestra que Windows produjo el resultado.

Esta versión amplía la gramática determinista y los diagnósticos del resolvedor.
No entrena Whisper, no ajusta pesos ni instala modelos nuevos. El motor conserva
Base cuando está instalado localmente y Tiny como recurso del instalador.

## Flujo implementado

1. **Captura y final de turno:** el controlador existente captura audio y envía un
   fragmento final. Los resultados parciales no ejecutan acciones.
2. **ASR local:** Faster Whisper conserva el modelo cargado en un trabajador
   aislado. Mantiene límites de bytes, duración, salida y cancelación.
3. **Protección de contenido:** scripts y texto de escritura conservan sus
   argumentos. Negaciones, citas y preguntas informativas conservan sus palabras
   iniciales.
4. **Gramática:** una función pura e idempotente elimina cortesía y convierte
   variantes verbales en sintaxis canónica.
5. **Destinos:** los alias se aplican en posiciones de aplicación o buscador.
   Una palabra dentro de una canción, consulta o texto no se sustituye globalmente.
6. **Resolución:** el backend elige un ID registrado y parámetros. Las aplicaciones
   se contrastan con el inventario de Windows.
7. **Revisión y ejecución:** se conservan aprobaciones, permisos, identidad de
   ventana, modo de ejecución y cancelación.
8. **Comprobación:** el recibo y sus postcondiciones determinan el resultado.
   Abrir una búsqueda no acredita lectura de la página ni reproducción musical.

## Gramática y vocabulario

| Familia | Entrada | Resultado |
|---|---|---|
| Cortesía | «me puedes…», «podrías, por favor…», «oye, Axx…» | Conserva verbo y argumentos |
| Petición | «necesito que me abras…», «quiero abrir…», «quisiera buscar…» | abre…, busca… |
| Apertura | abrir, abrirme, ábreme, abras, lanza, arranca, inicia | Apertura del destino observado |
| Cierre/foco/lectura | cerrar, ciérrame, cierres, enfocar, leer | Acción sobre ventana observada |
| Búsqueda | búscame, buscarme, busques, «en YouTube busca…», «usando Google» | Buscador y consulta separados |
| Sinónimo con destino | «encuentra X en YouTube» | Búsqueda en YouTube |
| Música | «quiero escuchar X en Spotify» | Búsqueda dirigida a Spotify |
| Sesión multimedia | «pon Spotify en pausa», «necesito que pauses Spotify» | Control de sesión de Spotify |
| Mouse | «puedes moverme el mouse a 100 y 200» | Coordenadas enteras, sin inferir clic |
| Nombres | you tube, chat gpt; en voz, yutube, espotifai, obsedia | Alias de destino acotados |

«Localiza X» sin buscador explícito no se fuerza a búsqueda web. Las peticiones
compuestas mantienen el planificador de tareas y su revisión; esta capa no
fragmenta libremente una frase para ejecutar cada parte.

## Ejecutar, sugerir o preguntar

Los errores conocidos de dictado se habilitan sólo con origen voice: Bosca puede
normalizarse a busca y Reprogoce a reproduce. El chat escrito no recibe estas
sustituciones fonéticas.

Si el verbo es desconocido pero se parece a uno conocido, se ofrece una
sugerencia: «puedes sabrirme Spotify» → «¿Quisiste decir abre Spotify?».
La similitud de caracteres exige mínimo 0,85 y separación mínima 0,12 entre
acciones candidatas. Son umbrales heurísticos, **no probabilidades de certeza**.
La respuesta es needs_input, con execution_allowed: false; no prepara operaciones.

Las aplicaciones conservan el umbral de similitud 0,80. Si dos nombres observados
quedan a menos de 0,15, se devuelven los candidatos cercanos. Una similitud léxica
no demuestra controles disponibles, permiso de lectura ni un efecto ejecutado.

No deben abrir ni cerrar aplicaciones:

- «No abras Spotify».
- «Quiero que no cierres Spotify».
- «Explícame cómo abrir Spotify».
- «Di abre Spotify».
- Una cita literal como «"abre Spotify"».

«Busca cómo no cerrar Spotify en Google» sigue siendo una búsqueda. El texto de
escritura, el uso de mayúsculas en URLs y las consultas citadas conservan su
contenido. La cortesía final en búsquedas se retira sólo si está separada con coma,
para no convertir «busca por favor» en una búsqueda vacía.

## Contrato de interpretación

POST /axx-api/commands/resolve conserva su contrato. Cuando cambia la sintaxis,
añade metadatos; por ejemplo:

    {
      "match": "exact",
      "command_id": "axx.desktop.search",
      "inputs": {"engine": "youtube", "query": "gatos"},
      "understanding": {
        "method": "bounded_grammar",
        "canonical": "busca gatos en youtube",
        "asr_correction_allowed": true
      }
    }

Exact significa que la gramática eligió un comando; no expresa certeza acústica
de 100 %. Resolve no ejecuta. El frontend envía texto original y procedencia;
el backend conserva la autoridad semántica. La comprobación de palabras del
frontend sólo selecciona la ruta y los controles internos existentes.

No se escriben audios ni transcripciones adicionales en logs por esta
normalización. La interpretación devuelta no constituye entrenamiento ni memoria
permanente.

## Exactitud acústica y rendimiento

Se compararon el contexto actual de Whisper y dos alternativas con audio
sintético español de MOSS. Algunas corrigieron And Chrome o Bosca, pero no
mejoraron consistentemente nombres y peticiones musicales. Se conserva el
contexto actual. La gramática no repara sonido que el modelo no reconoció.

Se corrigió además una acumulación del trabajador persistente: la protección de
importaciones nativas se instala una vez, en vez de añadir un objeto nuevo en
cada turno. Una prueba verifica esa invariante. Cancelar sigue descartando el
trabajador activo.

La gramática no llama a otro modelo. Deben medirse por separado:

- Última voz → cierre del segmento.
- Segmento → transcripción final.
- Transcripción → ID y parámetros.
- Preparación → efecto comprobado.
- Última voz → primer audio útil.

La meta de dos segundos pertenece a la última medida. ASR rápido o una coletilla
temprana no demuestran su cumplimiento.

## Evaluación y siguientes criterios

El corpus de desarrollo compara aperturas y búsquedas contra el resolvedor
anterior, además de negación, literalidad, ambigüedad, transporte y ausencia de
efectos al interpretar. Se usó al desarrollar la gramática; no es una evaluación
independiente de generalización.

Comparación local con la base publicada 0.22.0: aperturas, 2/13 → 13/13;
búsquedas, 1/10 → 10/10. En 2.300 normalizaciones de esas frases, la función pura
midió p50 0,010 ms y p95 0,019 ms. Esto no incluye ASR, inventario de Windows,
planificación, ejecución ni audio de respuesta.

La evaluación física requiere frases nuevas del usuario, varias distancias al
micrófono, ruido habitual y nombres reales de sus aplicaciones. Debe medir error
de palabras, acierto de intención, exactitud de parámetros, acciones no solicitadas,
aclaraciones y latencia p50/p95. Audio bruto se conserva sólo por decisión explícita.

Un ASR mayor, una segunda transcripción o una corrección mediante LLM son candidatos
futuros. No se activan aquí: añaden consumo y demora y requieren comparación
independiente, incluida preservación de negaciones y abstención ante ambigüedad.

## Implementación y comprobación

- backend/actions/command_language.py: gramática, alias y sugerencias.
- backend/actions/desktop.py: destinos y acciones tipadas.
- backend/actions/windows_apps.py: candidatos observados.
- backend/commands.py: integración y metadatos.
- 1.AXX/scripts/command-library.js: ruta del chat y paráfrasis multimedia.
- backend/speech/offline_asr.py: trabajador local persistente.
- backend/tests/test_command_language.py: resultados y contenido protegido.

Desde la raíz:

    python -m unittest backend.tests.test_command_language backend.tests.test_commands_http backend.tests.test_speech_text -q
    node 1.AXX/scripts/test-command-library.cjs
    node 1.AXX/scripts/test-desktop-frontend.cjs

La aceptación instalada y el hash se registran por versión en docs/releases.
Las pruebas sintéticas no sustituyen el micrófono físico.
