/* Spoken turns share the chat executor; waiting never produces synthetic audio. */
(function (Axx) {
    'use strict';
    Axx.voiceConversation = {
        instructions: 'MODO VOZ: Conversa con naturalidad en el idioma del usuario. Empieza por una respuesta útil y breve; amplía si la petición lo necesita. Usa frases completas, ritmo conversacional y palabras fáciles de escuchar. No leas Markdown, URLs, código ni identificadores técnicos salvo que te los pidan; esos detalles pueden quedar escritos. Evita saludos repetidos, coletillas, anunciar que estás pensando y preguntas de cierre automáticas. No imites emociones ni afirmes acciones sin un recibo del ejecutor. Si te corrigen, incorpora la corrección sin repetir la equivocación. ',
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
        finish(reader) {
            if (!reader) return;
            reader.awaitingText = false;
            if (reader.state === 'waiting') {
                reader.state = 'ended'; reader.onChange?.(); reader.onEnded?.();
            }
        }
    };
})(window.Axx = window.Axx || {});
