# Fase 8 (`PR-11` y `PR-12`) — Especificación: Agent Designer, Catálogo 24/9 y Evolución de Chats y Grupos

- **Fase:** 8 (`PR-11`, `PR-12`)
- **Rama:** `feature/axx-evolution-3`
- **Dependencia:** `PR-10` (`Gate G7` aprobado)
- **Gate objetivo:** `G8` (`CHAT-01`, `CHAT-02`, `CHAT-03`, `AGENT-01`, `AGENT-02`, `AGENT-04`, `AGENT-05`, `E2E-01`, `E2E-02`)

## 1. Archivos implementados

- `backend/agents/profiles.py` (`PR-11`: `AvatarFormAdapter` con las 24 formas AXX y 9 paletas canónicas, caché de miniaturas SVG sin bucle WebGL en reposo, validador `validate_agent_profile`, `export_agent_package` e `import_agent_package` limpios de secretos y con rutinas pausadas por defecto).
- `backend/agents/policy.py` (`PR-11`: resolución autoritativa de intersección de permisos en backend, atenuación estricta en delegaciones y cambio seguro de proveedor sin fuga de tokens de sesión).
- `backend/agents/registry.py` (`PR-11`: `AgentRegistry` SQLite con CAS por `revision`, gestión de `agent_permissions`, `agent_teams` y desactivación con revocación de grants).
- `backend/agents/bindings.py` (`PR-12`: `ConversationBindingService` N:N sobre `chat_conversations`, conversión reversible sin pérdida de historial/ID/borrador, bloqueo `CrossChatAccessDeniedError` contra lecturas cruzadas entre chats y limpieza ante olvido).
- `backend/chat_store.py` (integración aditiva en `purge()`, `forget()` y `delete` para depurar enlaces y eventos de conversaciones expiradas/olvidadas).
- `1.AXX/scripts/agents/agent-designer.js` y `1.AXX/scripts/agents/agent-roster.js` (módulos frontend lazy-loaded con accesibilidad por teclado roving `tabindex` y flujo `Preview -> Aplicar -> Descartar`).
- `backend/tests/test_agent_profiles_and_chat_bindings.py`.
