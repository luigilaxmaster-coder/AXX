/* Safe, reusable speech text. Audio is generated privately on this PC. */
const AXX_VOICE_PHRASE_GROUPS = {
    greeting: [
        'Hola, señor. Aquí estoy.', 'Buenas, señor. Te escucho.', 'Hola. ¿Qué quieres hacer hoy?', 'Aquí estoy. Dime qué necesitas.', 'Buenas tardes. Te escucho.',
        'Buenos días. ¿En qué te ayudo?', 'Buenas noches. Aquí estoy.', 'Hola de nuevo. Te escucho.', 'Qué bueno escucharte. ¿Qué necesitas?', 'Hola. Podemos empezar cuando quieras.'
    ],
    opening: [
        'Cuéntame lo que tienes en mente.', 'Dime por dónde quieres empezar.', 'Podemos resolverlo paso a paso.', 'Si tienes una idea, dímela tal como salga.', 'Estoy lista para escuchar tu pregunta.',
        'Dime qué resultado buscas.', 'Vamos con lo que más te importe ahora.', 'Puedes explicármelo con tus propias palabras.', 'Dime el objetivo y revisamos el camino.', 'Empecemos por la parte más urgente.'
    ],
    gratitude: [
        'De nada, señor.', 'Con gusto.', 'Me alegra que te sirva.', 'Cuando quieras, seguimos.', 'Gracias por decírmelo.',
        'Perfecto. Aquí sigo.', 'Me alegra haber ayudado.', 'Claro. Seguimos cuando quieras.', 'Para eso estoy aquí.', 'Gracias a ti.'
    ],
    farewell: [
        'Hasta luego, señor.', 'Nos vemos cuando quieras.', 'Que te vaya bien.', 'Aquí estaré cuando vuelvas.', 'Hablamos luego.',
        'Que tengas buen día.', 'Hasta la próxima.', 'Cuídate, señor.', 'Seguimos después.', 'Nos vemos pronto.'
    ],
    general_lead: [
        'Déjame revisar eso.', 'Un momento, lo reviso.', 'Voy a ordenar la respuesta.', 'Dame un instante para pensarlo.', 'Reviso los detalles.',
        'Voy con esa pregunta.', 'Déjame comprobar el contexto.', 'Un segundo, lo preparo.', 'Estoy revisando tu solicitud.', 'Voy a responderte con precisión.'
    ],
    search_lead: [
        'Revisaré qué información tengo disponible.', 'Voy a comprobar esa información.', 'Déjame buscar una respuesta útil.', 'Revisaré las fuentes disponibles.', 'Un momento, voy a consultar eso.',
        'Voy a verificar el dato.', 'Déjame contrastar esa información.', 'Voy a revisar lo que se sabe.', 'Un segundo, busco el dato.', 'Revisaré antes de darte una respuesta.'
    ],
    analysis_lead: [
        'Voy a analizarlo paso a paso.', 'Déjame revisar los datos.', 'Haré la cuenta con cuidado.', 'Voy a comprobar los números.', 'Un momento, reviso el razonamiento.',
        'Ordenaré las opciones primero.', 'Déjame comparar los resultados.', 'Voy a separar los puntos clave.', 'Revisaré las condiciones.', 'Un segundo, analizo el caso.'
    ],
    writing_lead: [
        'Voy a preparar un borrador.', 'Déjame ordenar el texto.', 'Voy a escribir una versión clara.', 'Revisaré el tono que necesitas.', 'Un momento, preparo el mensaje.',
        'Voy a pulir esa redacción.', 'Déjame estructurar la idea.', 'Prepararé una respuesta breve.', 'Voy a escribirlo con tus indicaciones.', 'Revisaré la claridad del texto.'
    ],
    translation_lead: [
        'Voy a traducirlo con cuidado.', 'Revisaré el sentido antes de traducir.', 'Un momento, preparo la traducción.', 'Voy a mantener el tono original.', 'Déjame comprobar los matices.',
        'Traduciré la idea completa.', 'Voy a revisar el idioma de destino.', 'Prepararé una versión natural.', 'Déjame ajustar la expresión.', 'Voy a comparar ambas versiones.'
    ],
    browser_lead: [
        'Voy a revisar la página que mencionas.', 'Déjame comprobar la dirección.', 'Voy a preparar la navegación.', 'Revisaré qué página necesitas.', 'Un momento, verifico el enlace.',
        'Voy a buscar el sitio correcto.', 'Déjame revisar esa pestaña.', 'Comprobaré la ruta de navegación.', 'Voy a preparar la búsqueda web.', 'Revisaré la página antes de responder.'
    ],
    music_lead: [
        'Voy a revisar lo que pides de la música.', 'Déjame identificar la canción.', 'Revisaré el control de reproducción.', 'Voy a comprobar la aplicación de música.', 'Un momento, reviso el título.',
        'Déjame distinguir artista y canción.', 'Voy a verificar el reproductor.', 'Revisaré dónde está sonando.', 'Voy a preparar esa búsqueda musical.', 'Déjame comprobar el estado de la música.'
    ],
    desktop_lead: [
        'Voy a revisar la aplicación indicada.', 'Déjame comprobar la ventana.', 'Voy a identificar el control correcto.', 'Revisaré qué hay abierto.', 'Un momento, localizo la aplicación.',
        'Voy a comprobar el escritorio.', 'Déjame revisar la ventana activa.', 'Revisaré la acción antes de hacerla.', 'Voy a confirmar el objetivo en pantalla.', 'Déjame identificar dónde debo actuar.'
    ],
    terminal_lead: [
        'Voy a preparar el comando para revisión.', 'Déjame comprobar los argumentos.', 'Revisaré el comando antes de ejecutarlo.', 'Voy a verificar la ruta indicada.', 'Un momento, preparo la instrucción.',
        'Déjame revisar el efecto del comando.', 'Voy a dejar la instrucción lista para revisar.', 'Comprobaré la sintaxis primero.', 'Revisaré qué resultado debe producir.', 'Voy a separar la orden de su explicación.'
    ],
    file_lead: [
        'Voy a revisar el archivo indicado.', 'Déjame comprobar la carpeta.', 'Revisaré la ruta del archivo.', 'Voy a identificar el documento.', 'Un momento, compruebo el nombre.',
        'Déjame revisar el contenido disponible.', 'Voy a buscar el archivo correcto.', 'Comprobaré qué formato tiene.', 'Revisaré antes de modificarlo.', 'Voy a preparar la lectura del archivo.'
    ],
    clarify: [
        '¿A qué archivo te refieres?', '¿Qué aplicación quieres usar?', '¿Qué canción quieres escuchar?', '¿En qué carpeta debo buscar?', '¿Qué página quieres abrir?',
        '¿Cuál de las dos opciones prefieres?', '¿Qué parte quieres que cambie?', '¿Qué resultado esperas ver?', '¿Puedes decirme el nombre exacto?', '¿Quieres que lo abra o que lo cierre?'
    ],
    listen_retry: [
        'No entendí la última palabra. Repítela, por favor.', 'Escuché solo una parte. Dímelo otra vez.', 'La frase quedó cortada. ¿Puedes repetirla?', 'No distinguí el nombre de la aplicación.', 'No distinguí el título de la canción.',
        'El dictado se interrumpió. Puedes repetirlo.', 'No entendí el lugar que mencionaste.', 'Esa palabra salió confusa. ¿Cuál era?', '¿Puedes hablar un poco más cerca del micrófono?', 'Escuché dos opciones. ¿Cuál querías?'
    ],
    approval: [
        'La acción está lista para que la revises.', 'Revisa los detalles antes de aprobar.', 'El comando está preparado, pendiente de tu aprobación.', 'Puedes comprobar el destino antes de continuar.', 'La vista previa está lista para revisar.',
        'La ejecución espera tu decisión.', 'Revisa el contenido antes de guardarlo.', 'Puedes aprobarlo cuando estés conforme.', 'El cambio todavía no se ha aplicado.', 'Confirma la acción en la tarjeta cuando quieras.'
    ],
    completion: [
        'La operación terminó correctamente.', 'El resultado está listo para revisar.', 'La acción se completó y quedó registrada.', 'La aplicación se abrió correctamente.', 'La ventana se cerró correctamente.',
        'El archivo se guardó correctamente.', 'La reproducción se reanudó.', 'La música quedó en pausa.', 'La búsqueda se abrió en el navegador.', 'El comando terminó y ya puedes ver su resultado.'
    ],
    incomplete: [
        'La acción no terminó; revisaré el motivo.', 'No puedo confirmar el resultado todavía.', 'La operación se detuvo antes de completarse.', 'El resultado quedó pendiente de comprobación.', 'La aplicación no respondió a tiempo.',
        'La ventana cambió mientras intentaba actuar.', 'La ruta indicada no estaba disponible.', 'La solicitud se canceló sin aplicar cambios.', 'No recibí confirmación del ejecutor.', 'Necesito comprobar el estado antes de repetirlo.'
    ],
    unavailable: [
        'Esa función no está disponible en este momento.', 'El servicio de voz no respondió; puedes leer la respuesta.', 'No encontré esa aplicación instalada.', 'No encontré el archivo con ese nombre.', 'La ventana indicada ya no está abierta.',
        'El dispositivo de audio no está disponible.', 'No pude acceder a esa página.', 'La conexión necesaria no está lista.', 'El modelo seleccionado no respondió.', 'No pude completar la acción; revisaré otra forma.'
    ],
    voice: [
        'Puedes probar esta voz desde el panel.', 'La velocidad se puede ajustar a tu gusto.', 'El sonido se puede hacer más cálido o más claro.', 'Los cambios de voz se aplican al reproducir.', 'Puedes volver al sonido natural cuando quieras.',
        'La muestra original permanece intacta.', 'Esta voz usa las muestras guardadas en tu equipo.', 'La primera frase puede tardar mientras se prepara el modelo.', 'Las frases ya preparadas se reproducen más rápido.', 'Puedes comparar español e inglés en el panel.'
    ],
    privacy: [
        'Tus muestras de voz permanecen en este equipo.', 'El audio original no se publica con Axx.', 'Puedes borrar las muestras locales cuando quieras.', 'La transcripción se realiza localmente cuando está disponible.', 'Revisaré los permisos antes de usar el micrófono.',
        'No enviaré una acción sin tu aprobación cuando se requiera.', 'No guardaré una grabación sin que lo decidas.', 'La voz se procesa con el motor seleccionado.', 'Puedes desactivar la respuesta hablada.', 'Tu configuración de voz se guarda en este perfil.'
    ],
    help: [
        'Puedo ayudarte a escribir, buscar y organizar tareas.', 'Puedes pedirme que abra una aplicación por su nombre.', 'Puedes dictar una orden y revisar lo que entendí.', 'Puedo leer en voz alta una respuesta.', 'Puedes pedirme que pause o reanude la música.',
        'Puedo preparar un comando para que lo apruebes.', 'Puedes pedirme que revise un archivo.', 'Puedo ayudarte a comparar dos opciones.', 'Si una acción falla, revisaré el motivo.', 'Dime qué quieres lograr y buscaré la forma.'
    ],
    english_greeting: [
        'Hello. I am here.', 'Good morning. I am listening.', 'Good afternoon. How can I help?', 'Good evening. I am here.', 'Hello again. What do you need?',
        'I am ready when you are.', 'Tell me what you have in mind.', 'We can take it step by step.', 'Where would you like to start?', 'Hello. Let us begin.'
    ],
    english_lead: [
        'Let me check that.', 'I will review the details.', 'One moment, I am looking into it.', 'Let me compare the options.', 'I will prepare a clear answer.',
        'I will check the information first.', 'Let me organize the response.', 'I will review the file you mentioned.', 'I will check the application.', 'One moment, I am working through it.'
    ]
};
const AXX_VOICE_PHRASES = Object.entries(AXX_VOICE_PHRASE_GROUPS).flatMap(([context, texts]) => {
    if (texts.length !== 10) throw new Error('Each voice context needs ten phrases: ' + context);
    return texts.map((text, index) => ({ id: context + '-' + String(index + 1).padStart(2, '0'), context,
        language: context.startsWith('english_') ? 'en' : 'es', text }));
});
if (AXX_VOICE_PHRASES.length !== 250 || new Set(AXX_VOICE_PHRASES.map(item => item.text)).size !== 250)
    throw new Error('Voice phrase catalog must contain 250 distinct phrases: ' + AXX_VOICE_PHRASES.length + ' / ' + new Set(AXX_VOICE_PHRASES.map(item => item.text)).size);
if (typeof window !== 'undefined') (window.Axx = window.Axx || {}).voicePhrases = AXX_VOICE_PHRASES;
if (typeof module !== 'undefined') module.exports = AXX_VOICE_PHRASES;
