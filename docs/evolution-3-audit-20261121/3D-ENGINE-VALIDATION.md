Fecha: 2026-11-21. Base: `2f177ea` (PR #6). Rama: `codex/axx-evolution-3-audit-visual-3d-chatgpt`. Mejoras: [Draft PR #7](https://github.com/luigilaxmaster-coder/AXX/pull/7).

# Validación geométrica y CAD

El generador anterior producía `MANIFOLD_SOLID_BREP` apuntando a `BLOCK`; su comprobación regex aceptaba datos que el lector OpenCascade no convertía en sólidos. La nueva implementación usa CadQuery 2.8.0/OpenCascade y verifica importación STEP, volumen positivo y validez de todos los sólidos.

GLB ahora tiene malla/accesores propios por pieza, normales orientadas, coordenadas en metros, rotación Z-up a Y-up para glTF y posiciones/rotaciones/explode aplicados igual que en STEP. La congruencia lee posiciones binarias; no confía únicamente en extras de metadata. Pruebas: caja rotada y tubo con volumen analítico en mm, cm, m, in y ft, distinción de mallas, worker real, timeout de 0,4 s y recuperación. La tolerancia física es explícita. Se conserva la distinción conceptual/documentado; no se certifica ingeniería, FEM ni CFD.

El worker tiene 45 s de plazo por defecto para incluir arranque frío del kernel nativo. La prueba anterior de 10 s era insuficiente con el kernel real bajo carga; se conserva la prueba de interrupción corta. `requirements-cad.txt` se instala en el Python de build/worker; PyInstaller deja de excluir SciPy y recoge licencias CAD. La aceptación de ese paquete congelado sigue pendiente: la candidata nativa de esta auditoría usa backend fuente Python.

Limitaciones abiertas: sección geométrica no aplicada por el worker; parámetros de recinto requieren wall_thickness; la placa preset usa un taladro central y no describe una distribución arbitraria de agujeros. La UI CAD v2 y el visor legacy no están conectados de extremo a extremo. No se acredita importación GLB arbitraria en la UI, raycasting v2, calibración de varios DPI, clipping 3D ni benchmark prolongado de GPU. No se modificaron materiales/cámara del avatar.

Evidencia: `step-before.json` (validador anterior true, lector 0 sólidos), `cad-final.log`, `backend/tests/test_cad_studio.py`, `evolution-final.log`.

Se probó también el worker CAD del backend PyInstaller sobre f2ce6b0: STEP con dos sólidos reimportados (volúmenes 24.0 y 11.78097245 mm3), GLB dos nodos y congruencia física, 27.969 s. Inventario onedir y licencias CadQuery/OCP/VTK verificados. Esto sigue siendo distinto de aceptación del instalador completo; el guard de raíz Git posterior requiere reconstrucción final, cuyo cierre se registra en el PR.
