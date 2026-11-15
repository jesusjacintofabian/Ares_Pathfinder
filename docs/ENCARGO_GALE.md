# Encargo: mapa de misión de exploración en Gale (Monte Sharp)

> Archivo de contexto para quien implemente (Claude Code en VS Code u otra herramienta).
> Contiene las decisiones ya tomadas, las fuentes verificadas y lo que **todavía no está verificado**.
> No inventes datos, enlaces ni resultados: si algo no está aquí o no lo puedes comprobar, dilo.

## 1. Contexto del proyecto existente
Mars Explorer Lab: API FastAPI + algoritmo A* + frontend Leaflet. Modos de datos `synthetic` y `mola`
(`MARS_DATA_SOURCE`). Contrato en `docs/CONTRATO_DE_DATOS.md` (API v1). Lee también `README.md`,
`docs/ARQUITECTURA.md` y `docs/FUENTES_DE_DATOS.md` antes de empezar.

Reglas que ya rigen el proyecto:
- Los datos simulados se identifican como tales; ninguna ruta se presenta como «segura».
- No subir archivos grandes ni credenciales. `main` exige Pull Request: trabaja en una rama.
- Pytest antes de cada commit; commits pequeños `tipo(ámbito): descripción`.

## 2. Problema definido
Un astronauta en caminata sobre la superficie de Marte debe llegar a un objetivo científico valioso y
regresar al hábitat sin exponerse a pendientes que su traje no permite, a terreno blando ni a radiación
evitable, y necesita poder cambiar de plan si el clima espacial empeora durante la salida.

Criterios de la hackatón (NASA Space Apps 2026, «Interplanetary Survival Guide: Martian Map»):
Impacto, Creatividad, Validez, Relevancia, Presentación (1 a 5). Se piden al menos 3 tipos de datos
combinados. Prioridad: seguridad del astronauta.

## 3. Decisiones tomadas
- **Región:** cráter Gale, flanco noroeste del Monte Sharp (Aeolis Mons). Objetivo científico: formaciones
  *boxwork* (crestas de 1 a 2 m con hondonadas arenosas, en una capa rica en sulfatos).
- **Ventana provisional** (por confirmar): `--bounds -5.3 -4.5 137.3 138.0` (≈ 47 × 41 km; ≈ 237 × 206 celdas de 200 m).
  Aterrizaje de Curiosity: 4.59°S, 137.44°E. Gale: 5.4°S, 137.8°E. Las coordenadas del *boxwork* **no están verificadas**.
- **Opción A** para el terreno blando: Mars Trek se usa como **contexto visual**; el costo de A* sale de datos
  numéricos. El indicador de terreno blando entra con peso 0 por defecto.
- **Recursos del reto usados (3 de 5):** Mars Trek (JPL), mapa geológico USGS y ruta propuesta de Curiosity.
  No se usan: NASA Worldview (es de la Tierra) ni las imágenes de Perseverance (Jezero, no Gale).

### Etiquetas obligatorias por capa (visibles en la interfaz y en la API)
| Capa | Etiqueta | Origen | ¿Entra al costo? |
|---|---|---|---|
| Elevación | MEDIDO | DEM MOLA+HRSC 200 m (USGS) | Sí |
| Pendiente | DERIVADO | Calculada desde la elevación | Sí |
| Terreno blando | INDICADOR | THEMIS (mosaico cualitativo) / TES | Sí, peso bajo y ajustable (0 por defecto) |
| Radiación | MODELADO | Ancla medida por RAD (Curiosity) + modelo | Sí, como modelo declarado |
| Unidades geológicas | INTERPRETADO | Mapa USGS (Tanaka et al., 2014) | No (contexto) |
| Ruta de Curiosity | REFERENCIA | Animación de NASA | No (comparación) |
| Costo total | ÍNDICE DEL PROYECTO | Combinación de las anteriores | Es el resultado |

El costo total es una puntuación de planificación con pesos ajustables: no es una probabilidad ni una
garantía de seguridad.

### Fórmula de costo
```
costo_paso = longitud × (1 + w_pendiente·pendiente + w_blando·indicador_blando + w_radiación·radiación_modelada)
```
Todos los pesos ≥ 0 (así la heurística de A* sigue siendo admisible). Documenta los pesos por defecto.

## 4. Fases
| Fase | Tarea | Criterio de aceptación |
|---|---|---|
| **F1** | `data/process_dem.py`: recorta una ventana del DEM (GeoTIFF), calcula pendiente y genera un JSON de celdas con el formato de `mola_valles_marineris.json`. Región integrada en el backend como una fuente más | Pruebas con rasters GeoTIFF diminutos generados en las pruebas; las pruebas existentes siguen pasando |
| **F2** | Capas visuales de Mars Trek (WMTS) y mosaico cualitativo THEMIS del USGS (peso 0 en el costo) | Capas activables; etiquetadas INDICADOR |
| **F3** | Radiación modelada: tasa medida por RAD como ancla + cuánto cielo ve cada celda (calculable desde el DEM) | Etiquetada MODELADO; documentar supuestos |
| **F4** | Capa de unidades geológicas del USGS (FeatureServer) | Etiquetada INTERPRETADO; avisar de la escala gruesa |
| **F5** | Ruta de Curiosity georreferenciada a mano desde el GIF | Etiquetada REFERENCIA y marcada como aproximada |
| **F6** | Costos de A* con pesos ajustables, modo «alerta solar» (ruta al refugio más cercano) y campo `provenance` por capa en la API | Campos nuevos opcionales; no romper el contrato v1 |
| **F7** | Pruebas, integración (`tests/integration_check.py`) y actualización de la guía técnica | Todo documentado, nada afirmado sin ejecutarlo |

Empieza solo por **F1** y detente para revisión.

## 5. Fuentes verificadas
- **DEM MOLA+HRSC 200 m (global, GeoTIFF ≈ 11 GB):**
  https://astrogeology.usgs.gov/search/map/mars_mgs_mola_mex_hrsc_blended_dem_global_200m
  Archivo: https://planetarymaps.usgs.gov/mosaic/Mars/HRSC_MOLA_Blend/Mars_HRSC_MOLA_BlendDEM_Global_200mp_v2.tif
  Licencias: MOLA CC0 y HRSC CC BY-SA 3.0 IGO. Citar: Fergason, Hare y Laura (2018).
- **Mars Trek, servicios WMTS:** https://trek.nasa.gov/tiles/apidoc/trekAPI.html?body=mars
  (imágenes en teselas; si falta una tesela, no hay cobertura).
- **Mapa geológico de Marte (Tanaka et al., 2014, escala 1:20 000 000, dominio público):**
  https://services.arcgis.com/nzS0F0zdNLvs7nc8/ArcGIS/rest/services/Mars_Geology_feature_layer/FeatureServer
  Es muy grueso para una ventana de ~40 km.
- **Mosaico de inercia térmica THEMIS (cualitativo, 8 bits, ≈ 100 m, ±60° de latitud, dominio público):**
  https://astrogeology.usgs.gov/search/map/themis_thermal_inertia_mosaic_qualitative_30n300e_100_mpp
  (esa es una tesela de ejemplo; **la tesela que cubre Gale hay que identificarla**).
- **Inercia térmica TES numérica (20 píxeles/grado ≈ 3 km):** https://pds-geosciences.wustl.edu/missions/mgs/tes-timap.html
  Demasiado gruesa para decidir rutas; sirve de contexto regional.
- **Ruta propuesta de Curiosity (GIF 1041 × 586, créditos NASA/JPL-Caltech/ESA/UArizona/JHUAPL/MSSS/USGS):**
  https://science.nasa.gov/resource/curiositys-proposed-path-up-mount-sharp/
- **Radiación medida (RAD):** Hassler et al. (2014), Science 343 (6169), 1244797. Tasa de dosis medida en
  Gale: 180 a 225 microgray por día, con pico cercano a 260 durante un evento solar.

## 6. Lo que NO está verificado (no lo des por hecho)
- Las coordenadas del *boxwork* y la ventana definitiva.
- Si existe un mapa geológico local de Gale descargable con más detalle que el global.
- Si el servidor del USGS permite leer el DEM por ventanas (lectura remota) o hay que descargar los 11 GB.
- Si el mosaico THEMIS trae valores calibrados: se verificó que es **cualitativo/relativo**.
- Qué tesela del mosaico THEMIS cubre Gale y qué productos de THEMIS ofrece hoy Mars Trek.
- Cuánto cuesta adaptar `mola_reader.py` (lee PDS4/ENVI) al GeoTIFF, o si conviene una librería nueva
  (por ejemplo `rasterio`). **Avisa antes de añadir dependencias.**

## 7. Reglas para quien implemente
1. Rama nueva (`feature/gale-dem`); no hagas push a `main`.
2. No inventes datos ni URLs. Cita cada fuente en `docs/FUENTES_DE_DATOS.md`.
3. El DEM crudo va a `data/raw/` y debe quedar fuera de Git (`.gitignore`).
4. No cambies el contrato de la API existente: los campos nuevos son opcionales.
5. Antes de instalar una dependencia, di cuál y por qué.
6. Usa modo Manual o Plan: pide permiso antes de descargas grandes o comandos con efectos.
7. Nunca pegues tokens ni credenciales.

## 8. Qué informar al terminar cada fase
- Qué archivos cambiaste y por qué (`git diff main --stat`).
- Qué **ejecutaste** y qué resultado dio (copia la salida real de `pytest`).
- Qué **no** pudiste comprobar.
- Qué decisiones quedan abiertas para el usuario.
