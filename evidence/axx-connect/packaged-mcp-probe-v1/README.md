# Chequeo del MCP empaquetado

Estado: **PREPARADO; NO EJECUTADO CONTRA NINGÚN `axx-backend.exe`**.

`verify_packaged_mcp_stdio.py` valida el SHA del EXE contra el recibo del build, confirma que las fuentes MCP y ASR aún coinciden con dicho recibo, y luego habla el protocolo stdio con el binario congelado. Envía únicamente `initialize`, `notifications/initialized` y `tools/list`. No invoca herramientas, no inicia una cuenta/modelo y no hace inferencia.

El proceso hijo recibe un `PATH` limitado a `System32`, sin rutas de Python o Node. La prueba usa el usuario actual para poder acceder al descriptor local protegido por DPAPI, aunque `tools/list` no lo consulta. stdout debe contener exclusivamente JSON-RPC válido. El proceso debe cerrar correctamente al recibir EOF.

Ejecutar sólo después de que el operador cierre el build final y entregue su `build-result.json` y `build/backend-build-receipt.json`:

```powershell
python evidence\axx-connect\packaged-mcp-probe-v1\verify_packaged_mcp_stdio.py `
  --exe build\connected-0.22.3-20261020\dist\axx-backend.exe `
  --source-root build\connected-0.22.3-20261020 `
  --receipt build\connected-0.22.3-20261020\build\backend-build-receipt.json `
  --expected-sha256 <sha256-de-dist-axx-backend-exe> `
  --report evidence\axx-connect\packaged-mcp-probe-v1\result.json
```

El resultado sólo acredita inicio MCP, negociación y catálogo de herramientas del EXE probado. No acredita ASR ejecutado, instalación, uso del micrófono ni aislamiento completo de las herramientas incorporadas de Codex.
