# Revisión de bounds del raster: resultado finito, sin parche

Fecha UTC: 2026-10-20T20:14:57.481648+00:00

## Fuente actual y cambios del propietario

- Candidato: `C:\Users\luigi\Desktop\Axx assistant\build\phased-ux-20261020\1.AXX\Axx.html`.
- SHA256 inicial: `BAA9979169C0EE6D2FCDF6ACB89575A9D5AC4A7CF66B24442380C3B985C2D6F1`.
- SHA256 final: `05A562B622317A56BE1470A738EDBAF9EED5369E377DFECEEAB639E500E2A9FB`.
- Hash estable durante esta prueba: **false**.
- Fuente canónica anterior usada únicamente como RED: `C:\Users\luigi\Desktop\Axx assistant\1.AXX\Axx.html`, SHA256 `AB498F1A138C603617CC12A58C9F4F76317DBFEDEBE1FB11DDF78711361AE7A8`.

El propietario cambió legítimamente `organicCurve` a `-Math.tanh(dx / 90)` y `actionArmOffset` a bandas80–180/110–210 con lado `tanh(... / 100)`. El bounds sigue usando padding170/104. La propuesta anterior de dos funciones `root-history-geometry-20261020.patch` tiene un baseline anterior y NO corresponde aplicar encima del nuevo trabajo.

## Método ejecutado

VM Node sin navegador/producto. Se extraen de ambos HTML las funciones reales `organicCurve`, `actionArmOffset`, `flowArmRadius` y el método `OrganicTendrils.tube`; el método real ejecuta sus escrituras de vértices Float32 con U24/V56. Se sustituyen solo destino Canvas, resolver de píxeles y rasterizador de triángulos por sumideros sin efectos. Cada vértice se compara con ancho/alto del raster realmente asignado, incluida la cuantización a16px; no basta comparar con el pad nominal.

Se recorren grosores reales del ajuste65%/110%/155%, progresos0.005/0.1/0.5/1, fases0/1.7, quiet normal/reducido, ruta activada/desactivada, raíces x500/1400, dx±150/±50/±1/±0.1/0 y dy80/120/180/400/800/1000 sobre viewport1920. La fixture temporal fue retirada al finalizar. No se ejecuta Axx, navegador, audio, GUI, instalación ni build.

```json
{
  "canonical_AB": {
    "cases": 10368,
    "casesWithVerticesOutsideRaster": 99,
    "worst": {
      "route": true,
      "quiet": false,
      "thickness": 1.55,
      "ax": 1400,
      "dx": -1,
      "dy": 400,
      "progress": 1,
      "phase": 1.7,
      "outsideVertices": 262,
      "maxOverflowCSS": 26.47767633380312,
      "arena": {
        "left": 1229,
        "top": -130,
        "width": 358.7878787878788,
        "height": 753.4545454545455,
        "rasterW": 640,
        "rasterH": 1344
      }
    },
    "examples": [
      {
        "route": true,
        "quiet": false,
        "thickness": 0.65,
        "ax": 500,
        "dx": 0,
        "dy": 400,
        "progress": 1,
        "phase": 0,
        "outsideVertices": 201,
        "maxOverflowCSS": 12.404435591264207,
        "arena": {
          "left": 330,
          "top": -130,
          "width": 340.8484848484849,
          "height": 753.4545454545455,
          "rasterW": 608,
          "rasterH": 1344
        }
      },
      {
        "route": true,
        "quiet": false,
        "thickness": 0.65,
        "ax": 500,
        "dx": 0,
        "dy": 400,
        "progress": 1,
        "phase": 1.7,
        "outsideVertices": 116,
        "maxOverflowCSS": 8.104973070549244,
        "arena": {
          "left": 330,
          "top": -130,
          "width": 340.8484848484849,
          "height": 753.4545454545455,
          "rasterW": 608,
          "rasterH": 1344
        }
      },
      {
        "route": true,
        "quiet": false,
        "thickness": 0.65,
        "ax": 1400,
        "dx": -1,
        "dy": 400,
        "progress": 1,
        "phase": 0,
        "outsideVertices": 226,
        "maxOverflowCSS": 12.75271326122862,
        "arena": {
          "left": 1229,
          "top": -130,
          "width": 358.7878787878788,
          "height": 753.4545454545455,
          "rasterW": 640,
          "rasterH": 1344
        }
      }
    ]
  },
  "stage_current": {
    "cases": 10368,
    "casesWithVerticesOutsideRaster": 0,
    "worst": null,
    "examples": []
  },
  "method": "Exact extracted tube and curve/radius functions, actual Float32 vertex writes. CPU triangle/pixel resolver/Canvas stubbed; compare every mesh vertex with actual allocated raster extents including 16px buffer rounding.",
  "U": 24,
  "V": 56,
  "widthCSS": 1920,
  "thicknesses": [
    0.65,
    1.1,
    1.55
  ],
  "progress": [
    0.005,
    0.1,
    0.5,
    1
  ],
  "phase": [
    0,
    1.7
  ],
  "quiet": [
    false,
    true
  ],
  "route": [
    false,
    true
  ],
  "meshVerticesPerCase": 1425,
  "gui": false,
  "productProcesses": false,
  "visualAcceptance": false
}
```

## Decisión y límites

El RED anterior contiene vértices fuera del raster en los casos registrados. En el candidato actual no se observa ese fallo dentro de esta búsqueda finita: las bandas más amplias del propietario reducen la excursión lateral. Por ello NO se genera ni aplica un parche de bounds contra el candidato actual; no hay un caso actual reproducido que justifique cambiar el renderer en esta revisión.

Este resultado no demuestra ausencia global de cortes. No prueba píxeles, clipping del canvas exterior/ventana nativa, leases, IPC, DWM ni aceptación visual. Tampoco es una prueba del ajuste temporal del brazo. Si reaparece corte instalado, capturar el link/progress/phase/thickness exacto y la geometría nativa antes de cambiar el bounds. Material, malla, thinning, quiet motion, preferencias, identidad24formas/9paletas y fuentes productivas permanecen intactos porque esta tarea solo escribió este documento.
