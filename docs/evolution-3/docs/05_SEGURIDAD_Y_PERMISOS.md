# 05 — Seguridad, permisos, aislamiento y modelo de amenazas

## 5.1 Principio de confianza mínima

`EffectivePermission = UserGrant ∩ ConversationPolicy ∩ AgentPolicy ∩ ProjectACL ∩ ResourcePolicy ∩ RuntimeCapability`. La intersección es del lado del backend; el LLM puede proponer acciones pero no modificar la resolución. Pertenecer a un grupo/equipo, cambiar forma/nombre/rol, importar skill o escribir un prompt no añade permisos. El grant delegado a subagente solo puede ser igual o más estrecho, con caducidad finita y target específico.

Acciones mutantes usan el `CommandService` existente y su journal. No habrá otro endpoint que ejecute comandos arbitrarios como bypass. Endpoints nuevos siguen autorización del host, validación CSRF/origen/identidad según las rutas actuales.

## 5.2 Clases de operaciones

| Nivel | Ejemplo | Política inicial |
|---|---|---|
| `read_scoped` | Leer archivo de proyecto, status Git, diff | Permitido si grant específico |
| `compute_pure` | Analizar AST, compilar en worker aislado | Configurar scope y límites |
| `write_workspace` | Patch de worktree, generar diagrama local | Revisión si no se autorizó policy explícita |
| `host_window` | UIA en ventana concreta | Grant efímero + observación vigente |
| `host_global_input` | Foco/teclas/clic/arrastre Windows | Pedir y obtener lease exclusivo |
| `external_write` | Enviar email, publicar PR, posts, pagos | Confirmación específica por destino/argumentos |
| `privileged` | Credenciales, elevar permisos, instalar drivers | No automático; flujo separado autorizado |

Modo `auto_safe` **no debe autorizar** acciones que los contratos actuales de AXX obligan a revisar. Nunca traducir el `unrestricted` guardado del chat en `bypassPermissions` de un proveedor; el backend sigue su política propia.

## 5.3 Amenazas relevantes

| Amenaza | Ataque | Control |
|---|---|---|
| Prompt injection | README, página web o asset exige exfiltrar datos | Rutas de data sin autoridad, aislamiento de instrucciones, scope de tools |
| Handoff confused deputy | Agente receptor usa permiso mayor | Contexto/actor firmado por backend, atenuación de permisos |
| Cross-tenant leak | Un bot lee otra conversación | ACL por conversation/project + generation, tests negativos |
| Secret exposure | Token guardado en prompt/export/log | Credenciales referenciadas y write-only, redactado, export limpio |
| Race filesystem | Archivo/symlink cambia tras validación | Handles seguros, resolución y revalidación antes/después, hashes CAS |
| Path traversal | `../` o junction de Windows fuera de root | Canonicalización, volumen/realpath, rechazo reparse points según policy |
| UI spoofing | Ventana falsa reutiliza título/PID | HWND+PID+creation time+observation TTL, verificación de proceso |
| Input collision | Agentes disputan mouse y foco | Lease host único, policy de interferencia, no fallback silencioso |
| Duplicate effects | Reintentar `unknown` | Journal existente, idempotencia y reconciliación |
| Untrusted code | Modelo genera script de instalación | Solo propuesta, revisión, worker aislado real, no host eval |
| Tool discovery abuse | MCP publica comandos nuevos | Allowlist por tool schema, origen y revisión; no auto grant |
| Browser token theft | Reutilizar Chrome personal | Perfiles aislados, no exponer CDP general ni puerto público |
| Supply chain | Asset/code externo con licencia/instrucciones | Pin SHA, SBOM, hash, firma si disponible, revisión de licencia |
| DoS | Agente recursivo o GPU thrash | Budget, TTL, limite fanout, rate limit, ResourceGovernor |

## 5.4 Definición de aislamiento y restricciones Windows

- Virtualenv, Job Object, subprocess y worktree **no** son aislamiento de seguridad completo. Sirven para gestión de dependencias, recursos o archivos, respectivamente.
- Sandbox real requiere límite de procesos, FS, red, privilegios, credenciales y superficie de kernel conforme a riesgo. Windows Sandbox se puede usar en ediciones/entornos compatibles; validar persistencia, host integration y requisitos antes de ofrecerlo como opción. En Linux usar contenedores con no-root, seccomp/apparmor según infraestructura y tests de escape; contenedor sin configuración no es frontera suficientemente fuerte para código hostil.
- No enviar disco completo o credenciales del host a VM remota. Montajes por workspace autorizados y de solo lectura salvo write grant.
- Cursor visual no es input físico independiente. `PostMessage` no equivale a control fiable de un canvas 3D moderno.
- Para host physical control, usar lista de procesos/ventanas que AXX ya bloquea y conservar las reglas de `backend/computer_use.py`.

## 5.5 Gestión de secretos

Windows Credential Manager/DPAPI o almacén seguro existente; credenciales en backend/proceso autorizado, nunca HTML/JS, URL de evento, export de agente, JSON de paquete ni consola. Abrir conexiones de proveedor con tokens de corta duración si infraestructura lo permite. Rotar al revocar. Auditar secretos ya registrados en logs; redactar argumentos sensibles con esquema tipado, no solo regex.

## 5.6 Permisos de archivo y cambios de código

Validar proyecto y raíz explícita; escritura de agente preferentemente solo en worktree. En Windows, revisar junctions, symlinks, path UNC, casos de mayúsculas/minúsculas, alternate data streams y archivos de sistema; rechazar rutas que salgan del perímetro autorizado tras resolver. Comparar `SHA256` de origen antes de aplicar patch; guardar backup/reflog si corresponde. No restaurar/modificar cambios del usuario automáticamente.

## 5.7 Permisos de otros agentes

`TeamACL`: conocimiento público del proyecto no equivale a memoria personal; no compartir contexto de grupos salvo nota explícita. Handoffs contienen `approved_context_refs` inmutables y `tool_grant_refs` no transferibles fuera de sus límites. Cuando se revoca el scope, futuras llamadas se deniegan aunque el modelo mantenga texto en su prompt; no se puede garantizar borrado retroactivo de contenido ya enviado a proveedores externos.

## 5.8 Política de aprobación y auditoría

La tarjeta debe contener: agente, objetivo, comando tipado, argumentos, app/ventana/PID, carpeta/host, impacto probable, fecha/TTL, modo foreground/background/isolated, efectos externos y botón cancelar/denegar. Se firma o liga por ID a los argumentos preparados; cambiar argumentos invalida aprobación. El log registra actor, timestamp, resultado, referencia de postcondición, correlation_id y modo; evita guardar secretos y el texto completo de chats por defecto.

## 5.9 Validación de contenido importado

SVG/HTML de diagramas no se cargan con scripts en WebView privilegiada; sanitizar o renderizar fuera; evitar `foreignObject`, URL remotas o eventos activos. GLB/glTF con límites de tamaño, dimensiones, extensiones y recursos; detectar materiales/texturas excesivos o referencias externas no autorizadas. Modelos importados no se convierten automáticamente en CAD exacto. Archivos ZIP deben controlar zip slip/zip bomb. Procesar upstreams como **datos hostiles** aunque el proyecto raíz tenga MIT.

## 5.10 Aceptación seguridad

Prueba de prompt injection desde README, página y textura; conector MCP alterado; symlink/hardlink race; revocación al vuelo; espera de aprobación sin auto-continue; exposición accidental en SSE; `Last-Event-ID` ajeno; dispatch duplicado; payload sobredimensionado; códigos de error constantes; localhost auth; port binding; pérdida de worker, reinicio y restauración. En caso de incertidumbre: FAIL CLOSED sin corrupción y con mensaje diagnóstico claro.
