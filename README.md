# Mapa léxico de referencias geográficas — *La Iberia Musical* (1842)

Pipeline de análisis geográfico del corpus de *La Iberia Musical* (Madrid, 1842), 36 números, ~55 000 palabras.  
Parte del proyecto **LexiMus** (PID2022-139589NB-C33, Universidad de Salamanca / ICCMU / Universidad de La Rioja).

## Mapa interactivo

👉 [leximus.usal.es/revistas/MAPA_IBERIA/](https://leximus.usal.es/revistas/MAPA_IBERIA/)

## Archivos

| Archivo | Descripción |
|---|---|
| `extraer_lugares.py` | Pipeline NER completo: BERT + LexiMus-BETO → normalización → geocodificación |
| `añadir_enlaces.py` | Inyecta URLs directas a `pagina.php?id=Y` en el HTML del mapa |
| `reparar_datos.py` | Correcciones post-procesado (cabecera revista, calles editoriales, personas ruidosas) |
| `decisiones.md` | Criterios de normalización y casos ambiguos resueltos |
| `menciones.jsonl` | 1 211 menciones extraídas (lugar, contexto, número, personas co-mencionadas) |
| `lugares.csv` | 176 lugares geocodificados con frecuencias totales y no-editoriales |
| `lugares.geojson` | GeoJSON para cualquier herramienta GIS |

## Metodología

1. **NER** con [`mrm8488/bert-spanish-cased-finetuned-ner`](https://huggingface.co/mrm8488/bert-spanish-cased-finetuned-ner) (entidades LOC) + [`LexiMusUSAL/LexiMus-BETO-per-v1`](https://huggingface.co/LexiMusUSAL/LexiMus-BETO-per-v1) (personas, para evitar falsos positivos geográficos)
2. **Normalización** de variantes históricas (siglo XIX) → nombres canónicos; criterios documentados en `decisiones.md`
3. **Geocodificación** con geopy/Nominatim (1 req/s) + diccionario `COORDS_FIJAS` para topónimos históricos ambiguos (Bohemia, Prusia, teatros madrileños…)
4. **Filtrado editorial** — menciones procedentes de cabeceras, anuncios e imprenta marcadas `ed:true` y ocultables en el mapa
5. **Visualización** con Leaflet.js: círculos proporcionales a frecuencia, coloreados por tipo (ciudad / país / región / sala), popups con citas y enlace directo a la página del facsímil en LexiMus

## Datos de partida

Transcripciones descargadas de [leximus.usal.es/revistas](https://leximus.usal.es/revistas) mediante la API pública (`exportar_corpus.php`).

## Proyecto LexiMus

Universidad de Salamanca · ICCMU · Universidad de La Rioja  
PID2022-139589NB-C33 — Ministerio de Ciencia e Innovación, España
