# Contrato para la UI unificada de Claude

No se modificaron Sistema y datos, IA y proveedores, Personalizar AXX ni CSS.
Axx.html solo carga scripts/dictation-engine.js. Un details usa el contenedor
existente #voice-panel-controls. Puede reubicarse manteniendo esta API:

```js
Axx.dictation.status() // api_version, mode, state, microphone_open, decoding, waiting_for_voice, pending_count, queue_length, error
await Axx.dictation.start('manual') // o 'focus'; siempre acción deliberada
Axx.dictation.finish() // finaliza frase; manual entrega lo final y termina
Axx.dictation.pause(); Axx.dictation.resume(); Axx.dictation.stop();
Axx.dictation.settings(); Axx.dictation.configure(settings); // solo OFF
Axx.dictation.pending(); Axx.dictation.copyPending(); Axx.dictation.discardPending();
await Axx.dictation.configureShortcut({key:68,modifiers:7,activation:'hold'});
await Axx.dictation.transcribeFile(file,{translate:false,targetLanguage:'en'});
```

Ajustes: language auto/ISO 2-3 letras; model ID del catálogo o vacío (motor actual);
microphone deviceId; profile literal/conversation/technical/code; output insert/copy;
dictionary lista de hasta 100 pares [original,reemplazo]. Literal/código conservan
texto y cifras; conversación/técnico aplican solo correcciones exactas y espacios.
No se convierten números ambiguos ni se reescribe significado con un LLM.

Evento axx-dictation-state: snapshot sin texto/audio. Estados OFF, ARMED,
CAPTURING, DECODING (fin manual), PAUSED, ERROR. decoding y microphone_open son
independientes: inferencia puede coexistir con captura del siguiente segmento.
Solo pending() devuelve texto explícitamente, solo RAM; sin logs/historial.

Atajo configurable: MOD_ALT=1, MOD_CONTROL=2, MOD_SHIFT=4, mínimo dos y A-Z.
Toggle/hold; colisión conserva el atajo previo. Android Ctrl+Alt+Shift+V y Axx
Alt+Shift+A están reservados. Preferencias de atajo no arman escucha al arrancar.

Backend autenticado desktop: GET /axx-api/speech/models, POST
/axx-api/speech/models/prepare {model}, /models/unload {}, /speech/transcribe
con campo model opcional y /speech/cancel {request_id}. Las rutas existentes y
/v1 móvil siguen vigentes. Preparar/liberar no modifica el proveedor de chat.
El postproceso remoto no existe: no mostrar un interruptor que prometa enviarlo.

El estado puede esperar una conversación aunque no haya stream activo entre turnos. No recuperar automáticamente el micrófono de una sesión que lo ha preemptado. El registro inicial de atajo espera la comprobación del chord de órdenes en el renderer; conflicto => deshabilitar solo el nuevo. La API de conflicto sirve al editor de atajos de voz para conservar ambos comportamientos separados.

Literal/código evitan sustituciones semánticas; la inserción global aplana CR/LF/tab a espacios para no sintetizar Enter. Los archivos devuelven su transcripción como texto y no se insertan ni envían automáticamente. Canary requiere origen explícito; forced_language=false en Parakeet significa que el hint no garantiza forzado.
