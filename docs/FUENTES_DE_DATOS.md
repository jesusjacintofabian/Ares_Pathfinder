# Fuentes de datos

> Documenta aquí procedencia, formato, condiciones de uso y atribución de cada
> conjunto científico. No confundas el DEM MOLA con capas de peligros.

## Conjunto integrado: MOLA MEGDR topography (`megt90n000eb`)

| Capa | Misión / instrumento | Fuente oficial | Formato y resolución | Unidades / referencia | Atribución |
|---|---|---|---|---|---|
| Elevación topográfica global | Mars Global Surveyor / MOLA | [PDS Geosciences Node, colección meg016](https://pds-geosciences.wustl.edu/mgs/urn-nasa-pds-mgs_mola_topography_derived/meg016/) · [label PDS4 del producto](https://pds-geosciences.wustl.edu/mgs/urn-nasa-pds-mgs_mola_topography_derived/meg016/megt90n000eb.xml) | `Array_2D_Image`, 2880 líneas × 5760 muestras, `SignedMSB2`; 1/16° × 1/16°. Escala lineal nominal en el ecuador: 3.7044613374 km/píxel | Elevación en metros respecto al areoide; latitud planetocéntrica; longitud positiva este; proyección equirectangular (radio esférico 3396 km, meridiano central 180°) | Smith et al., *Mars Global Surveyor Laser Altimeter Mission Experiment Gridded Data Record*, PDS, 2003, DOI [10.17189/1519460](https://doi.org/10.17189/1519460). |

El bundle MGS MOLA Topography Derived es archivado por el Geosciences Node del
NASA Planetary Data System (PDS). El `megt90n000eb.img` local mide 33.177.600
bytes; su MD5 es `357c759ab342140d2d008443e0a68015`, igual al listado publicado
en el manifiesto MD5 oficial del bundle. El producto PDS4 tiene logical
identifier `urn:nasa:pds:mgs_mola_topography_derived:data_meg016:megt90n000eb`.

### Archivos y lectura

Para este producto se requieren el raster `.img` y su label `.xml`. El `.hdr`
ENVI complementario declara `data ignore value = 0`; el lector aplica ese valor
como inválido cuando el header está disponible. El label PDS4 no declara un
valor nulo propio. Los valores restantes se interpretan como enteros con signo
de 16 bits en orden big-endian, convertidos a metros. La etiqueta declara la
forma y tipo del arreglo; el lector rechaza dimensiones, tipos, unidades o
tamaños binarios que no coincidan, y no supone que todo producto MOLA use el
mismo formato.

El PDS describe el pixel como la mediana de la topografía observada en su celda;
cuando no hay observaciones, se provee un valor interpolado. El dataset también
advierte menor densidad de observaciones cerca del ecuador y huecos entre
perfiles. No trates la elevación interpolada como una medición directa.

La fuente actual no proporciona una capa validada de peligro, transitabilidad
o seguridad. Para que las rutas y el mapa puedan considerar el relieve, el
laboratorio calcula un **proxy topográfico educativo** por celda válida:
`risk = min(slope_deg / 20, 1)`. El valor 0 corresponde a pendiente plana y 1 a
pendiente de 20° o más; los valores intermedios son una escala normalizada, no
probabilidades ni niveles calibrados de peligro. A* aplica a este proxy un peso
de 2.0. El método es igual para MOLA de detalle y global, aunque esta última
usa como pendiente el máximo observado entre los píxeles nativos de cada celda
de 1°. Celdas sin datos válidos se bloquean; su cero de compatibilidad no es
un proxy válido. Ninguno de estos valores modela geología, rocas, polvo,
iluminación, energía, comunicaciones o condiciones de misión.

El mapa identifica explícitamente el indicador como «proxy de riesgo
topográfico». **No es un modelo de peligro real ni una evaluación de seguridad
o transitabilidad.** El umbral de pendiente usado adicionalmente para bloquear
celdas es una regla configurable y demostrativa.

### Descarga y atribución

Usa el [directorio oficial de la colección meg016](https://pds-geosciences.wustl.edu/mgs/urn-nasa-pds-mgs_mola_topography_derived/meg016/)
y descarga conjuntamente `megt90n000eb.img`, `megt90n000eb.xml` y
`megt90n000eb.hdr` en `data/raw/mola/`. El [README del bundle PDS](https://pds-geosciences.wustl.edu/mgs/urn-nasa-pds-mgs_mola_topography_derived/readme.txt)
identifica la fuente como datos derivados de MOLA archivados por el PDS
Geosciences Node. La [documentación ENVI de PDS](https://pds-geosciences.wustl.edu/mgs/urn-nasa-pds-mgs_mola_topography_derived/document/mola_envi.htm)
describe la resolución precisa del mapa.

No se encontró una licencia separada en el label del producto o en el README
del bundle consultados. Por tanto, conserva los metadatos PDS, cita el producto
y sigue las condiciones indicadas por el PDS/NASA; no se atribuye aquí una
licencia adicional. El archivo local no registra una fecha verificable de
descarga. La fecha del archivo en el sistema local no se considera fecha de
adquisición.

## Regiones procesadas (derivadas de `megt90n000eb`)

Cada región es un recorte de la misma fuente, procesado con `data/process_mola.py`. El recorte conserva la
elevación original (redondeada) y añade una pendiente **derivada** y un bloqueo **demostrativo** por umbral.
Las estadísticas se calcularon directamente de los JSON versionados.

| Archivo | Límites (lat. planetocéntrica / lon. este) | Celdas | Elevación (m) | Pendiente máx. | Umbral | Bloqueadas | Inválidas |
|---|---|---|---|---|---|---|---|
| `mola_valles_marineris.json` | −14° a −12° / 291° a 293° | 32 × 32 | −4887 a 4441 | 32.16° | 20° | 96 | 1 |
| `mola_region.json` | −1° a 1° / 179° a 181° | 32 × 32 | −2839 a −2273 | 2.53° | 30° | 0 | 0 |

Comando usado para la región predeterminada:

```bash
python data/process_mola.py --bounds -14 -12 291 293 --max-slope-deg 20 \
  --output data/processed/mola_valles_marineris.json
```

Los escarpes de Valles Marineris separan la región en **cuatro zonas libres desconectadas** (698, 228, 1 y 1 celdas,
verificado con un recorrido independiente de A*). Elegir origen y destino en zonas distintas produce `404 NO_ROUTE`,
que es un resultado correcto del modelo y no un error.

Se eligió Valles Marineris por su relieve fuerte (cañones y escarpes) para que A* tenga obstáculos reales. Los
umbrales de bloqueo no son límites de tránsito validados. Cada celda trae `latitude` y `longitude` de su centro.

## DEM MOLA+HRSC de 200 m (región Gale)

| Campo | Valor |
|---|---|
| Producto | Mars MGS MOLA - MEX HRSC Blended DEM Global 200m v2 (USGS Astrogeology) |
| Página | https://astrogeology.usgs.gov/search/map/mars_mgs_mola_mex_hrsc_blended_dem_global_200m |
| Archivo | https://planetarymaps.usgs.gov/mosaic/Mars/HRSC_MOLA_Blend/Mars_HRSC_MOLA_BlendDEM_Global_200mp_v2.tif (redirige a `asc-pds-services.s3.us-west-2.amazonaws.com`) |
| Cita | Fergason, Hare y Laura (2018) |
| Licencias | MOLA: CC0; HRSC: CC BY-SA 3.0 IGO |
| Consulta | 2026-11-14 |

**Metadatos comprobados** (cabeceras HTTP y etiquetas TIFF leídas por rangos, sin descargar el archivo):
11 384 463 908 bytes, `Last-Modified: Wed, 09 Nov 2022 14:59:19 GMT`, `Accept-Ranges: bytes`;
BigTIFF little-endian de 106 694 × 53 347 píxeles, int16 con signo, sin compresión, una fila por strip,
sin overviews, `GDAL_NODATA = -32768`. Georreferencia geográfica en grados: punto de enlace (−180°, 90°),
píxel de 0,003374120830641° sobre la esfera `GCS_Mars_2000_Sphere` de radio 3 396 190 m (≈ 200 m).
El ancho total cubre 359,998°, así que la malla no está alineada con 0°E. El radio difiere del de MOLA
MEGDR (3 396 000 m); cada lector usa el que declara su archivo.

**No comprobado:** el archivo no trae una etiqueta GDAL_METADATA. La referencia vertical de la elevación
no se ha confirmado en los metadatos leídos; el contraste con MOLA (abajo) indica que son coherentes.

### Procesamiento (`data/process_dem.py`)

El DEM global no se descarga. `data/geotiff_reader.py` lee por rangos HTTP solo el tramo de columnas de
cada fila de la ventana y guarda un recorte crudo de 200 m en `data/raw/gale/`, ignorado por Git, para
reprocesar sin red. Desde F3 se lee además un margen de 10 km alrededor de la ventana para buscar el
horizonte (340 × 310 píxeles, ~217 KB en `gale_clip_200m_margen10km.tif`; el recorte anterior de 1 píxel
de margen, `gale_clip_200m.tif`, ya no basta para la capa de radiación). La pendiente se calcula
a 200 m con 1 píxel de margen y después se agrupan bloques de 3 × 3 píxeles: elevación media, pendiente
**máxima** del bloque, y celda válida solo si sus 9 píxeles lo son.

```bash
python data/process_dem.py \
  --dem https://planetarymaps.usgs.gov/mosaic/Mars/HRSC_MOLA_Blend/Mars_HRSC_MOLA_BlendDEM_Global_200mp_v2.tif \
  --bounds -5.3 -4.5 137.3 138.0 --aggregate 3 \
  --name "Gale — flanco noroeste del Monte Sharp (DEM MOLA+HRSC)" \
  --save-raw data/raw/gale/gale_clip_200m_margen10km.tif \
  --output data/processed/gale_monte_sharp_600m.json
```

`--horizon-radius-km` (10 por defecto; 0 desactiva la capa) y `--azimuths` (32) controlan la capa de
radiación MODELADA descrita más abajo. La versión versionada se regeneró el 2026-11-14 con ese comando; el
reprocesado sin red desde el recorte crudo da celdas idénticas.

| Archivo | Límites reales (lat. / lon. este) | Celdas | Elevación (m) | Pendiente máx. | Umbral | Bloqueadas | Inválidas |
|---|---|---|---|---|---|---|---|
| `gale_monte_sharp_600m.json` | −5.3088° a −4.4990° / 137.2989° a 138.0075° | 80 × 70 (600 m) | −4545 a 485 | 34.93° | 30° | 15 | 0 |

La ventana pedida (−5,3 a −4,5 / 137,3 a 138,0) es **provisional**: las coordenadas del *boxwork* no están
verificadas. La ventana real se amplía hasta el borde de píxel y hasta un múltiplo del factor de
agregación. Todas las celdas libres forman una sola zona conectada (5585 celdas). El umbral de 30° es
demostrativo, no el límite de un traje; además, a 200 m aparecen pendientes mayores que a la escala de MOLA.

El 6,59 % de las celdas (369 de 5600) tiene `risk = 1` (pendiente de 20° o más). Sensibilidad al umbral
de bloqueo, solo informativa (el valor por defecto sigue en 30°). La conectividad usa la regla de A*:
las diagonales no cortan esquinas.

| Umbral | Bloqueadas | Zonas libres | Zona mayor (% de las libres) |
|---|---|---|---|
| 15° | 1330 (23,75 %) | 26 | 4213 (98,67 %) |
| 20° | 369 (6,59 %) | 7 | 5221 (99,81 %) |
| 25° | 92 (1,64 %) | 1 | 5508 (100 %) |
| 30° | 15 (0,27 %) | 1 | 5585 (100 %) |

**Contraste independiente con MOLA MEGDR** (`megt90n000eb`): en 132 píxeles MOLA de 1/16° dentro de la
ventana, la media de las celdas de Gale difiere en +7 m (desviación típica de 122 m), con una correlación
de 0,9967. En el punto de aterrizaje de Curiosity (4,59°S, 137,44°E), el DEM da −4510 m y MOLA −4509 m.

## Radiación MODELADA (región Gale)

| Campo | Valor |
|---|---|
| Etiqueta | **MODELADO**: no es una medición celda por celda ni una dosis |
| Campos por celda | `sky_view_factor` y `radiation_modeled` (0–1, adimensionales; en esta versión son iguales) |
| Metadatos | `radiation_model` y `radiation_available` en el JSON y en `GET /api/v1/map` |
| Código | `data/sky_view.py` (horizonte y cielo visible), `data/radiation_model.py` (supuestos, límites y ancla) |
| Peso en A* | `radiation_weight = 0.0` por defecto; desde F6 se puede ajustar por solicitud (0–100) en `POST /routes` y `POST /routes/shelter` |

**Ancla medida.** Hassler et al. (2014), *Mars' Surface Radiation Environment Measured with the Mars
Science Laboratory's Curiosity Rover*, Science 343 (6169), 1244797, DOI
[10.1126/science.1244797](https://doi.org/10.1126/science.1244797). Según el resumen publicado, el
instrumento RAD del rover Curiosity midió en la superficie de Gale la dosis absorbida y la dosis
equivalente debidas a rayos cósmicos galácticos (GCR) y a partículas energéticas solares (SEP) durante
unos 300 días. Esa medición es el punto ancla: corresponde al lugar del rover, y el índice solo describe
cómo varía, de forma relativa, la exposición al cielo entre celdas.

**Cifras no cotejadas.** El encargo cita 180 a 225 µGy/día, una media de 0,21 mGy/día y un pico cercano a
260 µGy/día durante un evento solar. El resumen publicado no contiene esas cifras y no se pudo leer el
artículo completo (la copia de core.ac.uk respondió 403). Se conservan como metadato con
`verification_status: "no cotejado con el artículo publicado"` y `used_in_calculation: false`; no se
usan en ningún cálculo ni se publican como dosis por celda.

**Método (hipótesis del autor).** Para cada píxel de 200 m se busca el ángulo de horizonte H en 32
acimuts hasta 10 km, con muestreo al píxel más cercano, distancias métricas (el píxel este-oeste se
reduce con cos(latitud)) y corrección por curvatura d²/2R con el radio que declara el GeoTIFF. Los píxeles
sin dato no tapan el cielo. El factor de cielo visible es la fracción de ángulo sólido no tapada con cielo
isótropo: `media_acimut(1 − sin(max(H, 0)))`. Un plano abierto da 1; un pozo da menos. La celda de 600 m
toma la media de sus 3 × 3 píxeles. Índice: `radiation_modeled = sky_view_factor`.

**Supuestos.** Radiación isótropa en el cielo visible; el relieve bloquea por completo las direcciones que
tapa; más cielo visible implica más exposición relativa.

**Límites.**
- No modela la atenuación atmosférica con el ángulo cenital. La radiación que llega en ángulo bajo ya
  está muy atenuada, así que el índice **exagera** el blindaje del relieve.
- No modela la radiación secundaria del terreno (neutrones de albedo) ni la variación temporal (ciclo
  diurno de presión, ciclo solar, eventos SEP).
- No modela la columna atmosférica según la elevación. En la ventana hay unos 5 km de desnivel y es
  probablemente el factor espacial dominante; no se añadió porque no hay un coeficiente verificado.
- La resolución (200 m, celdas de 600 m) no capta el relieve del *boxwork* (crestas de 1 a 2 m).
- Más allá de 10 km no se busca horizonte: el borde lejano del cráter puede tapar algo más de cielo.

**Resultado en `gale_monte_sharp_600m.json`** (calculado sobre el JSON versionado): 5600 celdas, 0 con el
horizonte truncado. `sky_view_factor` va de 0,7404 a 0,9957 (mediana 0,9227, media 0,9209, p5 0,8540,
p95 0,9794); 1638 celdas (29,25 %) quedan por debajo de 0,9 y 14 (0,25 %) por debajo de 0,8. La celda
del punto de aterrizaje de Curiosity (4,59°S, 137,44°E) da 0,9556. Ninguna celda llega a 1, porque desde
todas se ve algo de relieve por encima de la horizontal (el Monte Sharp domina la ventana).

**Observación.** La correlación de Pearson entre `sky_view_factor` y la pendiente de la celda es −0,90; con
la elevación, −0,10. En una ladera, la propia cuesta tapa el cielo hacia arriba, así que el índice repite
en gran parte la información de la pendiente, que ya entra en el costo. Conviene tenerlo en cuenta al
elegir `radiation_weight` en F6.

### Procedencia: `sky_view_factor` DERIVADO, capa de radiación MODELADO

En el campo `provenance` de `GET /api/v1/map`, `sky_view_factor` se etiqueta **DERIVADO** y
`radiation_modeled` **MODELADO**, aunque en esta versión los dos valores sean iguales:

- `sky_view_factor` es **geometría** calculada solo desde el DEM (ángulo de horizonte en 32 acimuts,
  corrección de curvatura). Lo único que afirma es qué fracción del cielo tapa el relieve. No hace
  ninguna suposición sobre la radiación, igual que la pendiente.
- `radiation_modeled` (la capa de F3) toma ese número y le añade **hipótesis físicas** para leerlo como
  exposición: cielo isótropo, bloqueo total por el relieve y la idea de que más cielo implica más
  exposición. Esas hipótesis son las que la convierten en un modelo, con los límites listados arriba.

Por eso la misma cifra lleva etiquetas distintas según para qué se usa: `sky_view_factor` como dato
del terreno (para elegir zonas candidatas de espera) y `radiation_modeled` como índice de exposición
(en el costo, con peso 0 por defecto).

## Zona candidata de espera (modo «alerta solar», región Gale)

| Campo | Valor |
|---|---|
| Etiqueta | **ÍNDICE DEL PROYECTO**: criterio del laboratorio, no un producto de NASA ni una protección verificada |
| Endpoint | `POST /api/v1/routes/shelter` (ver `docs/CONTRATO_DE_DATOS.md`) |
| Código | `backend/app/services/shelter_service.py`, `algorithms/astar.py` (`find_nearest_target`) |
| Criterio por defecto | celda válida y libre con `slope_deg ≤ 10` y `sky_view_factor ≤ 0,90`; ambos umbrales se pueden cambiar por solicitud |
| Límite de distancia | `max_distance_km` opcional, sin valor por defecto: la zona se acepta si su ruta de menor costo mide como mucho ese valor; si ninguna queda dentro, `404 NO_SHELTER`. La respuesta trae siempre `distance_km` |

**Método.** Dijkstra desde el origen; se detiene en la primera celda que cumple el criterio. Así se elige
la zona más cercana **por costo** (con la misma fórmula y los mismos pesos que `/routes`), no por
distancia. `sky_view_factor` solo decide qué celdas son candidatas; **no penaliza el costo**, porque su
correlación con la pendiente es −0,90 y la pendiente ya entra al costo (sería un doble castigo).

**Justificación de los umbrales** (calculada sobre las 5585 celdas libres de `gale_monte_sharp_600m.json`):

- **10°** es la mediana de pendiente de las celdas libres (10,05°): la zona candidata queda en la mitad
  más llana y su proxy de riesgo topográfico es ≤ 0,5. La pendiente es el máximo del bloque de 3 × 3
  píxeles de 200 m.
- **0,90** es aproximadamente el percentil 25 de `sky_view_factor` en las celdas libres (0,895).

| Criterio | Candidatas | Grupos separados (8 vecinos) | `sky_view_factor` medio |
|---|---|---|---|
| pendiente ≤ 10° y SVF ≤ 0,85 | 0 | – | – |
| pendiente ≤ 10° y SVF ≤ 0,88 | 6 | – | – |
| **pendiente ≤ 10° y SVF ≤ 0,90** (por defecto) | **64** | 20 | 0,890 |
| pendiente ≤ 12° y SVF ≤ 0,90 | 131 | 40 | 0,890 |

Por la correlación −0,90, las celdas con poco cielo visible casi siempre están en ladera: umbrales más
estrictos dejan la región sin candidatas.

**Ejemplo ejecutado** (pesos por defecto): desde el punto de aterrizaje de Curiosity (4,59°S, 137,44°E;
celda 8, 13) la zona candidata más cercana por costo es la celda (11, 42), a 29 pasos y ~18,1 km
(`total_cost` 53,69), con pendiente 9,84° y `sky_view_factor` 0,893.

**Límites (decirlos siempre).**
- La reducción de cielo visible modelada es pequeña: una zona candidata media ve 0,89 frente a la
  mediana de 0,92 (≈ 3 % menos). Además el índice no incluye la atenuación atmosférica y **exagera** el
  blindaje del relieve, así que el beneficio real puede ser menor.
- A 600 m por celda no se representan resaltes, cornisas ni el relieve del *boxwork*, que a escala de
  una persona podrían dar más sombra que la que se ve aquí.
- La distancia a la zona candidata (18 km en el ejemplo) puede ser mayor que la que permite una
  caminata; `max_distance_km` permite acotarla, pero el modo no considera tiempo, consumibles ni
  duración de un evento solar.
- Es una ayuda de planificación educativa: no es un refugio verificado ni una recomendación operacional.

## Mosaico visual global: Viking MDIM 2.1

La interfaz puede mostrar opcionalmente como mapa base el producto **Mars Viking MDIM 2.1
Color Mosaic**, publicado por NASA/JPL Mars Trek como servicio ArcGIS ImageServer
`Mars_Viking_MDIM21_ClrMosaic_global_232m`. El catálogo de mapas base de Mars
Trek lo identifica como su mosaico global equirectangular; el servicio informa
extensión global `0..360°` de longitud, `-90..90°` de latitud, tres bandas RGB y
muestreo de `0.00390625°` por píxel (232 m nominales en el ecuador).

- [NASA Mars Trek](https://trek.nasa.gov/mars/)
- [Catálogo de mapas base](https://trek.nasa.gov/mars/jpl/config/basemapList.json)
- [Metadatos y servicio de imágenes](https://trek.nasa.gov/mars/trekarcgis/rest/services/Mars_Viking_MDIM21_ClrMosaic_global_232m/ImageServer?f=pjson)

El frontend solicita teselas al servicio de imágenes solo cuando el usuario
activa esta capa; requiere conexión a Internet. Es un mosaico orbital global de
imágenes Viking, no imágenes actuales de alta resolución. Solo funciona como
capa visual y no altera los datos de las rutas. Consérvese la atribución NASA/JPL Mars Trek
mostrada en la interfaz; no se documenta aquí una licencia adicional no
verificada.

## Vista topográfica MOLA global del frontend

Para dar contexto del planeta completo sin devolver los 16.588.800 píxeles
nativos por la API, `data/render_mola_preview.py` genera
`frontend/assets/mola-global.png` directamente desde el raster MEGDR. Cada
píxel de la imagen representa el promedio de los datos válidos dentro de un
bloque de 8 × 8 píxeles nativos (0,5° por píxel); los valores declarados como
inválidos por el header ENVI se excluyen del promedio y quedan transparentes.
La paleta hipsométrica es una decisión visual del laboratorio, no una
clasificación de peligros.

La imagen cubre 0–360° de longitud este y −90° a 90° de latitud, y se sirve
localmente desde el frontend: no requiere una consulta de teselas ni conexión
externa. Para regenerarla (requiere el raster `.img` local y NumPy):

```bash
python3 data/render_mola_preview.py
```

La vista global es una representación de contexto de menor resolución; no se
usa para seleccionar celdas, calcular pendientes ni planificar rutas. La
procedencia del relieve sigue siendo el producto `megt90n000eb` archivado por
NASA PDS; la imagen no es un producto oficial de NASA.

## Malla MOLA global para rutas (1°)

`data/process_mola_global.py` genera `data/processed/mola_global_1deg.json.gz`
(180 × 360 celdas), `frontend/assets/mola-global-blocked.png` y
`frontend/assets/mola-global-risk.png`. La elevación de
cada celda es el promedio de los píxeles MOLA válidos de ese bloque de 1°.
Para no ocultar escarpes mediante el promedio, la pendiente asignada a la celda
es la máxima pendiente calculada sobre los píxeles nativos del bloque. El
procesador calcula el proxy normalizado `min(slope_deg / 20, 1)`, marca
inválidas/bloqueadas las celdas sin pendiente calculable y bloquea las que
alcanzan el umbral demostrativo de 20°.

La resolución angular corresponde aproximadamente a 59 km norte-sur y, en el
ecuador, 59 km este-oeste; la dimensión este-oeste se reduce con la latitud.
Esta cuadrícula permite explorar y calcular rutas aproximadas fuera de la
región MOLA de detalle. Si uno o ambos puntos quedan fuera del recorte local,
el backend planifica sobre esta malla; si ambos están dentro, usa el recorte
detallado. La máscara PNG representa las celdas bloqueadas; `mola-global-risk.png`
representa con una rampa verde-amarillo-rojo el proxy de pendiente. Esas
imágenes no son capas científicas de peligro ni de seguridad.

El `.json.gz` comprimido y la máscara se versionan para que la API pueda operar
sin tener el raster de 33 MB. Para regenerarlos se requiere el raster original
en `data/raw/mola/` y NumPy:

```bash
python3 -m data.process_mola_global
```

El generador no reemplaza archivos existentes. La fuente sigue siendo MOLA
MEGDR y la agregación, el umbral de pendiente y el enrutamiento son decisiones
demostrativas del laboratorio, no productos oficiales de NASA ni validaciones
de tránsito.

## Nomenclatura de accidentes geográficos marcianos

Los nombres y tipos de volcanes, cráteres y otros accidentes se consultan desde
la capa oficial `combinedNom/MapServer/0` de NASA/JPL Mars Trek. La respuesta
incluye el tipo del accidente y, cuando existe, su diámetro publicado. La
interfaz consulta por el área visible. Para reducir el apiñamiento, el umbral
de diámetro desciende al acercar el mapa (≥1.000, 500, 200 y 50 km; en zoom de
detalle se consultan todos), y las etiquetas permanentes evitan solaparse
priorizando accidentes grandes. Las etiquetas pueden consultarse al pasar el
cursor sobre los marcadores restantes. Esta capa es nomenclatura, no una
evaluación de peligros o transitabilidad.

- [Metadatos de la capa](https://trek.nasa.gov/mars/trekarcgis/rest/services/combinedNom/MapServer/0?f=pjson)
- [Servicio de consulta de accidentes](https://trek.nasa.gov/mars/trekarcgis/rest/services/combinedNom/MapServer/0/query)

## Otros productos por investigar

HiRISE, CTX, THEMIS y CRISM son candidatos para capas adicionales. Su
disponibilidad para una región, formatos y condiciones de uso deben verificarse
en fuentes oficiales antes de incorporarlos.


## Galería de imágenes de misiones marcianas

El frontend incorpora una galería que consulta el endpoint público de búsqueda de NASA Image and Video Library:

- Endpoint: `https://images-api.nasa.gov/search`
- Parámetros: `q`, `media_type=image` y `page_size=12`.
- Búsquedas disponibles: Perseverance, HiRISE (Mars Reconnaissance Orbiter), THEMIS (Mars Odyssey), CTX (Mars Reconnaissance Orbiter) y HRSC (Mars Express).
- El usuario puede abrir cada vista previa en una pestaña nueva. El catálogo aporta título, fecha y recurso de imagen; la galería no descarga ni almacena los originales.

Esta integración aporta fotografías de misiones reales para exploración visual. No debe confundirse con una capa cartográfica georreferenciada ni con un DEM: las fotografías no se superponen automáticamente sobre el mapa Leaflet y no intervienen en A*. La relevancia exacta de cada resultado depende de la búsqueda del catálogo; revisa el título y los metadatos antes de usar una imagen como evidencia de una ubicación concreta.

Fuentes oficiales:

- [NASA Image and Video Library](https://images.nasa.gov/)
- [NASA Open APIs](https://api.nasa.gov/)
- [THEMIS / ASU: mapas de imágenes de Marte](https://themis.mars.asu.edu/maps)
- [NASA Mars Trek](https://trek.nasa.gov/mars/)
