# Recuperación Optical Glass / Magic Pen

Fecha: 2026-11-13. Revisión propia, sin revisor independiente.

## Estado

**Candidata 0.22.48 validada en WebView2; NO_GO_RELEASE mientras sigan abiertos los bloqueantes de conexiones.** Código subido, sin integración en `main`, instalación personal ni publicación.
Base remota verificada: `b3231e83166df83a77b947b18b40ce91529d4eb2` (`origin/main`, 0.22.47).
Rama: `codex/axx-optical-glass-magicpen-recovery`.
Worktree: `C:\Users\luigi\.codex\worktrees\axx-optical-glass-magicpen-recovery\axx2`.

El checkout original está en `codex/mobile-companion-20261028`, con cambios de voz sin confirmar. No se copiaron ni sobrescribieron. El `main` local de otro worktree está atrasado respecto a `origin/main`; no se movió ni se limpió. La base remota contiene la integración de Fases 6, 7 y 8 y su publicación 0.22.47. No se modifican las fuentes de micrófono, Handy, WASAPI, VAD, Whisper, Parakeet, atajos o coordinación de voz.

## Optical Glass

Hecho: [PR #5](https://github.com/luigilaxmaster-coder/AXX/pull/5), HEAD `3fd045ce5a1bd8db5f012738a8289046b8399929`, sigue abierta y no fusionada. Su archivo no está en el historial de `origin/main`. La integración 0.22.47 no incluía el módulo. No hay evidencia de que el actualizador borrase un material ya integrado en `main`.

Se recuperaron selectivamente `optical-glass.js`, sus cinco presets, la prueba y la documentación. No se fusionó el HTML antiguo de la rama. Se incorporó el acabado al selector actual y se trasladó ese único selector a «Forma y materiales». Se corrigieron el guardado inmediato de los sliders, la reversión de la óptica, su inclusión en estilos guardados, los límites de valores persistidos y una referencia global incorrecta en estados con forma no bloqueada.

Obsidian, Prism y Smoke conservan su implementación. El módulo solo transforma la LUT cuando se selecciona Optical Glass. Los tentáculos consumen la misma LUT y clave de caché. No se cambian geometría, curvas, radios, raíces ni anclajes. El alfa de material sigue en 255. La translucidez es una aproximación por luz y reflejos; no hay refracción física del escritorio.

## PR #3 y #4 / Magic Pen

[PR #3](https://github.com/luigilaxmaster-coder/AXX/pull/3), HEAD `0f9b58c99d5cb9773bce5b4224d720c1e3cfbb88`, y [PR #4](https://github.com/luigilaxmaster-coder/AXX/pull/4), HEAD `2bd5c99cdbb7bce6aada9cd4e068ffed77b23a27`, siguen abiertas, pero sus soluciones ya existen en la base actual: normalización de IDs y referencias, JSON delimitado, diagrama ilustrativo 2D desde prosa con aviso, esquemas estrictos y diagnóstico de truncamiento. `presentation_plan.py` no se reemplazó por las versiones antiguas.

Defectos reproducidos y corregidos:

| Etapa | Defecto | Corrección y comprobación |
| --- | --- | --- |
| Ejecución | El adaptador aceptaba 240/300 s pero serializaba como máximo 70 s al worker. | Conserva el plazo acotado hasta 300 s; prueba roja antes y verde después; cancelación conservada. |
| Transporte | Planes visuales pequeños y pruebas de aptitud usaban el timeout de chat de 20/60 s. | Las solicitudes `vision` usan su plazo propio; el chat mantiene su timeout. Prueba roja/verde. |
| Recepción/UI | El polling cancelaba todas las presentaciones a los 80 s. | Espera acotada de 600 s para identificación + generación + una reparación; texto mantiene 80 s. |
| Coste | La prueba de aptitud omitía el presupuesto y el registro de uso. | Comprueba el límite antes de llamar y registra el consumo aun si el plan no valida; dos pruebas rojas/verdes. |

El JSON sigue validándose antes de persistir o renderizar. Una escena 3D explícita necesita `scene`; no se declara éxito 3D por texto. El fallback ilustrativo 2D conserva su aviso. Los tests cubren captura/selección, revisión, cancelación, cierre, recuperación, referencias de escena, modificaciones y límites.

## Modelos reales

Las llamadas usan las conexiones existentes y sus autorizaciones; no se publican claves, cuerpos de autenticación ni capturas personales. El recibo privado `build/recovery/providers.json` registra las 29 entradas y separa catálogo, respuesta y aptitud. Es una auditoría directa del adaptador: no arranca los gateways auxiliares de la instalación personal. Sus aliases con puertos locales antiguos no se deben presentar como una prueba de caída de todo el servicio instalado.

| Ruta configurada | Resultado observado |
| --- | --- |
| Claude `axx1` / `claude-sonnet-5-5` | Catálogo y respuesta real PASS; imagen, JSON, explicación, 2D y 3D básicos verificados. |
| Claude `axx44` | Respuesta real PASS; esta conexión solo declara texto, no se amplió su permiso a visión. |
| ChatGPT/Codex 0.160.0 / `gpt-6.1-sol` | Cuenta autenticada y catálogo real. La primera prueba visual falló; una ejecución posterior produjo imagen + JSON + escena válidos. No se declara estabilidad prolongada. |
| Gemini `axx55` / `gemini-3.6-flash` | Se observó respuesta real y también timeout. Repetición final: modelo presente en catálogo, timeout de texto y prueba visual sin resultado válido. No se declara conexión visual estable. |
| Ollama local / `qwen2.5:3b` | Endpoint local sin respuesta durante la auditoría; existen manifiestos locales Qwen y Llama. El intento de iniciar el servidor fue rechazado por la revisión automática de la herramienta (`blocked by policy`); no se ejecutó. No se descargaron modelos ni se cambió el modelo guardado. |
| Ollama Cloud `axxx3` / `gemma4:31b` | Modelo en catálogo; la petición real recibió exigencia de pago. No se activó fallback de pago. |
| OpenRouter gratis | Catálogo accesible; sin credencial disponible para una respuesta satisfactoria. La ausencia en una lista truncada no demuestra inexistencia del modelo. |
| `gemini-free-tier` | Deshabilitada y sin autorización de gasto; no se activó. |
| FreeLLMAPI y aliases locales restantes | Fallos de endpoint/cuota/solicitud registrados individualmente en el recibo; no se reescribieron puertos, credenciales ni conexiones personales. |
| OpenAI API directa | No hay una conexión directa configurada; ChatGPT/Codex se verifica por separado. |

Flujo con Claude e imagen sintética propia, a través de `MagicPenService`, router y proveedor reales:

| Solicitud | Resultado | Tiempo observado |
| --- | --- | --- |
| Diagrama 2D | Dos pasos, diagrama presente, sin escena 3D | 9.33 s |
| Escena 3D | Dos pasos y dos piezas reales de plan validado | 26.16 s |
| Continuación | Conserva ambas piezas y cambia la primera a `#22aa55` | 5.97 s |

Las respuestas y el documento persisten en almacenamiento aislado. Esos planes no equivalen por sí solos a aceptación gráfica: el renderizado WebView2 tiene su recibo separado.

## Pruebas y evidencia

Evidencia privada bajo `build/recovery/`, excluida de Git. No publicar perfiles, capturas de escritorio, claves DPAPI ni estado de runtime.

| Comprobación | Estado registrado |
| --- | --- |
| Python Magic Pen, HTTP, planes, proveedores, transporte, router y capacidad Codex | 199 PASS; más 29 PASS tras el ajuste final de timeout. Los avisos WinError 10038 al cerrar algunos servidores fixture también aparecen en la base. |
| Optical Glass unitario y geometría de tentáculos | PASS. |
| Fase 7 + presets, guardar/descartar, reinicio, ambos temas, 24 formas y nueve paletas | PASS. |
| Chat básico, formas técnicas/espaciales y diagramas | PASS. |
| Dictado y dictado global, fixtures sin micrófono físico | PASS; fuentes sin cambios. |
| Suite providers | FAIL también en copia intacta de `origin/main`: fixture de memoria obsoleta (`AbortError`, línea 148). |
| Compositor de herramientas | PASS final, nueve comprobaciones, ejecutado en serie tras cerrar compilaciones/candidata. La copia intacta de `origin/main` también pasa. Hubo timeouts intermitentes de la fixture bajo carga concurrente; no se ocultaron ni se aumentaron sus límites. |
| Magic Pen navegador, prueba del plazo largo | PASS completo, incluida respuesta tras superar 80 s. Se estabilizó únicamente el fixture de narración para simular una lectura aún ocupada; no se cambió voz productiva. |
| Gate PC/Android | PASS final: 15 contratos, 113 backend (1 omisión preexistente), 58 navegador y 8 selector. Recibo `companion-final.json` sobre la fuente final. El primer recibo quedó invalidado correctamente al cambiar la fuente durante su ejecución. |
| Rust | 27 PASS, 2 pruebas optativas ignoradas; sin pruebas físicas de micrófono. |
| Candidata WebView2 | PASS; motor real 157.0.4341.46, IPC y backend empaquetados. Perfil aislado `com.axx.recovery`, capturas de ambos temas, captura nativa de pantalla, 2D y 3D renderizados y modificación real desde el compositor. |
| Release y manifiestos | 24 pruebas PASS; `release.py check` PASS. Se volvió a sincronizar el README tras crear las notas nuevas. |
| CI remoto | El gate compañero del primer commit pasó. La comprobación de versión pasa tras sincronizar el índice. Se corrigió el Python 3.11 de CI, incompatible con el PyAV 19.0.2 ya fijado, usando 3.12 sin cambiar dependencias de voz. CI descubrió además una carrera de la fixture de grabación: su sondeo volvía a marcar listo un backend que la prueba había puesto en falso. Se estabilizó la disponibilidad simulada conservando la misma aserción; seis comprobaciones locales PASS. La batería remota completa posterior sigue pendiente; no se declara CI completamente verde. |

### Aceptación gráfica nativa

Recibo: `build/recovery/native-acceptance.json`, resultado final **PASS**. Los SHA de los tres módulos servidos por WebView2 coinciden con la fuente. `native-optical-light.png` y `native-optical-dark.png` fueron inspeccionadas visualmente: selector único, cinco presets, colores de ambos temas y avatar con el acabado recuperado.

La restauración de Obsidian compara todos los bytes de su LUT, no una muestra. Los cinco presets mantienen alfa 255 y consumo de material por los tentáculos. El barrido nativo existente de calidad cubre 60 combinaciones de longitud/ángulo/DPR sin huecos interiores ni recortes: mediana 4.4 ms y p95 41.3 ms por tubo en el ensayo final. No es una garantía de FPS sostenidos.

La LUT óptica se recalculó en 370–500 ms en el ensayo final, con caché de 0–0.1 ms. Un ensayo anterior bajo carga concurrente midió 1.08–1.38 s y hasta 0.2 ms de caché. Cambiar parámetros puede bloquear brevemente el hilo de interfaz; no se redujo resolución ni calidad para ocultarlo.

`native-real-3d.png` muestra el plan real de Claude como **dos objetos y 2668 triángulos WebGL**, con coordenadas finitas y contexto gráfico válido. Desde el compositor de la candidata, el backend empaquetado volvió a consultar Claude y cambió la primera pieza a `#ff9922`, conservando ambas. `native-real-2d.png` muestra el diagrama real. El micrófono permaneció cerrado. La instalación personal conservó su SHA durante el ensayo y el proceso de candidata se cerró al terminar.

Los primeros intentos del harness fallaron por una carrera al localizar la página recién creada y por copiar el documento sintético fuera de `artifacts/`. Se corrigió el harness; esos dos errores no se clasifican como defectos del producto.

Comandos reproducibles:

```powershell
node scripts/test-optical-glass.cjs
node scripts/test-tendril-geometry.cjs
node 1.AXX/scripts/phase7-ui-harness.cjs test
node 1.AXX/scripts/test-magic-pen.cjs
python -m unittest backend.tests.test_magic_pen backend.tests.test_magic_pen_http backend.tests.test_presentation_plan backend.tests.test_provider_aptitude backend.tests.test_provider_settings backend.inference.tests.test_adapter_cancellation backend.inference.tests.test_hardened_router backend.inference.tests.test_spatial_transport backend.connect.tests.test_provider_capability -q
python scripts/verify-recovery-providers.py --config "$env:LOCALAPPDATA\Axx\providers.json" --output build/recovery/providers.json --vision --codex
python scripts/verify-recovery-providers.py --config "$env:LOCALAPPDATA\Axx\providers.json" --output build/recovery/claude-flow.json --name axx1 --vision --flow
python scripts/validate_companion.py --output build/recovery/companion-final.json
node scripts/verify-recovery-native.cjs <ruta-a-AxxRecovery.exe>
```

Los tests JavaScript requieren Playwright y `AXX_TEST_CHROMIUM` apuntando al Chromium instalado. El harness nativo exige el backend empaquetado y el perfil `com.axx.recovery`; nunca lanzar la identidad productiva para sustituir esta prueba. La candidata se compila con `src-tauri/tauri.recovery-candidate.conf.json`.

## Entrega, hashes y límites

Código de runtime: **`251929050d40417dcab536dee5c149971dabb466`**, confirmado en GitHub en la rama de recuperación. Los cambios posteriores del harness y de este informe no alteran las fuentes del runtime probado. `build/recovery/source-manifest.json` verifica sus hashes. La versión se sincronizó con `release.py sync --version 0.22.48`; Android permanece en 0.2.14.

| Artefacto privado | Bytes | SHA-256 |
| --- | --- | --- |
| `AxxRecovery.exe` debug aislado | 22083072 | `7b0626ebd95afeba4eb73644a90a910850660f6b39971bee0bbb65d01ab6cd97` |
| `axx-backend.exe` empaquetado | 23240146 | `718216c129f7a67e72b6e23e1e91f63346712bc67ac4a0c0a3d64d9e0d6f0c16` |
| Worker ASR existente, fuentes sin cambios y bytes reutilizados | 3707392 | `688a9a5206d366f30582404ee7729fffb53c3bdee808916bb3fe1d3efde5367e` |

El host está en `C:\Users\luigi\.codex\builds\axx-recovery48-target\debug\AxxRecovery.exe`; el backend y recursos tienen inventario verificado en `build/recovery/backend/backend-bundle.json`. Es una candidata privada debug, no un instalador de producción. No se reutilizó 0.22.47 para sus binarios. La instalación 0.22.47 observada antes/después mantiene `fd1a784a7a4bbfcc952d339bd6c9fa59ae642aa3b1edd78aedab3c23c05a6761`.

No se ha fusionado en `main`, instalado ni publicado 0.22.48. No se ha reemplazado un asset de 0.22.47. La instalación personal observada es 0.22.47; no se han borrado ajustes, enlaces, historial ni modelos. No se ha ejecutado rollback ni instalación sobre datos reales. El nuevo acabado no se acredita en el APK instalado ni en dispositivos físicos.

Bloqueantes de entrega: reconciliar los endpoints/credenciales/cuotas de las conexiones que no responden, comprobar estabilidad de las rutas intermitentes y cerrar la batería remota completa. No se puede verificar una respuesta autenticada de una conexión sin su credencial ni eliminar un requisito de pago del proveedor modificando Axx. Después: backup comprobado, ensayo de rollback, build de producción, instalación y verificación oficial antes de publicar. No se hizo un backup nuevo ni un rollback de la instalación personal porque no se inició su actualización. No se actualizaron baselines para ocultar fallos. La rama conserva el trabajo verificable sin declarar una actualización completa.
