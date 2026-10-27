# Revisión conjunta de Axx · 27 de octubre de 2026

Esta revisión reúne Magic Pen, voz y control del escritorio en las fuentes de
Axx. Los recibos privados de compilación, instalación y ensayos permanecen en
`build/`; no se publican conversaciones, credenciales, muestras ni pesos.

| Trabajo revisado | Resultado de la revisión | Integración |
| --- | --- | --- |
| Magic Pen | Dos pasadas visuales; controles, foco, opacidad y entrada nativa contrastados. | Interfaz integrada. |
| Voz en vivo | Referencia por solicitud; caché antigua invalidada al cambiar de voz. | Fuentes y pruebas integradas. |
| Enrutamiento y escritorio | Corregida la asociación entre captura y destino; baseline fresco antes del gesto. | Fuentes y pruebas integradas. |
| Entrenamiento de intenciones | Candidato M11 r3 revisado con sus manifiestos; la línea de laboratorio ya continuó a M12/M13. | Laboratorio separado, sin promoción. |
| Propuesta de comunicaciones | El chat «Integrar OpenWA en AXX» describe una futura integración de llamadas; no aporta una sesión local ni una llamada verificada. | El catálogo conserva guías de Telegram y WhatsApp; llamadas automáticas pendientes de cuenta, integración y ensayo real. |
| Guiones para voz | Material de grabación y transcripción del chat «Diálogo para probar voz». | No acredita entrenamiento ni calidad de una voz. No se publican grabaciones personales. |

## Evaluación independiente M11

El trabajo de laboratorio M11 r3 permanece separado de la aplicación, sin
promoción. Su alcance es probar contratos locales MCP con transporte en memoria
y SQLite temporal; no ejecuta servicios MCP externos, modelos ni entrada física.

La revisión contrastó los manifiestos del candidato: 208 archivos Python,
221 archivos completos y 50 artefactos coincidieron con sus hashes. El banco
existente registra 23 casos ejecutados y aprobados. Esta revisión no repitió ese
banco ni atribuye sus resultados a las fuentes actuales de Axx.

El candidato refuerza identidad, política y esquema en la postcondición, y
conserva el estado de despacho cuando se recibe una respuesta inválida. No
certifica origen ni verdad remota. La fase de excepción anterior al retorno del
transporte sigue sin desambiguar por sí sola un envío. La aplicación actual no
contiene ese candidato; cualquier integración requiere una evaluación propia.

La lectura posterior de `CURRENT-TRAINING.json`, a las 07:57 UTC, sitúa el
laboratorio en M13 r1, todavía antes de su baseline, sobre M12 r2. El registro
declara M12 r2 cerrado con 21/21, sin modelos, conexiones ni sesiones de audio
reales y con `no_promotion:true`. Esta revisión no reproduce ni verifica ese
recuento: no se suma al banco M11 ni al de la aplicación. M13 es trabajo en
curso sobre eventos sintéticos y no demuestra voz en vivo.

## Entrega de escritorio

La tabla del [README](../README.md) distingue el estado de cada función. La
versión de Windows se sincroniza con `scripts/release.py`; publicar exige el
instalador y la instalación verificados y el hash confirmado por GitHub.
