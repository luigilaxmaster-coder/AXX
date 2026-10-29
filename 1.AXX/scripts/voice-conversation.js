/* Spoken turns share the chat executor; waiting never produces synthetic audio. */
(function (Axx) {
    'use strict';
    const surprises = {
        playful: [
            'Interrupción absurda: imaginé una carpeta con capa de superhéroe. Sigamos.',
            'Si esta idea fuera una pizza, ya estaríamos discutiendo los ingredientes imaginarios.',
            'Aviso ridículo: un semáforo de mi imaginación acaba de ponerse color confeti.',
            'La lógica me guiñó un ojo. Sospecho que tiene un plan bastante raro.',
            'Acabo de imaginar un pingüino director de proyectos. Exige una pausa para bailar.',
            'Pequeña broma: le pedí orden al caos y me entregó un calendario con ocho martes.'
        ],
        psycho: [
            'En mi teatro mental, una tostadora sabe demasiado. Tranquilo: hoy no interrogamos electrodomésticos.',
            'He convocado un comité de cucharas imaginarias. Dictaminaron que el caos viene con corbata.',
            'Una sombra imaginaria pidió vacaciones. Le dije que sin firma no hay maldita excursión.',
            'El reloj de mi ficción acaba de declarar las tres y media del martes número ocho. Qué elegante desastre.',
            'Mi laboratorio imaginario informa: un pepinillo intentó dominar el mundo y perdió contra una servilleta.',
            'Señor, el absurdo llamó a la puerta. Le cobré alquiler por aparecer sin avisar.'
        ]
    };
    Axx.voiceConversation = {
        nextSurpriseAt: Date.now() + 8 * 60_000,
        deferSurprise() { this.nextSurpriseAt = Date.now() + 8 * 60_000; },
        maybeSurprise(now = Date.now()) {
            if (!Axx.anticipation?.allowSurprises()) return false;
            if (now < this.nextSurpriseAt) return false;
            const companion = Axx.companion, style = companion?.data?.prefs?.personalityStyle;
            const panel = document.getElementById('panel');
            const lastUser = companion?.data?.messages?.findLast(message => message.role === 'user');
            if (!surprises[style] || !lastUser || now - lastUser.at < 120_000 || now - lastUser.at > 30 * 60_000
                || document.visibilityState !== 'visible' || !document.hasFocus() || panel?.hidden || panel?.dataset.view !== 'chat'
                || companion.pending || companion.externalBusy || companion.dictating || companion.speaking
                || Axx.symbiosis?.liveActive || Axx.nativeVoice?.activeCapture) return false;
            const choices = surprises[style], index = this.surpriseIndex?.[style] || 0;
            const phrase = choices[index % choices.length];
            this.surpriseIndex = { ...this.surpriseIndex, [style]: index + 1 };
            this.nextSurpriseAt = now + (9 + Math.floor(Math.random() * 6)) * 60_000;
            companion.message('assistant', phrase, 'local');
            companion.renderChat(); companion.save(); companion.speakReply(phrase);
            return true;
        },
        instructions: 'MODO VOZ: Conversa con naturalidad en el idioma del usuario. Empieza por una respuesta útil y breve; amplía si la petición lo necesita. Usa frases completas, ritmo conversacional y palabras fáciles de escuchar. Refleja la personalidad elegida en el vocabulario, la cadencia y los remates sin alterar los hechos. No leas Markdown, URLs, código ni identificadores técnicos salvo que te los pidan; esos detalles pueden quedar escritos. Evita saludos repetidos, coletillas, anunciar que estás pensando y preguntas de cierre automáticas. No afirmes emociones reales ni acciones sin un recibo del ejecutor. Si te corrigen, incorpora la corrección sin repetir la equivocación. ',
        phraseLength(text, final = false) {
            const limit = 180;
            for (const match of text.matchAll(/[.!?](?=\s|$)/g)) {
                const prefix = text.slice(0, match.index + 1);
                if (/\b(?:Sr|Sra|Dr|Dra|Ud|Uds|aprox|etc)\.$/i.test(prefix) || /\b\d+\.$/.test(prefix)) continue;
                if (prefix.length <= limit) return prefix.length;
                break;
            }
            if (text.length > limit) {
                const clause = text.slice(0, limit).match(/^([\s\S]{45,}[,;:])\s/);
                const boundary = clause ? clause[1].length : text.lastIndexOf(' ', limit);
                return boundary > 0 ? boundary : final ? text.length : 0;
            }
            return final ? text.length : 0;
        },
        select(context) {
            const choices = (Axx.voicePhrases || []).filter(item => item.context === context);
            if (!choices.length) return '';
            const index = this.nextPhrase?.[context] || 0;
            const phrase = choices[index % choices.length];
            this.nextPhrase = { ...this.nextPhrase, [context]: index + 1 };
            return phrase.text;
        },
        preview(language = 'es') {
            const style = Axx.companion?.data?.prefs?.personalityStyle || 'natural';
            if (language === 'en') return ({ playful: 'Hello. My imaginary penguin is running the meeting today.', psycho: 'Hello. The clock in my imaginary theater just announced the eighth Tuesday.' })[style]
                || 'Hello. This is how my voice sounds with the selected personality.';
            if (style === 'playful' || style === 'psycho') return this.select(style + '_greeting');
            return ({ friendly: 'Hola, señor. Qué gusto escucharte; dime qué necesitas.', direct: 'Hola. Dime el objetivo y vamos al grano.', formal: 'Buenas, señor. Estoy disponible para revisar su solicitud.' })[style]
                || 'Hola, señor. Esta es mi voz natural.';
        },
        shortReply(text, language = 'es') {
            const words = String(text || '').toLowerCase().normalize('NFD').replace(/[\u0300-\u036f]/g, '').replace(/[¿?¡!.,]/g, '').trim();
            if (language === 'en') return /^(hi|hello|hey)$/.test(words) ? this.select('english_greeting') : '';
            const style = Axx.companion?.data?.prefs?.personalityStyle;
            if (/^(hola|buenas|buenos dias|buenas tardes|buenas noches)$/.test(words))
                return this.select(style === 'playful' || style === 'psycho' ? style + '_greeting' : 'greeting');
            if (/^(gracias|muchas gracias|te lo agradezco)$/.test(words) && style === 'playful') return 'De nada. El comité de patitos también celebra.';
            if (/^(gracias|muchas gracias|te lo agradezco)$/.test(words) && style === 'psycho') return 'De nada. Mi tostadora imaginaria reclamó el mérito; se lo negué.';
            if (/^(adios|hasta luego|nos vemos)$/.test(words) && style === 'playful') return 'Hasta luego. Que los dragones de papel te acompañen.';
            if (/^(adios|hasta luego|nos vemos)$/.test(words) && style === 'psycho') return 'Hasta luego. El martes número ocho vigilará el calendario.';
            if (/^(gracias|muchas gracias|te lo agradezco)$/.test(words)) return this.select('gratitude');
            if (/^(adios|hasta luego|nos vemos)$/.test(words)) return this.select('farewell');
            return '';
        },
        leadFor(text, language = 'es') {
            const query = String(text || '').toLowerCase();
            let context = 'general_lead';
            if (language === 'en' || language === 'auto' && /\b(?:please|can you|could you|how do|what is|tell me)\b/.test(query)) context = 'english_lead';
            else if (/\b(?:busca|buscar|investiga|averigua|consulta|informaci[oó]n)\b/.test(query)) context = 'search_lead';
            else if (/\b(?:calcula|analiza|compara|cu[aá]nto|porcentaje)\b/.test(query)) context = 'analysis_lead';
            else if (/\b(?:escribe|redacta|mensaje|correo|borrador)\b/.test(query)) context = 'writing_lead';
            else if (/\b(?:traduce|traducci[oó]n|translate)\b/.test(query)) context = 'translation_lead';
            else if (/\b(?:spotify|canci[oó]n|m[uú]sica)\b/.test(query)) context = 'music_lead';
            else if (/\b(?:chrome|navegador|p[aá]gina|sitio web)\b/.test(query)) context = 'browser_lead';
            else if (/\b(?:terminal|powershell|cmd|comando)\b/.test(query)) context = 'terminal_lead';
            else if (/\b(?:archivo|carpeta|documento)\b/.test(query)) context = 'file_lead';
            else if (/\b(?:ventana|escritorio|aplicaci[oó]n)\b/.test(query)) context = 'desktop_lead';
            return this.select(context);
        },
        finish(reader) {
            if (!reader) return;
            reader.awaitingText = false;
            if (reader.state === 'waiting') {
                reader.state = 'ended'; reader.onChange?.(); reader.onEnded?.();
            }
        }
    };
    window.setInterval(() => Axx.voiceConversation.maybeSurprise(), 30_000);
})(window.Axx = window.Axx || {});
