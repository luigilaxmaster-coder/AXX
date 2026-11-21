Fecha: 2026-11-21. Base: `2f177ea` (PR #6). Rama: `codex/axx-evolution-3-audit-visual-3d-chatgpt`. Mejoras: [Draft PR #7](https://github.com/luigilaxmaster-coder/AXX/pull/7).

# Revisión de seguridad

Se corrigieron pérdida de worktrees, identidad de proyecto mutable, dispatch sin aprobación, flags ignoradas, booleanos ambiguos y rutas de exportación sin validar. Todos los endpoints siguen detrás de autenticación host, bloqueo Origin y loopback existentes. La desactivación deja disponibles cancelación/limpieza para no atrapar operaciones en vuelo. Las pruebas de seguridad negativas no cambian expectativas para ocultar efectos.

Las rutas sin backend real devuelven no disponible. WSL comparte distribución y acceso potencial a archivos del host; no es un sandbox para código adversario ni tiene límites RAM/vCPU efectivos por workspace. Worktrees y subprocess no se anuncian como sandboxes. Ejecutar pruebas del proyecto ejecuta su código con la cuenta local y exige opt-in explícito.

Secretos y datos: se preservaron login, credenciales, pairing, grants, memoria, voz y ajustes de la instalación habitual. No se copiaron DB reales ni muestras de voz al repositorio. Las muestras de proveedor son sintéticas; informes/capturas de ejecución privados no se publican automáticamente.

Pendientes: auditoría completa de transitorias del nuevo kernel, verificación del backend congelado/instalador, persistencia de drafts de editor no guardados y carreras con escritores externos que no respeten locks cooperativos. No hay garantía global de ausencia de vulnerabilidades. El bundle precompilado de Monaco incluía DOMPurify 3.4.15 con avisos bajos. Se fijó 3.4.18 y se compila desde ESM con esbuild 0.28.2; el metafile comprueba que la dependencia corregida entra en el bundle, no solo en el lockfile. npm audit final: cero avisos conocidos; no es una garantía de seguridad universal. Referencia primaria: [DOMPurify 3.4.18](https://github.com/cure53/DOMPurify/releases/tag/3.4.18). El AMD anterior se conserva fuera de los assets distribuibles, en evidencia ignorada.

D24 cierra el bypass de metadatos Git por capitalización, profundidad y alias con punto/espacio final de Windows. Se conserva `.github`; la regresión exige rechazo antes de leer o escribir y verifica bytes intactos.
