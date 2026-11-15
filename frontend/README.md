# Frontend — Ares Pathfinder

Interfaz web con Leaflet para explorar una cuadrícula y pedir rutas al backend.
El cálculo A* lo hace el backend. El modo MOLA muestra un relieve global
colorizado, generado localmente desde el producto MOLA MEGDR y reducido a 0,5°
por píxel, junto con una máscara de bloqueos de la cuadrícula global de rutas.
El sombreado opcional de riesgo muestra un proxy topográfico basado únicamente
en pendiente (`min(pendiente / 20°, 1)`); el mismo indicador se aplica al detalle
y penaliza rutas MOLA. No es una probabilidad ni estima peligros geológicos o seguridad.
Se pueden seleccionar puntos en todo Marte: A* usa una malla MOLA aproximada
de 1° fuera de la región de detalle, y la cuadrícula local dentro de ella.

## Ejecutar
1. Inicia el backend desde `backend/`. Para el mosaico y la cuadrícula MOLA (región Valles Marineris por defecto; sin `MARS_DATA_SOURCE` se usa el modo sintético):
   ```bash
   MARS_DATA_SOURCE=mola \
   ../.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000
   ```
2. Desde `frontend/`: `python3 -m http.server 5500 --bind 127.0.0.1`
3. Abre http://127.0.0.1:5500

La URL de la API está en `js/config.js` (por defecto `http://127.0.0.1:8000`).
Leaflet 1.9.4 se incluye localmente en `vendor/leaflet/` (no requiere Internet).
En el mapa MOLA, «Marte completo» muestra el relieve planetario y «Ir a zona
MOLA» acerca al recorte de mayor detalle. La imagen global se genera con
`python3 data/render_mola_preview.py`; la malla de rutas de 1° se genera con
`python3 -m data.process_mola_global` y se sirve como datos compactos por la API;
también genera la visualización global del proxy de pendiente.
Si ambos puntos están dentro de la región local, se usa detalle; en caso contrario,
la ruta utiliza la malla global. «Imagen orbital Viking» y los topónimos NASA/JPL son capas
opcionales que requieren Internet. Los topónimos no son peligros; no hay una
capa global de peligros validada integrada en la aplicación. El proxy de riesgo
de MOLA usa pendiente, no observaciones de peligros.
Al activar los nombres de lugares, solo se muestran accidentes grandes con la
vista global; al acercar, se van incorporando accidentes menores. Las etiquetas
permanentes se separan para evitar solaparse y se priorizan las de mayor diámetro.


## Capas de trayectorias rover

En modo MOLA, el panel izquierdo permite activar/desactivar las trayectorias de
Perseverance, Curiosity, Opportunity, Spirit y Zhurong. Al seleccionar una de esas
misiones, el mapa centra su región y muestra la trayectoria de referencia, el lugar
de aterrizaje y puntos de interés con ventanas emergentes. La galería NASA se conserva
como complemento independiente y ambos paneles se mantienen plegados hasta que se
necesiten.

Los recorridos incluidos son aproximaciones didácticas y no telemetría oficial. Se
superponen al relieve MOLA global. La malla de 1° es aproximada (unos 59 km por
celda en el ecuador) y ni ella ni el detalle MOLA son herramientas de navegación
operacional o garantías de seguridad.


## Región Gale: procedencia, pesos y alerta solar

Con el backend en `MARS_DATA_SOURCE=mola MARS_MOLA_REGION=gale`, la interfaz usa solo lo que
la API ya publica (ver `docs/CONTRATO_DE_DATOS.md`):

- **Etiquetas de procedencia.** Junto a cada capa y al costo total aparece la etiqueta de
  `provenance` (MEDIDO, DERIVADO, MODELADO, ÍNDICE DEL PROYECTO). Al pasar el cursor o
  enfocarla se ven la fuente y si entra al costo. También salen en Valles Marineris, porque
  el backend publica `provenance` en todas las regiones MOLA; en el modo sintético no hay.
- **Pesos del costo** (solo si `/map` trae `radiation_available: true`). Hay un deslizador de
  0 a 100 con un campo numérico para `slope_weight` (0,05 por defecto) y otro para
  `radiation_weight` (0 por defecto). Se envían a `POST /routes`, y el resultado muestra los
  `cost_weights` aplicados. En las demás regiones la solicitud no cambia.
- **Índice de apantallamiento · MODELADO.** Es una capa activable, apagada por defecto. Pinta
  `1 − radiation_modeled`: la inversión la hace la interfaz, porque la API publica la
  exposición relativa. La escala es relativa al rango de la región. No es una dosis ni una
  medición, y exagera el blindaje del relieve porque no incluye la atenuación atmosférica.
- **Alerta solar.** Desde el origen elegido llama a `POST /routes/shelter`, con los mismos
  pesos y una distancia máxima opcional (`max_distance_km`). Dibuja en ámbar la ruta a la
  **zona candidata de espera** y muestra la distancia, el criterio y la nota educativa.
  Si la respuesta es `NO_SHELTER`, explica que es un resultado del modelo y no un fallo.
  Solo funciona con orígenes dentro de la zona de detalle.

Rendimiento: Gale tiene 5 600 celdas. Las capas de celdas (elevación, pendiente, riesgo,
apantallamiento, cuadrícula y la capa invisible de clics) se dibujan con `L.canvas()`, con un
renderizador por pane. La ruta, los pines, las celdas bloqueadas y las misiones siguen en
SVG/DOM. La capa de clics en canvas va por debajo de topónimos, ruta, pines y misiones,
porque un `<canvas>` capta el puntero en toda su superficie. Así, los marcadores y tooltips
de misiones reciben el clic incluso dentro de la zona de detalle. Donde no hay marcador, el
canvas encuentra la celda por geometría o pasa el clic al mapa (malla global). Con `?perf=1`
en la URL se mide la construcción del mapa (`window.__marsPerf`, la consola y un recuadro en
pantalla); `MarsMap.getLayerStats()` da los elementos visibles por capa.

## Pruebas de la interfaz (jsdom)

Requieren Node.js (22.22+ o 24.15+). jsdom es solo una dependencia de desarrollo: el
navegador no la usa.

```bash
cd frontend
npm install     # una vez; instala jsdom en node_modules/ (fuera de Git)
npm test        # node --test: carga index.html, Leaflet y los js con un fetch falso
```

Las pruebas cubren el modo sintético, una región MOLA sin radiación (como Valles) y una Gale
reducida: etiquetas, pesos, capa de apantallamiento, alerta solar (incluidos `NO_SHELTER`
y un origen fuera de la zona) y el vocabulario («zona candidata de espera», nunca
«refugio»). jsdom no pinta: el tiempo real de dibujo se mide en un navegador con `?perf=1`.
