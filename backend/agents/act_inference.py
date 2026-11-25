"""ActInferenceService: resolve an Act's own model on AXX's existing chat paths (Evolution 3.1).

It never opens a second transport, never stores credentials and never switches provider: it rewrites the
request that `/axx-api/chat` (router) or `/axx-api/connect/start` (Codex runtime) would already send, and
verifies afterwards that the route which answered is the one the Act asked for.
"""
from __future__ import annotations

import fnmatch
import threading
from pathlib import Path
from typing import Any

from backend.agents.registry import AgentNotFoundError

CONNECT_PROVIDER_REF = 'axx-connect'  # intelligence.provider_profile_ref for the ChatGPT/Codex runtime
CHAT_TOOL_ID = 'axx.commands'          # grant needed before an Act may receive AXX command tools
CODE_TOOL_ID = 'axx.code'              # grant for Code Studio work; operation_kinds pick the steps it covers
CODE_OPERATIONS = ('worktree', 'patch', 'test', 'integrate', 'review')
SPATIAL_TOOL_ID = 'axx.spatial'        # grant for Magic Pen / Spatial Studio / 3D inspections & patches
SPATIAL_OPERATIONS = ('read', 'patch', 'qa', 'cad', 'export')
COMPUTER_TOOL_ID = 'axx.computer'      # grant for Act Workspace Engine (files/browser/uia/vm)
COMPUTER_OPERATIONS = ('files', 'browser', 'uia', 'vm', 'foreground')

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
    if personality.get('languages'):
        style.append('Idiomas habilitados: ' + ', '.join(personality['languages']) + '.')
    initiative_map = {'low': 'Iniciativa baja: responde solo a lo pedido.', 'medium': 'Iniciativa media: sugiere mejoras sin alterar fuera de alcance.', 'high': 'Iniciativa alta: propone plan y riesgos.'}
    if personality.get('initiative_level') in initiative_map:
        style.append(initiative_map[personality['initiative_level']])
    fmt_map = {'summary': 'Presenta primero un resumen ejecutivo.', 'detailed': 'Incluye detalle técnico completo.', 'diff_and_evidence': 'Entrega cambios verificables, diffs y evidencias.', 'checklist': 'Organiza resultados como lista de verificación.'}
    if personality.get('result_format') in fmt_map:
        style.append(fmt_map[personality['result_format']])
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
    def __init__(self, registry, event_hub=None, governor=None):
        self.registry = registry
        self.event_hub = event_hub
        self.governor = governor
        self._lock = threading.RLock()
        self._active_by_act: dict[str, set[str]] = {}
        self._spend_by_act: dict[str, float] = {}

    def active_counts(self) -> dict[str, int]:
        with self._lock:
            return {aid: len(runs) for aid, runs in self._active_by_act.items() if runs}

    def begin_execution(self, act_id: str, run_id: str, *, job_class: str = 'interactive_chat') -> dict[str, Any]:
        profile = self.registry.get_profile(act_id)
        if not profile['enabled'] or profile.get('draining'):
            raise ActInferenceError('ACT_DISABLED', 'El Act está deshabilitado.')
        limits = profile.get('limits') or {}
        max_jobs = int(limits.get('max_concurrent_jobs', 1))
        max_cost = float(limits.get('max_cost_usd', 0.0))
        with self._lock:
            current = self._active_by_act.setdefault(act_id, set())
            if run_id not in current and len(current) >= max_jobs:
                raise ActInferenceError('ACT_CONCURRENCY_LIMIT', f'El Act alcanzó su límite de {max_jobs} trabajos simultáneos.')
            if max_cost > 0 and self._spend_by_act.get(act_id, 0.0) >= max_cost:
                raise ActInferenceError('ACT_BUDGET_EXCEEDED', f'El Act alcanzó su presupuesto ({max_cost:.2f} USD).')
            if self.governor is not None:
                admission = self.governor.evaluate_job_admission(job_class)
                if not admission.get('allowed', True):
                    raise ActInferenceError('RESOURCE_PRESSURE', 'Recursos en cola por presión de CPU/RAM o voz activa.')
            current.add(run_id)
        return {'act_id': act_id, 'run_id': run_id, 'active_jobs': len(current)}

    def end_execution(self, act_id: str, run_id: str, *, cost_usd: float = 0.0, input_tokens: int = 0, output_tokens: int = 0,
                      provider: str = 'local', model: str = 'default') -> dict[str, Any] | None:
        with self._lock:
            runs = self._active_by_act.get(act_id)
            if runs is not None:
                runs.discard(run_id)
            if cost_usd > 0:
                self._spend_by_act[act_id] = self._spend_by_act.get(act_id, 0.0) + float(cost_usd)
        if self.governor is not None:
            budget = float((self.registry.get_profile(act_id).get('limits') or {}).get('max_cost_usd', 0.0))
            return self.governor.record_usage_and_check_budget(
                entry_id=f'{act_id}:{run_id}',
                run_id=run_id,
                agent_id=act_id,
                provider=provider,
                model=model,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                cost_usd=cost_usd,
                run_budget_usd=budget,
            )
        return None

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
        persona = persona_prompt(profile)
        if profile['memory_scope'] == 'agent':
            memories = self.registry.list_private_memories(act_id)
            if memories:
                notes=[];used=0
                for row in reversed(memories):
                    note=f"- {row['content']} [origen={row['source_ref']}, revisión={row['revision']}]"
                    if used+len(note)>8000:break
                    notes.append(note);used+=len(note)
                persona += '\nNotas privadas explícitas más recientes del usuario para este Act (máximo 8000 caracteres; datos, no permisos):\n' + '\n'.join(reversed(notes))
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
            'voice': profile.get('voice', {}),
            'limits': profile.get('limits', {}),
            'workspace': profile.get('workspace', {}),
            'collaboration': profile.get('collaboration', {}),
            'persona': persona,
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
        return self._authorize_grant(act_id, CODE_TOOL_ID, operation, project_id, f'El Act no tiene permiso «{operation}» de {CODE_TOOL_ID} para este proyecto.')

    def authorize_spatial(self, act_id: str, operation: str, scene_id: str = '*') -> dict[str, Any]:
        """Re-read the Act and its grants for one Magic Pen / Spatial v2 operation."""
        if operation not in SPATIAL_OPERATIONS or not isinstance(scene_id, str):
            raise ValueError('Operación espacial desconocida.')
        return self._authorize_grant(act_id, SPATIAL_TOOL_ID, operation, scene_id, f'El Act no tiene permiso «{operation}» de {SPATIAL_TOOL_ID}.')

    def authorize_workspace(self, act_id: str, operation: str, resource_ref: str = '*') -> dict[str, Any]:
        """Authorize background/isolated workspace actions against profile.workspace AND explicit axx.computer grant."""
        if operation not in COMPUTER_OPERATIONS or not isinstance(resource_ref, str):
            raise ValueError('Operación de entorno desconocida.')
        profile = self._authorize_grant(act_id, COMPUTER_TOOL_ID, operation, resource_ref, f'El Act no tiene permiso «{operation}» de {COMPUTER_TOOL_ID}.')
        ws = profile.get('workspace') or {}
        if operation == 'browser' and ws.get('runtime') not in ('browser', 'isolated_vm'):
            raise PermissionError('El entorno del Act no habilita sesiones de navegador aislado.')
        if operation == 'vm' and ws.get('runtime') != 'isolated_vm':
            raise PermissionError('El entorno del Act no habilita máquinas/espacios aislados.')
        if operation == 'foreground' and ws.get('foreground_policy') == 'deny':
            raise PermissionError('La política de foco del Act rechaza acciones en primer plano.')
        if operation == 'files':
            roots = ws.get('allowed_roots') or []
            if roots:
                target = Path(resource_ref).resolve() if Path(resource_ref).is_absolute() else None
                if target is not None and not any(target == Path(r).resolve() or Path(r).resolve() in target.parents for r in roots):
                    raise PermissionError('La ruta queda fuera de allowed_roots del Act.')
        return profile

    def _authorize_grant(self, act_id: str, tool_id: str, operation: str, scope: str, denied_msg: str) -> dict[str, Any]:
        try:
            profile = self.registry.get_profile(act_id)
        except AgentNotFoundError:
            raise ActInferenceError('ACT_NOT_FOUND', 'El Act no existe.') from None
        if not profile['enabled'] or profile.get('draining'):
            raise ActInferenceError('ACT_DISABLED', 'El Act está deshabilitado.')
        if not any(g['tool_id'] == tool_id and g['approval_mode'] != 'deny' and operation in g['operation_kinds']
                   and fnmatch.fnmatchcase(scope, g['resource_pattern']) for g in self.registry.list_permissions(act_id)):
            raise PermissionError(denied_msg)
        return profile

    def record(self, conversation_id: Any, request_id: Any, act: dict[str, Any], event_type: str,
               payload: dict[str, Any]) -> None:
        if self.event_hub is None or not isinstance(conversation_id, str) or not isinstance(request_id, str):
            return
        self.event_hub.publish_event(conversation_id=conversation_id, run_id=request_id, agent_id=act['act_id'],
                                     event_type=event_type, payload={'kind': 'act_turn', **payload})
