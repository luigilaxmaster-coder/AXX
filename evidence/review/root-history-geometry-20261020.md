# Propuesta acotada de continuidad geométrica — no aplicada

Fecha UTC: 2026-10-20T20:11:13.513598+00:00

## Propiedad y alcance

El chat «Verifica AXX por fases» conserva la propiedad del HTML y la integración. Este paquete cambia únicamente dos funciones en una propuesta de diff: `organicCurve` y `actionArmOffset`. No modifica el producto, fuentes del candidato, anclajes, springs, extremo angular, renderer, grosor, materiales, formas, paletas ni preferencias. No se incluye hunk opcional de bounds del raster.

- Destino de revisión: `C:\Users\luigi\Desktop\Axx assistant\build\phased-ux-20261020\1.AXX\Axx.html`.
- SHA256 de lectura inicial: `AB498F1A138C603617CC12A58C9F4F76317DBFEDEBE1FB11DDF78711361AE7A8`.
- SHA256 al terminar: `AB498F1A138C603617CC12A58C9F4F76317DBFEDEBE1FB11DDF78711361AE7A8`.
- Histórico de fórmulas: `C:\Users\luigi\Desktop\Axx assistant\build\functional-repair-0.21.7\1.AXX\Axx.html`.
- SHA256 histórico: `8C7D11804291502B08B6183CAD547148B6E9D3EE11B11DDB7CF4286A1B126605`.
- Archivo de diff: `C:\Users\luigi\Desktop\Axx assistant\evidence\review\root-history-geometry-20261020.patch`.
- SHA256 del diff: `C92016F6B6AF52C0C947A5210AE8A1728510FA7CE00C91FB03B3AA8F2F9A44BB`.
- Baseline estable durante esta generación: **true**.

## Adaptación exacta

`organicCurve`: sustituye únicamente el signo discontinuo del bend por `-Math.tanh(dx / 24)`, fórmula del histórico. Conserva la rama actual `quiet`/fase cero y su ripple sin cambios.

`actionArmOffset`: usa bandas smoothstep 96–144 para distancia vertical y 126–174 para separación horizontal, y `-Math.tanh((a.x - width * .55) / 32)` para el lado, según el histórico. El helper smoothstep es local a esta función y equivalente al `armSmoothstep` histórico; así no requiere una tercera función ni exportación `Axx` ausente en el baseline.

Los comentarios del diff y rutas `a/1.AXX/Axx.html`, `b/1.AXX/Axx.html` permiten revisión por contexto desde la raíz del candidato. **No aplicar todo el HTML histórico ni este diff automáticamente si el propietario ha cambiado las mismas funciones.**

## Validación ejecutada

Node VM, solo funciones extraídas de los bytes reales del baseline y de la propuesta en memoria; sin navegador, audio, GUI, servidor, build ni proceso Axx. Se compilaron las dos funciones en ambas variantes. Inputs con diferencia 0,2 CSS px cruzan cuatro discontinuidades. Los asserts requieren salto RED >100px y GREEN <1px; además comprueban extremos y quiet motion. La fixture se creó en un directorio temporal propio y se retiró al terminar.

```json
{
  "status": "PURE_VM_RED_GREEN_PASS",
  "scripts_compiled": 4,
  "input_delta_css": 0.2,
  "red": {
    "curve_midpoint": 104.09999675000017,
    "route_dx": 125,
    "route_dy": 125,
    "route_side": 250
  },
  "green": {
    "curve_midpoint": 0.5333308120932543,
    "route_dx": 0.781245478877473,
    "route_dy": 0.7812454788774801,
    "route_side": 0.781247456877713
  },
  "assertions": 14,
  "quiet_motion_preserved": true,
  "endpoint_behavior_preserved": true,
  "gui": false,
  "product_processes": false,
  "native_acceptance": false
}
```

## Límites y aceptación pendiente

Esto prueba cuatro cruces finitos y las propiedades indicadas; no demuestra continuidad global, FPS, latencia IPC/PNG, DWM, aceptación visual ni que el brazo deje de recortarse. No suaviza posiciones de anclaje. Los umbrales de selección del extremo y los bounds de raster del candidato actual quedan fuera de estos dos hunks y requieren trabajo separado del propietario. La identidad procedural no se cambia porque el diff solo toca estas dos funciones de trayectoria, pero no se ejecutó una prueba de píxeles ni de las 24 formas/9 paletas.

Próximo paso del integrador: revisar y aplicar por contexto en su copia de trabajo, ejecutar sus verificaciones y aceptar el resultado en Windows de forma serial.
