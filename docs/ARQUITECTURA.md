# Arquitectura del laboratorio

```text
data/raw/mola/
  .img + .xml + .hdr ──▶ data/mola_reader.py (mmap)
                             ├── data/process_mola.py ─────▶ JSON de detalle
                             ├── data/process_mola_global.py ▶ JSON.gz global (1°)
                             └── data/render_mola_preview.py ▶ PNG global (0,5°)
                                      │                 │              │
                                      └─────────────────┴──────────────┘
                                                        ▼
                                                   FastAPI
                               /api/v1/map, /routes y /routes/shelter
                                                        │
                                                        ▼
                                                Frontend Leaflet
                              ├── relieve MOLA global local (0,5°)
                              ├── malla global de rutas (1°) + bloqueos
                              ├── Viking opcional (NASA Mars Trek)
                              ├── nomenclatura visible (NASA/JPL)
                              ├── detalle MOLA local + ruta A* (capas de celdas en canvas)
                              ├── etiquetas de procedencia por capa (provenance)
                              └── Gale: pesos, índice de apantallamiento y alerta solar
```

## Flujo topográfico MOLA

1. Obtén el producto `megt90n000eb` y conserva sin modificar el raster original,
   el label PDS4 `.xml` y el header ENVI `.hdr` bajo `data/raw/mola/`.
2. `data/mola_reader.py` lee las dimensiones y el tipo binario del label PDS4,
   valida el raster y usa `numpy.memmap` para evitar cargar el globo completo.
   El procesador local lee el recorte pedido; el global promedia elevaciones a
   1° y conserva como pendiente de cada celda el máximo de las pendientes MOLA
   nativas incluidas en ella. La periodicidad longitudinal se considera al
   derivar pendientes en la malla global.
3. `data/process_mola.py` convierte el recorte en una cuadrícula JSON pequeña
   en `data/processed/`. Celdas sin dato se marcan inválidas y bloqueadas.
   `data/render_mola_preview.py` genera el PNG equirectangular global de
   `720 × 360` píxeles (0,5° por píxel). `data/process_mola_global.py` genera
   la malla de rutas comprimida y su máscara PNG de celdas bloqueadas.
4. El backend carga las dos cuadrículas MOLA cuando se configura
   `MARS_DATA_SOURCE=mola`. A* usa el mismo `Grid`/`GridCell`; no se modifica
   el algoritmo ni se elimina el dataset sintético.
5. `/api/v1/map` expone el recorte local y la malla global compacta.
   `/api/v1/routes` acepta índices locales heredados o coordenadas geográficas:
   usa detalle si ambos extremos están dentro de la región activa; si no,
   calcula sobre la malla global. Las rutas geográficas incluyen centros de
   celdas para dibujarse directamente en Leaflet.

## Selección de la fuente

- Sin configuración, `MARS_DATA_SOURCE=synthetic` es el valor predeterminado.
- Para MOLA basta `MARS_DATA_SOURCE=mola`: sin más configuración se usa la región
  **Valles Marineris** (`data/processed/mola_valles_marineris.json`, 32 × 32 celdas, 96 bloqueadas
  con umbral de 20°). Para otra región, procésala y apunta `MARS_MOLA_GRID_FILE` al JSON
  dentro de `data/processed/`. La muestra ecuatorial plana (`mola_region.json`) se conserva como control.
- Las rutas fuera de la región activa usan
  `data/processed/mola_global_1deg.json.gz`, de 180 × 360 celdas. La API la carga
  al iniciar el dataset MOLA; por lo tanto ese archivo versionado es necesario
  para la operación MOLA, aunque no se incluya el raster original.
- El recorte admite hasta 250.000 celdas; se prohíbe así exponer la matriz
  global nativa de 16.588.800 celdas a la respuesta JSON y al planificador.
  La malla de 1° tiene 64.800 entradas compactas.
- Los requests de ruta admiten el formato legado de índices y coordenadas
  geográficas MOLA. El cliente no necesita enviar selector de fuente: mapa y
  rutas usan la configuración del backend.

## Frontend

- `js/api.js` solo comunica. `postRoute` añade `slope_weight` y `radiation_weight` únicamente
  si se le pasan; `postShelter` llama a `/routes/shelter`. El backend calcula todas las rutas.
- `js/app.js` muestra las etiquetas de `provenance` (fuente y papel en el costo en el título).
  Si `/map` trae `radiation_available`, también muestra:
  - la tarjeta de pesos;
  - la capa del índice de apantallamiento;
  - la alerta solar.

  En las demás fuentes la interfaz y las solicitudes no cambian. `NO_SHELTER` se presenta
  como resultado del modelo, no como error.
- `js/map.js` dibuja las capas de celdas con `L.canvas()`, con un renderizador por pane:
  elevación, pendiente, riesgo, apantallamiento, cuadrícula y la capa invisible de clics.
  La ruta, los pines, las celdas bloqueadas y las misiones siguen en SVG/DOM. Un `<canvas>`
  capta el puntero en toda su superficie, así que la capa de clics (pane 452) queda por
  debajo de topónimos, ruta, pines y misiones. Donde no hay un marcador encima, el canvas
  encuentra la celda por geometría o pasa el clic al mapa (malla global).
- El índice de apantallamiento es `1 − radiation_modeled`, calculado en la interfaz solo para
  pintarlo. Su escala es relativa al rango real de la región.
- Con `?perf=1`, la interfaz mide la construcción del mapa (`window.__marsPerf`).

## Límites científicos y geométricos

- MOLA aporta topografía relativa al areoide, no una capa de peligros. El
  `risk` de MOLA es un proxy topográfico educativo: `min(slope_deg / 20, 1)`.
  Se publica en las celdas globales y de detalle y tiene peso 2.0 en A*; no es
  una probabilidad ni estima peligros geológicos o seguridad. Las celdas MOLA
  inválidas están bloqueadas y su proxy no está disponible.
- El umbral de pendiente de 30° por defecto es una regla demostrativa
  configurable, no un límite de tránsito validado para una misión.
- El cálculo de pendiente usa el radio marciano declarado por el producto y
  corrige la escala este-oeste por latitud. A* conserva el `cell_size_m`
  escalar original; la distancia reportada usa el tamaño nominal en el ecuador
  y es aproximada fuera de él.
- En modo MOLA, Leaflet representa latitud/longitud en una cuadrícula
  equirectangular, con longitudes positivas este de 0° a 360°. La vista
  planetaria es una imagen derivada del producto MOLA, muestreada a 0,5° por
  píxel; una malla independiente de 1° permite seleccionar y calcular rutas
  aproximadas en todo el planeta. El botón «Marte completo» muestra el globo
  y «Ir a zona MOLA» acerca al recorte de mayor detalle.
- El mapa base Viking MDIM 2.1 tiene resolución nominal de 232 m/píxel en el
  ecuador; no equivale a imágenes orbitales actuales de alta resolución.
  Se carga bajo demanda y requiere Internet. El modo sintético conserva su
  cuadrícula local.
- Los topónimos se consultan por extensión visible desde `combinedNom` de
  NASA/JPL Mars Trek. El filtro por diámetro cambia progresivamente con el zoom
  (1.000, 500, 200 y 50 km; en zoom de detalle se admiten todos); para cada vista
  se priorizan los accidentes grandes y las etiquetas que no se solapan. Estos
  datos son nomenclatura, no constituyen una capa de peligros.
- Una ruta es el óptimo del modelo de costo configurado; no garantiza
  seguridad, comunicación, energía ni transitabilidad de rover/persona.

## Pruebas y contratos

Las pruebas de lector construyen rasters PDS4/ENVI pequeños en temporales. Las
pruebas API verifican el formato legado, rutas geográficas globales y selección
del detalle en una región activa. Además, `test_mola_default_region.py` comprueba
la región predeterminada (relieve, bloqueos y rutas que los esquivan).
`tests/integration_check.py` valida contra servidores reales el modo sintético, MOLA
(`--mola`) y Gale (`--gale`: procedencia, capa de radiación y `/routes/shelter`).

La interfaz se prueba con jsdom (`cd frontend && npm test`). Las pruebas cargan
`index.html`, Leaflet y los scripts reales con un `fetch` falso y un contexto 2D falso:
- cuerpos de las solicitudes;
- etiquetas, pesos, capas y casillas;
- alerta solar y vocabulario;
- clics y hover por coordenadas sobre el canvas.

jsdom no pinta; el pintado real se revisa con la lista de comprobación manual del README.

- **Datos y API:** `docs/CONTRATO_DE_DATOS.md`
- **Procedencia:** `docs/FUENTES_DE_DATOS.md`
- **Documentación automática FastAPI:** `/docs`

## Alineación con el reto

La arquitectura permite combinar gradualmente capas de misiones distintas.
MOLA es la primera capa topográfica integrada; otras misiones y cualquier
modelo de riesgo requieren fuentes, metadatos y validación independientes.
