# Mapa léxico de referencias geográficas — *La Iberia Musical* (1842)

Pipeline NER + geocodificación + mapa interactivo para el análisis de las referencias geográficas en *La Iberia Musical* (Madrid, 1842), 36 números, ~55 000 palabras.

Parte del proyecto **LexiMus: Léxico y ontología de la música en español**  
PID2022-139589NB-C33 — Universidad de Salamanca / ICCMU / Universidad de La Rioja

---

## 👉 [Ver el mapa interactivo](https://leximus.usal.es/revistas/MAPA_IBERIA/)

---

## Archivos

| Archivo | Descripción |
|---|---|
| `extraer_lugares.py` | Pipeline NER completo (ver metodología abajo) |
| `añadir_enlaces.py` | Inyecta URLs directas a `pagina.php?id=Y` en el HTML del mapa |
| `reparar_datos.py` | Correcciones post-procesado: cabecera de la revista, calles editoriales, personas ruidosas, links a página |
| `decisiones.md` | Criterios de normalización y casos ambiguos resueltos (>300 entradas) |
| `menciones.jsonl` | 1 211 menciones extraídas: lugar, contexto, número de revista, personas co-mencionadas, URL a facsímil |
| `lugares.csv` | 176 lugares geocodificados: frecuencia total y no-editorial, contextos, personas asociadas |
| `lugares.geojson` | GeoJSON para cualquier herramienta GIS (QGIS, Kepler, etc.) |

---

## Proceso completo

### 1. Corpus de partida

Las transcripciones de los 36 números se descargaron de [leximus.usal.es/revistas](https://leximus.usal.es/revistas) mediante la API pública (`exportar_corpus.php`, token de acceso). Cada número se almacena como un `.txt` con marcas de página `=== Pág. N ===`.

### 2. Extracción de entidades (NER) — dos modelos en cadena

La extracción se realiza con **dos modelos** ejecutados sobre cada fragmento de texto (~80 palabras):

**Modelo 1 — Detección de lugares:**  
[`mrm8488/bert-spanish-cased-finetuned-ner`](https://huggingface.co/mrm8488/bert-spanish-cased-finetuned-ner)  
BERT en español ajustado para NER. Detecta entidades `LOC`, `PER`, `ORG`. Se utiliza `aggregation_strategy='simple'` y se filtra sobre etiqueta `LOC`.

**Modelo 2 — Filtro de personas (nuestro modelo):**  
[`LexiMusUSAL/LexiMus-BETO-per-v1`](https://huggingface.co/LexiMusUSAL/LexiMus-BETO-per-v1)  
Modelo propio del proyecto LexiMus, basado en `dccuchile/bert-base-spanish-wwm-cased`, entrenado para identificar entidades musicales en español del siglo XIX: `COMPOSITOR`, `INTERPRETE`, `CANTANTE`, `AGRUPACION`. Se aplica sobre los mismos fragmentos y sus entidades se usan para enriquecer el campo `persona_co_mencionada` de cada mención geográfica, y para descartar falsos positivos (nombres de cantantes u obras que BERT-NER etiquetaba como LOC).

> **¿Por qué dos modelos?** spaCy (`es_core_news_lg`) generó más de 700 falsos positivos en texto histórico del XIX: títulos de ópera, nombres de cantantes, secciones de la revista. BERT redujo el ruido drásticamente. El modelo LexiMus resuelve los casos ambiguos persona/lugar que quedan.

### 3. Filtrado y normalización

Tras la extracción se aplican varios niveles de filtrado:

- **Artefactos OCR**: subcadenas WordPiece (`##token`), fragmentos de 1-3 caracteres, abreviaturas de sección.
- **Lista de exclusión (`EXCLUIR`)**: ~50 entidades conocidas no geográficas (títulos de ópera, nombres propios de músicos, topónimos falsos como `LODRE` = imprenta Lodré).
- **Normalización histórica (`NORMA`)**: >300 variantes del siglo XIX → nombre canónico moderno. Ejemplos: `Ñapoles`→`Nápoles`, `Alemania`+`la Alemania`→`Alemania`, `Teatro del Circo (Madrid)`→`Teatro del Circo`, teatros con dirección postal → nombre propio.
- **Etiquetado editorial (`ed:true`)**: menciones procedentes de cabeceras de suscripción, anuncios, colofón tipográfico y direcciones de imprenta/almacén de música (calle de la Madera, calle del Sordo, carrera de San Gerónimo). Visibles pero ocultables en el mapa.

Las decisiones caso por caso están documentadas en `decisiones.md`.

### 4. Geocodificación

- **Nominatim (geopy)**: 1 petición/segundo, user-agent `leximus_iberia_musical_1842_mpalacios@usal.es`.
- **`COORDS_FIJAS`**: ~60 entradas de corrección manual para topónimos que Nominatim resolvía mal en contexto histórico: Bohemia→Checquia (no Brooklyn), Prusia→Polonia central, Granada→Andalucía (no isla del Caribe), teatros madrileños con coordenadas exactas, etc.
- Resultado: 176 de 183 lugares únicos geocodificados (96%).

### 5. Inyección de enlaces a facsímil

`añadir_enlaces.py` recorre cada mención, lee el `.txt` del número correspondiente, busca los primeros 80 caracteres del contexto en los bloques de página, y sustituye el enlace de reserva (`ejemplar.php?id=X`) por la URL exacta de la página (`pagina.php?id=Y`). 93% de las menciones apuntan a la página concreta.

### 6. Correcciones post-procesado

`reparar_datos.py` corrige cuatro problemas detectados en revisión manual:

1. `IBERIA`/`Iberia` como topónimo → en este corpus casi siempre es la cabecera de la propia revista, no la Península. Se eliminan esas 7 menciones de España.
2. Calles y plazas administrativas marcadas `ed:false` que inflaban Madrid con ruido publicitario → `ed:true`.
3. Personas co-mencionadas con fragmentos OCR cortos (`Hay`, `Gris`, `S. M`), títulos de ópera (`Lucrecia Borgia`, `Roberto el Diablo`) y duplicados por salto de línea → limpieza.
4. Re-intento de búsqueda de página exacta para los ~82 fallbacks, recuperando 40 adicionales.

### 7. Visualización

Mapa Leaflet.js con diseño tipográfico del XIX (Playfair Display + EB Garamond):
- Círculos proporcionales a frecuencia (√f × 3)
- Color por tipo: ciudad / país / región / sala y teatro
- Filtro por tipo de lugar y por número de revista (1–36)
- Popups con citas textuales, personas co-mencionadas y enlace directo al facsímil en LexiMus
- Bloque de estadísticas dinámico (referencias, lugares y número activo)

---

## Dependencias

```
pip install transformers torch spacy spacy-transformers geopy folium huggingface-hub paramiko
python -m spacy download es_core_news_lg
```

El modelo LexiMus-BETO requiere `spacy>=3.8,<3.9`.

---

## Cita

Si usas estos scripts o datos, por favor cita:

> Proyecto LexiMus (PID2022-139589NB-C33). *Mapa léxico de referencias geográficas en La Iberia Musical (1842)*. Universidad de Salamanca, 2025. https://github.com/LeximusUSAL/iberia-musical-1842-mapa-lexico
