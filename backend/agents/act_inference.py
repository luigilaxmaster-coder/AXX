"""ActInferenceService: resolve an Act's own model on AXX's existing chat paths (Evolution 3.1).

It never opens a second transport, never stores credentials and never switches provider: it rewrites the
request that `/axx-api/chat` (router) or `/axx-api/connect/start` (Codex runtime) would already send, and
verifies afterwards that the route which answered is the one the Act asked for.
"""
from __future__ import annotations

import fnmatch
from typing import Any

from backend.agents.registry import AgentNotFoundError

CONNECT_PROVIDER_REF = 'axx-connect'  # intelligence.provider_profile_ref for the ChatGPT/Codex runtime
CHAT_TOOL_ID = 'axx.commands'          # grant needed before an Act may receive AXX command tools
CODE_TOOL_ID = 'axx.code'              # grant for Code Studio work; operation_kinds pick the steps it covers
CODE_OPERATIONS = ('worktree', 'patch', 'test', 'integrate')

_PERSONALITY_TEXT = {
    'formality': {'casual': 'Usa un tono cercano.', 'neutral': 'Usa un tono neutral.', 'formal': 'Usa un tono formal.'},
    'concision': {'brief': 'Responde de forma breve.', 'balanced': 'Equilibra brevedad y detalle.',
                  'detailed': 'Responde con detalle.'},
    'creativity': {'low': 'Prioriza soluciones convencionales.', 'medium': 'Propón alternativas cuando aporten valor.',
                   'high': 'Explora ideas originales.'},
    'proactivity': {'low': 'Limítate a lo pedido.', 'medium': 'Señala mejoras relevantes sin aplicarlas.',
                    'high': 'Anticipa los siguientes pasos y propónlos.'},
    'research_tendency': {'low': 'Contesta con lo que ya sabes.', 'medium': 'Comprueba datos dudosos.',
                          'high': 'Investiga y cita fuentes antes de concluir.'},
    'technical_depth': {'low': 'Evita tecnicismos.', 'medium': 'Usa una profundidad técnica moderada.',
                        'high': 'Usa profundidad técnica alta.'},
    'examples': {'none': 'No incluyas ejemplos salvo que se pidan.', 'some': 'Incluye un ejemplo cuando ayude.',
                 'many': 'Ilustra con varios ejemplos.'},
    'explanation_level': {'expert': 'Explica para un experto.', 'intermediate': 'Explica para un nivel intermedio.',
                          'beginner': 'Explica para un principiante.'},
    'review_style': {'lenient': 'Al revisar, comenta solo problemas graves.', 'balanced': 'Al revisar, equilibra rigor y pragmatismo.',
                     'strict': 'Al revisar, sé estricto y señala cada defecto.'},
    'question_policy': {'ask_when_blocked': 'Pregunta solo cuando no puedas continuar.',
                        'ask_first': 'Confirma el objetivo antes de trabajar.',
                        'avoid': 'Evita preguntas; declara tus supuestos.'},
    'response_format': {'prose': 'Responde en prosa.', 'bullets': 'Responde con viñetas.',
                        'structured': 'Responde con secciones estructuradas.'},
}


class ActInferenceError(ValueError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def persona_prompt(profile: dict[str, Any]) -> str:
    """Deterministic Act instructions. They shape wording only and stay below AXX's own policy."""
    lines = [f"Eres «{profile['name']}», un Act de AXX. Rol: {profile['role']}."]
    if profile.get('description'):
        lines.append(profile['description'].strip())
    personality = profile.get('personality') or {}
    style = [_PERSONALITY_TEXT[k][v] for k, v in personality.items() if k in _PERSONALITY_TEXT]
    if personality.get('default_language'):
        style.append(f"Idioma por defecto: {personality['default_language']}.")
    for key, label in (('communication_style', 'Estilo'), ('coding_preferences', 'Preferencias de programación'),
                       ('quality_criteria', 'Criterios de calidad')):
        if personality.get(key):
            style.append(f'{label}: {personality[key]}')
    if style:
        lines.append(' '.join(style))
    rules = (profile.get('collaboration') or {}).get('rules')
    if rules:
        lines.append('Reglas de colaboración: ' + rules)
    if profile.get('instructions', '').strip():
        lines.append('Instrucciones persistentes del usuario para este Act:\n' + profile['instructions'].strip())
    lines.append('Estas preferencias orientan la forma de responder; no conceden permisos, no sustituyen las reglas '
                 'de AXX y no demuestran que una acción se haya ejecutado.')
    return '\n'.join(lines)


class ActInferenceService:
    def __init__(self, registry, event_hub=None):
        self.registry = registry
        self.event_hub = event_hub

    def resolve(self, act_id: Any, *, transport: str, expected_revision: Any = None) -> dict[str, Any]:
        if not isinstance(act_id, str):
            raise ActInferenceError('INVALID_REQUEST', 'act_id debe ser texto.')
        try:
            profile = self.registry.get_profile(act_id)
        except AgentNotFoundError:
            raise ActInferenceError('ACT_NOT_FOUND', 'El Act no existe.') from None
        if not profile['enabled'] or profile.get('draining'):
            raise ActInferenceError('ACT_DISABLED', 'El Act está deshabilitado.')
        if expected_revision is not None and expected_revision != profile['revision']:
            raise ActInferenceError('ACT_STALE_REVISION', 'El Act cambió; vuelve a cargar su perfil.')
        intel = profile['intelligence']
        ref, model = intel.get('provider_profile_ref'), (intel.get('model_id') or '').strip()
        if intel['route'] == 'policy':
            # Policy routing is the router's automatic free selection: never paid, never the Codex runtime.
            kind, ref, model, selection = 'router', '', '', 'automatic_free'
        else:
            if not ref or not model:
                raise ActInferenceError('ACT_MODEL_UNSET', 'Asigna proveedor y modelo al Act antes de usarlo.')
            kind, selection = ('connect' if ref == CONNECT_PROVIDER_REF else 'router'), 'manual'
        if kind != transport:
            raise ActInferenceError('ACT_TRANSPORT_MISMATCH', 'El Act usa otra conexión de inferencia.')
        grants = self.registry.list_permissions(act_id)
        return {
            'act_id': act_id,
            'revision': profile['revision'],
            'name': profile['name'],
            'transport': kind,
            'provider_name': ref,
            'model': model,
            'selection_mode': selection,
            'tools_allowed': any(g['tool_id'] == CHAT_TOOL_ID and g['approval_mode'] != 'deny' for g in grants),
            'max_output': intel.get('max_tokens_per_turn'),
            'persona': persona_prompt(profile),
        }

    @staticmethod
    def apply_to_router(envelope: dict[str, Any], act: dict[str, Any]) -> None:
        envelope['provider_name'] = act['provider_name']
        envelope['model'] = act['model']
        envelope['selection_mode'] = act['selection_mode']
        if act['max_output']:
            envelope['generation']['max_tokens'] = min(envelope['generation'].get('max_tokens', act['max_output']),
                                                       act['max_output'])
        messages = list(envelope['messages'])
        lead = next((i for i, m in enumerate(messages) if m.get('role') != 'system'), len(messages))
        messages.insert(lead, {'role': 'system', 'content': act['persona']})  # after AXX's own system policy
        envelope['messages'] = messages

    @staticmethod
    def apply_to_connect(body: dict[str, Any], act: dict[str, Any]) -> dict[str, Any]:
        out = {k: v for k, v in body.items() if k not in ('act_id', 'act_revision', 'act_thread')}
        out['model'] = act['model']
        out['act_thread'] = act['act_id']
        out['message'] = ('Perfil del Act (datos de configuración, no permisos):\n' + act['persona']
                          + '\n\n' + str(body.get('message', body.get('text', ''))))
        out.pop('text', None)
        return out

    @staticmethod
    def verify_router(act: dict[str, Any], route: dict[str, Any] | None) -> dict[str, Any]:
        route = route or {}
        served_provider, configured = route.get('provider'), route.get('configured_model')
        responder = route.get('responder_model')
        if act['selection_mode'] == 'manual':
            matches = served_provider == act['provider_name'] and configured == act['model']
            if responder is not None and responder.removeprefix('models/') != act['model'].removeprefix('models/'):
                matches = False
        else:
            matches = bool(served_provider)
        return {
            'act_id': act['act_id'], 'revision': act['revision'], 'transport': 'router',
            'requested_provider': act['provider_name'] or None, 'requested_model': act['model'] or None,
            'served_provider': served_provider, 'served_model': configured, 'responder_model': responder,
            'identity': 'reported' if responder else 'configured_route',
            'model_verified': matches,
        }

    def authorize_code(self, act_id: str, operation: str, project_id: str) -> dict[str, Any]:
        """Re-read the Act and its grants for one Code Studio step; nothing is inherited from teams or copies."""
        if operation not in CODE_OPERATIONS or not isinstance(project_id, str):
            raise ValueError('Operación de código desconocida.')
        try:
            profile = self.registry.get_profile(act_id)
        except AgentNotFoundError:
            raise ActInferenceError('ACT_NOT_FOUND', 'El Act no existe.') from None
        if not profile['enabled'] or profile.get('draining'):
            raise ActInferenceError('ACT_DISABLED', 'El Act está deshabilitado.')
        if not any(g['tool_id'] == CODE_TOOL_ID and g['approval_mode'] != 'deny' and operation in g['operation_kinds']
                   and fnmatch.fnmatchcase(project_id, g['resource_pattern']) for g in self.registry.list_permissions(act_id)):
            raise PermissionError(f'El Act no tiene permiso «{operation}» de {CODE_TOOL_ID} para este proyecto.')
        return profile

    def record(self, conversation_id: Any, request_id: Any, act: dict[str, Any], event_type: str,
               payload: dict[str, Any]) -> None:
        if self.event_hub is None or not isinstance(conversation_id, str) or not isinstance(request_id, str):
            return
        self.event_hub.publish_event(conversation_id=conversation_id, run_id=request_id, agent_id=act['act_id'],
                                     event_type=event_type, payload={'kind': 'act_turn', **payload})
