# Fase 2: cancelación correlacionada de voz — borrador aislado

Estado: implementado y probado como overlay de dos módulos; **sin integrar, compilar, instalar ni validar audio físico**. No se modificaron `backend/server.py`, HTML, JS, Rust ni fuentes del candidato congelado. No se operaron micrófono, SAPI, Whisper, altavoces, UI o aplicaciones destino.

## Base y alcance

Copiados primero desde `C:\Users\luigi\Desktop\Axx assistant\build\phased-ux-20261020`:

| Archivo de base | SHA256 |
|---|---|
| `backend/speech/offline_asr.py` | `1209041D593EC5D38D4E70E5AAB53E048DD2D1D824827F77E5A6E44C3F75F3F2` |
| `backend/speech/windows_tts.py` | `1619368D4A954CCD1D467BB654C614EC82D620EC5EE7EC12947BF92B476C604F` |

Se leyó `evidence/review/root-history-backend-20261020.md` y se comparó la corrección histórica ASR `6DE5BC2C…` y sus seis pruebas. Se adaptó el principio de publicar un registro antes de preparar archivos/spawn y de conservar su evento y exclusión de recursos. No se copió el archivo histórico completo. La función ASR `worker_main` y el script SAPI inmutable se conservaron; la envoltura de ejecución ahora comparte límites, recursos y limpieza.

Integrar **los dos módulos juntos** después de cerrar el freeze de fase 1. ASR importa el registro y el runner privados de `windows_tts.py`; copiar uno solo no es compatible.

## Contrato

`transcribe(body)` y `synthesize(body)` aceptan `operation_id` opcional. Si falta, generan UUID; un valor presente nulo se rechaza. Formato exacto: `[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}` ASCII, longitud 1–128. No usar texto dictado, rutas ni secretos como ID.

Cada respuesta exitosa contiene `operation_id` y `kind`, respectivamente `transcription` o `synthesis`, además del resultado existente. El trabajador ASR no recibe el ID ni texto extra; la correlación permanece en el proceso servidor. Cancelar no vacía ni modifica transcripciones o borradores persistidos.

Cada servicio expone `cancel(operation_id) -> CancellationResult`:

```json
{"kind":"transcription","operation_id":"example:A","state":"cancel_requested"}
```

| Estado | Significado |
|---|---|
| `cancelled` | Tombstone anterior a admisión, o propietario ya retirado y sin hijo pendiente. Una solicitud posterior con ese ID se rechaza con `CANCELLED`. |
| `cancel_requested` | Evento señalado y retirada en curso. Puede existir preparación/spawn bloqueado; no significa que la operación haya terminado. |
| `already_finished` | La operación ya confirmó su resultado o terminó con otro error. No se modifica ni se vuelve a ejecutar. |

Los registros son independientes por servicio/kind. Cancelar A no toca B; el mismo ID de síntesis y transcripción representa dos operaciones distintas. La cancelación anterior a admisión deja tombstone. Los registros terminales se retienen 300 s y el máximo es 256 por servicio. No se expulsan tombstones vivos ni activos para hacer espacio: se devuelve `BUSY`. El cliente debe generar ID nuevo por intento y no reutilizarlo aunque expire la retención.

Registro y busy se adquieren bajo la misma exclusión antes de archivos/spawn. El resultado se confirma bajo la exclusión del registro; si cancelación ganó esa carrera, se eleva `SpeechError('CANCELLED', ...)`. El mismo registro sobrevive al intervalo de spawn y posee proceso/Job hasta limpieza. El runner limita pipes, plazo y salida, mata solo el hijo propio y sus descendientes mediante el gestor existente, y llama `wait()` para retirarlo. Si Windows rehúsa retirar el hijo, se mantiene registro/busy y una cancelación dirigida puede reintentar; no se anuncia `cancelled` ni se admite otro trabajo como si estuviera limpio.

SAPI se ejecuta dentro de su PowerShell propio con entrada privada y WAV temporal. Cancelar mata ese trabajador; no hay llamada de voz al altavoz desde el backend. La reproducción de un WAV ya recibido pertenece al cliente: debe detener `Audio`/WebAudio local y rechazar resultados tardíos por ID. Estas pruebas no certifican el comportamiento de SAPI ni el audio de la aplicación instalada.

`cancel_active()` conserva retorno entero para cierre explícito. **No usarlo desde cancelación de una petición o desde el Stop de otra función.**

## Hooks exactos para el integrador de servidor

Estas son instrucciones de integración; no se aplicaron al servidor congelado. Conservar autenticación, comprobación de origen y límites existentes. No tomar `server.action_lock` para voz o cancelación: bloquearía el endpoint que debe señalar la operación activa.

Importar los validadores internos junto al servicio:

```python
from backend.speech.windows_tts import (
    WindowsSpeechService, SpeechError, _body_operation_id, _validate_operation_id,
)
```

Extender `_speech_error` sin romper sus llamadas existentes para devolver identidad validada también en errores correlacionados:

```python
def _speech_error(self, error, *, kind=None, operation_id=None):
    status = {'INVALID_REQUEST': 400, 'BUSY': 409, 'CANCELLED': 499,
              'NOT_SUPPORTED': 501, 'DEADLINE_EXCEEDED': 504}.get(error.code, 502)
    payload = {'error': {'code': error.code, 'message': str(error)}}
    if kind is not None and operation_id is not None:
        payload.update(kind=kind, operation_id=operation_id)
    self._send_json(status, payload)
```

Sustituir solo las dos ramas de voz y añadir la rama de cancelación:

```python
elif path in ('/axx-api/speech/synthesize', '/axx-api/speech/transcribe'):
    kind = 'synthesis' if path.endswith('/synthesize') else 'transcription'
    operation_id = _body_operation_id(body)  # INVALID_REQUEST si ID malformado.
    service = self.speech if kind == 'synthesis' else self.transcription
    try:
        if service is None:
            raise SpeechError('NOT_SUPPORTED', 'Local speech service is unavailable')
        request = {**body, 'operation_id': operation_id}
        result = service.synthesize(request) if kind == 'synthesis' else service.transcribe(request)
    except SpeechError as exc:
        self._speech_error(exc, kind=kind, operation_id=operation_id)
    else:
        self._send_json(200, result)

elif path == '/axx-api/speech/cancel':
    if set(body) != {'kind', 'operation_id'} or body.get('kind') not in ('transcription', 'synthesis'):
        raise SpeechError('INVALID_REQUEST', 'Expected kind and operation_id')
    kind = body['kind']
    operation_id = _validate_operation_id(body['operation_id'])
    service = self.transcription if kind == 'transcription' else self.speech
    try:
        if service is None:
            raise SpeechError('NOT_SUPPORTED', 'Local speech service is unavailable')
        result = service.cancel(operation_id)
    except SpeechError as exc:
        self._speech_error(exc, kind=kind, operation_id=operation_id)
    else:
        self._send_json(200, result)
```

El `_body()` actual ya exige objeto JSON. No reflejar IDs inválidos en mensajes o logs. Los errores de ID malformado mantienen el error general existente; las peticiones con ID válido devuelven ambos campos de identidad.

En `/axx-api/actions/cancel`, retirar **solo** los incrementos mediante `self.speech.cancel_active()` y `self.transcription.cancel_active()` (base líneas 457–460). Conservar cancelación de comandos/acciones con su propietario. Mantener las llamadas globales de voz únicamente en cierre explícito. No traducir `cancel_requested` a éxito terminal en JS.

## Validación ejecutada

Overlay aislado de los dos módulos del borrador, con importaciones restantes desde el candidato y Python `-B`/`dont_write_bytecode` para no producir bytecode en el freeze.

1. `python -B tests/test_speech_cancellation.py`, cwd de este borrador: **19 PASS**. Barreras deterministas en preparación, spawn, trabajador activo, cancelación tardía A/B, commit, enumeración de voces, límites TTL/cap, ID/campos inválidos, errores del worker, fallo de reaping y recuperación dirigida, compatibilidad de cierre y legado. El harness falla ante excepciones de los threads de pipes. Se conservaron hash de entrada ASR, metadatos WAV y script SAPI. Los WAV de contrato son solo bytes PCM inertes generados por la prueba y no se reproducen.
2. Un caso de las 19 pruebas reemplaza ambos comandos de voz por dos hijos Python propios que solo leen stdin y duermen. Se verifica que cancelación deja `CANCELLED`, hijo terminado/reaped, busy liberado y temporales vacíos. No se ejecuta código de reconocimiento o síntesis.
3. **6 PASS** de `backend.tests.test_delivery_contract.DeliveryContractTests` con el mismo overlay: `test_offline_transcription_input_guards`, `test_body_size_and_object_validation`, `test_no_public_token_or_cross_origin_access`, `test_memory_inspection_fallback_and_bounded_identifiers`, `test_paid_and_local_only_blocked`, `test_baseline_sqlite_migration_and_preferences`. Resultado: `Ran 6 tests in 16.599s / OK`.
4. Se excluyó expresamente `test_real_windows_speech_wav_and_input_guards` porque invoca SAPI real. Sus guardas de tamaño/rate/volume/voz se comprobaron con dependencias inertes en la suite nueva. No se atribuye ninguna prueba de audio físico a esta ejecución.

Para repetir los seis contratos existentes desde este borrador:

```python
import importlib.util
import unittest
from pathlib import Path
p = Path('tests/test_speech_cancellation.py').resolve()
spec = importlib.util.spec_from_file_location('draft_overlay', p)
overlay = importlib.util.module_from_spec(spec)
spec.loader.exec_module(overlay)
names = ['test_offline_transcription_input_guards', 'test_body_size_and_object_validation',
         'test_no_public_token_or_cross_origin_access',
         'test_memory_inspection_fallback_and_bounded_identifiers',
         'test_paid_and_local_only_blocked', 'test_baseline_sqlite_migration_and_preferences']
suite = unittest.defaultTestLoader.loadTestsFromNames([
    'backend.tests.test_delivery_contract.DeliveryContractTests.' + name for name in names])
result = unittest.TextTestRunner(verbosity=2).run(suite)
raise SystemExit(not result.wasSuccessful())
```

Ejecutar mediante `python -B -`; no copiar los módulos del borrador al freeze para probarlos. Tras integrar, repetir estos contratos sobre los módulos integrados y probar por HTTP el nuevo endpoint con barreras inertes. La UI/micrófono/voz/dictado real y la versión instalada siguen pendientes del integrador. Restaurar el par de fuentes base revierte este borrador; no borrar transcripciones, preferencias ni datos del usuario.
