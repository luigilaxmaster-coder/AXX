Fecha: 2026-11-21. Base: `2f177ea` (PR #6). Rama: `codex/axx-evolution-3-audit-visual-3d-chatgpt`. Mejoras: [Draft PR #7](https://github.com/luigilaxmaster-coder/AXX/pull/7).

# Conexión ChatGPT: evidencias y límites

La ruta activa es `backend/connect/provider.py` (Codex App Server 0.160.0), no las dos fachadas legadas de OAuth. Se localizaron todos sus consumidores; los helpers DPAPI siguen usados por ajustes y Connect. No se cargan ni eliminan los tokens legados. No se cambiaron credenciales ni se inició sesión por automatización de navegador.

| Prueba | Resultado |
|---|---|
| Cuenta ya autenticada y catálogo | INTEGRATION_PASS; no equivale a nuevo login ni a entitlement universal |
| Respuesta real gpt-6.1-sol | INTEGRATION_PASS: AXX_AUDIT_OK, modelo solicitado=servido |
| Streaming | INTEGRATION_PASS: eventos item/agentMessage/delta observados |
| Reinicio/contexto | INTEGRATION_PASS: COBALTO_AXX_731 recuperado tras cerrar y recrear proveedor |
| Cancelación | INTEGRATION_PASS: cancelled, effects_reverted=false |
| Cambio a gpt-6.1-terra | INTEGRATION_PASS tras corregir reanudación: AXX_MODEL_SWITCH_OK |
| Persistencia de selección | UNIT_PASS y reinicio real de proveedor; verificación de inferencia no se conserva falsamente |
| Expiración/revocación/red/cuota/mismatch | UNIT_PASS en contratos controlados; no se revocó la sesión compartida del propietario |
| Herramienta emitida por modelo real | INTEGRATION_PASS: gpt-6.1-sol invocó axx_status, ConnectService.dispatch devolvió executor=ready; consulta sin efectos |
| Herramienta aprobada y efecto | INTEGRATION_PASS de API de agentes/ejecutor con archivo y readback; no una tool-call emitida por ChatGPT en esta auditoría |
| Perfil individual/equipo/visión/ASR/TTS | Pendientes en el producto completo; no inferidos a partir del login |

Evidencia local: `provider/live-turn.json`, `provider/continuity-live.json`, `provider/model-switch-after.json`, `connect-final.log`, `provider/tool-live.json`. Las muestras contienen únicamente instrucciones sintéticas. Un sondeo de Axx Connect instalado devolvió executor ready y UI conectada; ese sondeo es independiente de la inferencia de la candidata y no demuestra origen ChatGPT web.

Se consultó documentación oficial vigente: [autenticación](https://developers.openai.com/codex/auth), [App Server](https://developers.openai.com/codex/app-server), [SIWC](https://developers.openai.com/siwc), [plan usage](https://developers.openai.com/siwc/token-sharing-open-source), [App Server SIWC](https://developers.openai.com/siwc/token-sharing-open-source/codex-app-server), [limitaciones preview](https://developers.openai.com/siwc/token-sharing-open-source/preview-limitations), [API](https://developers.openai.com/api/docs). Catálogo e inferencia se separan conforme al protocolo oficial. No se encontró registro OAuth SIWC específico de Axx que permita activar esa vía; no se creó uno. OpenAI API tiene credenciales/costes independientes y no se activó. No se habilitó túnel público ni se acreditó integración desde ChatGPT web.
