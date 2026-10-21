# Axx Connect 0.1.2

Plugin privado para hosts locales compatibles en Windows. Reutiliza el backend autenticado y los ejecutores de Axx; no contiene otro asistente.

Desde la raíz fuente: `powershell -NoProfile -ExecutionPolicy Bypass -File scripts/install-axx-connect.ps1`.

El instalador registra el marketplace local `axx-local`, instala `axx-connect@axx-local` y guarda solamente la ubicación del runtime. El modo fuente requiere Python y el entorno aislado `.venv-axx-connect`; el modo empaquetado usa el backend de Axx con `--mcp-server`, sin Python adicional.

Los manifiestos portables `plugin.json`/`mcp.json` y los archivos de compatibilidad `.codex-plugin/plugin.json`/`.mcp.json` describen el mismo servidor. Cada host elige un formato; no deben fusionarse ni registrarse dos servidores.

El formato Codex declara `env_vars: ["AXX_CONNECT_DATA_DIR"]`, documentado por el host, para pruebas con una instancia aislada. El esquema portable 1.0.0 admite `env` pero no `env_vars`; no se añadió un campo incompatible. Sin override se usa la instancia local del usuario en ambos formatos.

En el formato Codex los plazos de inicio y herramienta se fijan en 30 segundos. Si el catálogo inicial aparece vacío, consulta el diagnóstico MCP del host: el tiempo de gracia para servidores opcionales es un ajuste independiente. Una prueba aislada puede usar `mcp_optional_startup_grace_ms=0` sólo en su proceso. No se cambian las aprobaciones del host.

Comprueba `axx_status`, descubre capacidades y verifica una llamada real. Instalar el paquete no demuestra conexión. Documentación completa: `docs/axx-connect/README.md` en el proyecto.
