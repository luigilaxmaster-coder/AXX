# Renderizado de conexiones del avatar

## Geometría y material

`OrganicTendrils`, en `1.AXX/Axx.html`, dibuja un barrido tubular en el plano de
pantalla con sección circular y normales de volumen. Reutiliza la tabla de
iluminación y la paleta del avatar. No sustituye las formas ni usa WebGL.

- `fitTendrilLink` consulta la silueta del raster actual. Busca una sección sólida
  para enterrar la raíz, ignora partículas sueltas y limita el radio al espacio
  disponible. La punta se introduce bajo el icono; un destino superpuesto no
  genera un tubo que sobresalga detrás.
- `organicCurve` mantiene los extremos y limita la curvatura y la ondulación.
- `flowArmRadius` afina la sección sin un abultamiento final. El cierre de la
  punta se mide en píxeles para que no se estire con una conexión larga.
- Las conexiones se dibujan al terminar la tarea del cuadro, antes de componer
  la pantalla. Así consultan la misma silueta que acaba de dibujar el avatar,
  evitando una unión calculada con la forma del cuadro anterior.
- La curva central se muestrea cada dos píxeles aproximadamente, con límites de
  64–1.024 segmentos. Las derivadas se interpolan entre muestras. El sombreado
  no utiliza caras triangulares longitudinales ni facetas alrededor del tubo.

Para cada píxel se calcula su posición transversal y la normal de la sección.
La normal incorpora la tangente de la curva y la variación de radio. Los modos
de material, arcilla, normales y rejilla conservan su representación.

## Nitidez y coste

El raster se orienta según el enlace. Así, un tubo diagonal ocupa una franja
estrecha y no el rectángulo completo entre sus extremos. La salida usa una
densidad superior al píxel nativo, cobertura fraccional del contorno y filtrado
de alta calidad al componerla. Los reflejos se filtran en la tabla de material;
no se desenfoca el objeto completo ni se añaden sombras CSS que dejen rastros.

El presupuesto objetivo es 2,6 millones de píxeles por franja, con dimensiones
cuantizadas para reducir reasignaciones y un límite longitudinal de 8.192. Las
pruebas exigen menos de cuatro millones de píxeles tras el redondeo. Los buffers
de enlaces retirados se liberan. La tabla filtrada se reconstruye cuando cambia
el material, no en cada cuadro.

## Verificación

```powershell
node scripts/test-tendril-geometry.cjs
node scripts/test-installed-tendril-quality.cjs
node scripts/test-installed-tentacles.cjs
```

Las dos últimas pruebas requieren la app instalada y CDP temporal en loopback
9224. Se ejecutan de una en una. La prueba de calidad recorre 60 combinaciones de
distancia, dirección y densidad; comprueba cobertura continua, suavizado,
recorte y memoria. Sus tiempos son coste del dibujo de una franja, no FPS de la
aplicación ni una garantía para otros equipos.

La aceptación visual utiliza capturas nativas, arrastre, uniones cercanas y
extendidas, tres siluetas, ambos temas y retracción completa. Guarda los recibos
privados en `build/chat-0.21.4/tentacles/`. Una vista previa inyectada para diseño
debe llevar `source_preview: true`; hay que repetir la aceptación después de
compilar e instalar. Al terminar, arrancar normalmente sin CDP.
