# Decisiones de normalización — La Iberia Musical (1842)
Generado: 2026-06-05  |  NER: mrm8488/bert-spanish-cased-finetuned-ner + LexiMusUSAL/LexiMus-BETO-per-v1

## Criterios generales
- **Extracción**: mrm8488 (BERT español) para LOC/ORG/PER.
  LexiMus-BETO añade personas musicales (COMPOSITOR, INTERPRETE, CANTANTE, AGRUPACION).
- **Canónico**: topónimo moderno en español normalizado (con tildes).
- **Ortografía de época**: preservada en `lugar_tal_cual` de menciones.jsonl.
- **Tipo**: ciudad | pais | region | sala.
- **Salas**: geocodificadas con coordenadas fijas curadas manualmente.

## Casos ambiguos resueltos

| Variante | Canónico | Tipo | Criterio |
|---|---|---|---|
| la córte / la corte | Madrid | ciudad | Perífrasis para Madrid en prensa de época |
| Capital de las Españas | Madrid | ciudad | Perífrasis para Madrid en prensa de época |
| Iberia | España | pais | Referencia metonímica al territorio español |
| Helvecia | Suiza | pais | Nombre histórico de Suiza |
| Circo / Teatro del Circo | Teatro del Circo (Madrid) | sala | Teatro lírico madrileño, c/ Barquillo |
| Cruz / Teatro de la Cruz | Teatro de la Cruz (Madrid) | sala | Teatro madrileño, demolido 1859 |
| Museo / Museo Lírico | Museo Lírico (Madrid) | sala | Sala de conciertos, calle Alcalá |
| Liceo / Licéo | Gran Teatro del Liceo (Barcelona) | sala | Contextos confirman Barcelona |
| Liceo Artístico / Liceo de Madrid | Liceo Artístico (Madrid) | sala | Institución distinta del Liceo barcelonés |
| Liceo de Granada / Valencia | Liceo de Granada / Valencia | sala | Sedes provinciales del movimiento licéico |
| San Carlos / San Carlo | Teatro San Carlo (Nápoles) | sala | Principal teatro napolitano |
| Teatro de Oriente | Teatro Real (Madrid) | sala | Nombre anterior al Teatro Real |
| teatro de la Scala / Escala | Teatro alla Scala (Milán) | sala | Variantes del nombre italiano |
| Scombrum / Schœnnbrunn | Schönbrunn (Viena) | sala | Grafías de época para Schönbrunn |
| Schwartzemberg / Shovartzemberg | Schwarzenberg (Viena) | sala | Palais Schwarzenberg, conciertos de aristocracia |
| Pésaro / Pesaro | Pésaro | ciudad | Ciudad natal de Rossini |
| INSPRUK | Innsbruck | ciudad | Grafía de época para Innsbruck |
| PERUSA | Perugia | ciudad | Grafía española de Perugia |
| Leipsick / Lipsia / Leisipeck | Leipzig | ciudad | Variantes de época |
| Méjico / Mejico | México D.F. | ciudad | Contexto: siempre ciudad, no país |
| Rosellón | Rosellón | region | Región histórica franco-catalana |
| Prusia | Prusia | region | Estado alemán histórico |
| América meridional | América del Sur | region | Expresión geopolítica de época |
| calle de la Madera / del Sordo | Madrid | ciudad | Dirección de impresión/redacción de la revista |
| LODRE / LONDRE | Londres | ciudad | Variantes OCR de LONDRES |
| San Petesburgo | San Petersburgo | ciudad | Variante OCR |
| WILNA | Vilna | ciudad | Nombre histórico de Vilnius |

*(Todos los lugares normalizados — ningún REVISAR)*
