# Integración de Axx · fase 4

Verificación del 10 de noviembre de 2026 en codex/axx-phase-4. Código evaluado en 7eb0f792b5db127b843f3e4b18c047daea8a3481.

## Historial y alcance

El HEAD local y remoto de main coincidió en dfe3d5a27e2830eb7cf1cb3a2aa0707d4e117dc4. Ese commit es el padre de 9fe55a2. Su incorporación selectiva produjo 31c75bff36a175aa7322565b8979b83d4d74eeeb. El inventario de 99 referencias del repositorio está en build/phase4/ref-inventory.txt. Las 33 ramas consultadas directamente en origin están en build/phase4/remote-ref-inventory.txt.

Se contrastaron los cuatro informes CLAUDE-PHASE3 y los seis documentos de docs/phase-2. Se adaptaron las correcciones de autoridad y supervisión de b753903, la procedencia de d2241a3, el timeout de inventario de 7281c00 y la titularidad de aa2802c sobre los archivos actuales. El parche de sintaxis 0bbab0f de la rama antigua carecía de equivalente pendiente en main. La suite Magic Pen sobre el renderer moderno pasó.

El worktree de integración es independiente. Las referencias main y codex/axx-phase-2 y el worktree de los cambios locales previos permanecen en sus commits de origen.

## Cierre de hallazgos de Claude

| Hallazgo | Cambio y verificación |
|---|---|
| R-01 | Bearers separados por canal y por instancia. HTTP real del daemon, titularidad Telegram, revocación y ausencia de efecto probadas con una cuenta sintética. |
| R-02 | Límite literal de 48 en prueba y prompt. 48 pasa y 49 falla. Se detecta la mutación a 1000. |
| R-03 y R-04 | Unrestricted local exige consentimiento por conversación. Se permiten efectos locales tipados y escritura acotada de texto. Descarga y exportación PDF, lecturas de contenido privado y ejecución arbitraria conservan revisión. El modelo nunca hereda Unrestricted. |
| R-05 | La espera de aprobación se limita a canal y conversación. Una preparación rechazada genera bloqueo sin inventar un identificador. Se conserva la exclusión para recursos del ejecutor Windows. |
| R-06 | Se conserva el contrato /v1. Work aplica la revisión de PC ya representable por el estado awaiting_pc_approval. Los recibos de Work se limitan al dispositivo propietario. |
| R-07 | El test observa la transición de interacción del avatar. El mensaje transitorio vuelve al estado de actividad tras 1800 ms. |
| R-08 | El texto original y el estado del recibo se muestran juntos. Los detalles del ejecutor quedan en Comandos y fuera del historial que se puede reenviar al proveedor. |
| R-09 | El proveedor guardado chatgpt pasa por el wrapper de Axx Connect hacia Codex. La ruta OAuth obsoleta conserva su rechazo explícito. El contrato Chromium cubre la preferencia persistida y la ruta oficial. |

El primer barrido general detectó dos observaciones Computer Use bloqueadas por revisión duplicada. La ruta vuelve a comprobar el permiso propio y el ticket efímero en el despacho y conserva la revisión general para los demás efectos del modelo. Se verifican tickets falsos y revocados sin captura ni entrada. Se conserva el CMD por voz revisado de main. El callback Telegram consume cuerpos pequeños acotados antes del rechazo para evitar un reset TCP en Windows.

La prueba de cancelación nativa inicial estaba midiendo también el arranque de la conexión MCP. El fixture inicializa ese transporte antes de esperar la entrada al cuerpo que se va a cancelar. Mantiene los plazos anteriores.

La matriz de aceptación y los límites de cada prueba están en PHASE4-REGRESSION-RESULTS.md y PHASE4-RELEASE-CANDIDATE.md.
