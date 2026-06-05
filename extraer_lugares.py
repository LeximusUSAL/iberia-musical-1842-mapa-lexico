#!/usr/bin/env python3
"""
Pipeline geográfico — La Iberia Musical (1842)
NER con BERT (mrm8488 + LexiMus-BETO) + geocodificación + mapa.

Paso 1  mrm8488 → LOC/ORG/PER por fragmentos de texto
         LexiMus-BETO → COMPOSITOR/INTERPRETE/CANTANTE/AGRUPACION como co-menciones
Paso 2  Normalización de variantes ortográficas de época
Paso 3  Geocodificación con Nominatim
Paso 4  lugares.csv
Paso 5  lugares.geojson
Paso 6  mapa.html (Folium)
Paso 7  decisiones.md
"""

import json, re, time, csv, sys
from pathlib import Path
from datetime import date

# ── Dependencias opcionales ────────────────────────────────────────────────
try:
    from transformers import pipeline as hf_pipeline
except ImportError:
    sys.exit("Instala transformers:  pip install transformers")
try:
    import spacy
except ImportError:
    sys.exit("Instala spacy:  pip install spacy spacy-transformers")
try:
    import folium
except ImportError:
    sys.exit("Instala folium:  pip install folium")
try:
    from geopy.geocoders import Nominatim
    from geopy.exc import GeocoderTimedOut
except ImportError:
    sys.exit("Instala geopy:  pip install geopy")
try:
    from huggingface_hub import snapshot_download
except ImportError:
    sys.exit("Instala huggingface_hub:  pip install huggingface_hub")

# ── Configuración ──────────────────────────────────────────────────────────
DIR        = Path(__file__).parent
JSONL      = DIR / "menciones.jsonl"
CSV_OUT    = DIR / "lugares.csv"
GEO_OUT    = DIR / "lugares.geojson"
MAP_OUT    = DIR / "mapa.html"
DEC_MD     = DIR / "decisiones.md"
CACHE_FILE = DIR / ".bert_cache.jsonl"

LEXIMUS_LOCAL = Path("/tmp/leximus_beto")

# Límite de tokens por fragmento enviado a BERT (conservative)
CHUNK_MAX_WORDS = 80

# Umbral de confianza para LOC/ORG del modelo mrm8488
SCORE_MIN = 0.80
# ──────────────────────────────────────────────────────────────────────────

# ── Carga de modelos ───────────────────────────────────────────────────────
print("Cargando modelos NER…")

# mrm8488: LOC, ORG y PER sobre español histórico
ner_bert = hf_pipeline(
    "ner",
    model="mrm8488/bert-spanish-cased-finetuned-ner",
    aggregation_strategy="simple",
    device=-1,           # CPU
)

# LexiMus-BETO: COMPOSITOR, INTERPRETE, CANTANTE, AGRUPACION
if not LEXIMUS_LOCAL.exists() or not (LEXIMUS_LOCAL / "config.cfg").exists():
    print("Descargando LexiMusUSAL/LexiMus-BETO-per-v1…")
    snapshot_download("LexiMusUSAL/LexiMus-BETO-per-v1",
                      local_dir=str(LEXIMUS_LOCAL))

nlp_leximus = spacy.load(str(LEXIMUS_LOCAL))
print("Modelos listos.\n")

TIPOS_LOC  = {"LOC", "ORG"}   # ORG captura teatros ("Liceo", "Teatro Carlo Felice")
TIPOS_PER  = {"PER"}
ETIQ_LEXIMUS = {"COMPOSITOR", "INTERPRETE", "CANTANTE", "AGRUPACION"}

# Entidades que BERT devuelve como LOC/ORG pero NO son lugares geográficos.
# Se excluyen silenciosamente (aparecen en decisiones.md como "excluidos").
EXCLUIR: set[str] = {
    # Nombres de compositores / intérpretes (all-caps o bien conocidos)
    "CARRAFA", "Carrafa", "Carafa", "RUBINI", "Rubini", "MOZAR", "Mozart",
    "VIARDOT", "Viardot", "GARCÍA", "Garcia", "Gluck", "Haydn", "Haynd",
    "Donizetti", "Rossini", "Bellini", "Meyerbeer", "Paganini", "Herz",
    "Espronceda", "Jacobo", "Bassin", "Bassini", "Kolhau", "Kulbech",
    "Kurbech", "Lobkowitz", "Lobkser", "Wan-Svietén", "Wan-Swieten",
    "Esterhazy", "Esheracy", "Eskeracy", "Esteracy",
    # Títulos de ópera / obras
    "La Aldeana", "Zelmira", "Otello", "Giuramento", "Tauride",
    "Figlia del Reggimento", "Figlia del Regimento", "Regina di Golconda",
    "Rober-le-Diable", "Rober - le - Diable", "Viaggio",
    "Torre misteriosa", "Cavaletta", "Sonnámbula",
    # Publicaciones / secciones editoriales
    "Espectador", "Gaceta", "Diario de Avisos", "Noticioso", "Correo",
    "Revista de Teatros", "Revista de Teatros del 17",
    "Iberia Musical", "La Iberia", "La Iberia Musical",
    "ESTRANJERA", "ESPAÑOL", "ESPAÑOL",
    # Instituciones genéricas (no localizaciones)
    "Junta", "Empresa", "Comision", "Sociedad", "Redaccion", "Provincia",
    "Corps", "Guardia Real", "Real Cámara", "Real Capilla",
    "Real Capilla de S. M", "Real capilla", "Real capilla de S.",
    "Cámara", "Capilla", "ANÉCDOTAS",
    # Personas / títulos de texto
    "Cabrero", "Sr. Cabrero", "Bravo", "Villoslada", "Martin",
    "Carlos X", "S. M", "S. M.", "S. M. C", "Excmo",
    # Otros no geográficos
    "Invierno", "mundo", "Alma", "Parca", "Alpes", "Italiana",
    "Música", "Albion", "Aldeana", "Academia", "Academia fila",
    "Academia Real", "Carolina", "Carmen", "Cella", "Conserva",
    "Comunic", "Capital", "Apolo", "Andelsbat", "Baiding",
    "Bearnes", "Lucero", "Lu", "Alcan", "Art", "Ateneo de Paris",
    "* * *", "; Haydn", "Caldederon",
    # Personas / establecimientos etiquetados como ORG/LOC por BERT
    "Wan - Svietén", "Wan - Swieten", "Salla - Barroilhet",
    "Leduc", "Lobkaer",
    "Lodre", "LODRE",   # Almacenes de música Lodré en Madrid, no la ciudad de Londres
    # Fragmentos genéricos / secciones editoriales
    "Estra", "Espec", "Estrangero", "Literario", "Romano",
    "Teatro", "Iglesia", "colegio", "Salas", "Sales", "Cons",
    "Filarmónico de MADRID", "Gaceta Veneciana",
    "Torreon de Haydn", "Torreon", "Torre blanca",
    "Estanque", "Olimpo", "de Embajadores", "de los Fuertes",
    "Cercle", "sella", "tantino", "universidad", "La Union",
    "Legion de", "Nueva", "Viams", "Yestde",
    "teatro", "teatro Nuevo",
}

# ── Limpieza básica del texto de cada número ───────────────────────────────
_GUION  = re.compile(r'-\n(\w)')
_PAGMRK = re.compile(r'^=== Pág\. \d+.*?===$', re.MULTILINE)

def limpiar(texto: str) -> str:
    texto = _GUION.sub(r'\1', texto)
    texto = _PAGMRK.sub('\n', texto)
    return re.sub(r'\n{3,}', '\n\n', texto).strip()

def num_revista(fname: str) -> int:
    m = re.search(r'_n(\d+)', fname)
    return int(m.group(1)) if m else 0

# ── Segmentación en fragmentos ─────────────────────────────────────────────
def segmentar(texto: str) -> list[str]:
    """
    Divide el texto en fragmentos de ≤ CHUNK_MAX_WORDS palabras,
    cortando en límites de párrafo y luego de frase si es necesario.
    Cada fragmento conserva suficiente contexto para NER.
    """
    parrafos = [p.strip() for p in re.split(r'\n{2,}', texto) if p.strip()]
    fragmentos = []
    for p in parrafos:
        palabras = p.split()
        if len(palabras) <= CHUNK_MAX_WORDS:
            fragmentos.append(p)
        else:
            # cortar en frases
            frases = re.split(r'(?<=[.!?])\s+', p)
            buf, buf_w = [], 0
            for frase in frases:
                fw = len(frase.split())
                if buf_w + fw > CHUNK_MAX_WORDS and buf:
                    fragmentos.append(' '.join(buf))
                    buf, buf_w = [], 0
                buf.append(frase)
                buf_w += fw
            if buf:
                fragmentos.append(' '.join(buf))
    return fragmentos

# ── NER con BERT ───────────────────────────────────────────────────────────
_SUBWORD  = re.compile(r'^##')                      # BERT WordPiece artifact
_SOLO_DIG = re.compile(r'^\d[\d\s\-]*$')            # años, números sueltos
_ABREV    = re.compile(r'^[A-ZÁÉÍÓÚÑ]{1,3}\.?$')   # abreviaturas de 1-3 letras
_TRUNC    = re.compile(r'^[A-ZÁÉÍÓÚÑ][a-záéíóúñ]{2,4}$')  # posibles truncados de 3-5 chars

# Palabras truncadas que sí son lugares válidos completos (ej. Pisa, Reus)
_CORTOS_VALIDOS = {
    "Reus", "Pisa", "Roma", "Lima", "Bonn", "Lyon", "Acre", "Cali", "Mons",
}

def _valida_loc(texto: str) -> bool:
    """True si el texto parece un lugar geográfico válido (no un artefacto)."""
    if not texto or len(texto) < 3:
        return False
    if _SUBWORD.match(texto):
        return False
    if _SOLO_DIG.match(texto):
        return False
    if _ABREV.match(texto):
        return False
    if texto in EXCLUIR:
        return False
    return True

def ner_fragmento(frag: str) -> tuple[list[str], list[str]]:
    """
    Devuelve (lista_locs, lista_pers) para un fragmento de texto.
    lista_locs: textos de entidades LOC/ORG con score ≥ SCORE_MIN, sin artefactos
    lista_pers: textos de entidades PER con score ≥ SCORE_MIN
    """
    try:
        ents = ner_bert(frag)
    except Exception:
        return [], []
    locs, pers = [], []
    for e in ents:
        if e["score"] < SCORE_MIN:
            continue
        texto_ent = e["word"].strip()
        if e["entity_group"] in TIPOS_LOC:
            if _valida_loc(texto_ent):
                locs.append(texto_ent)
        elif e["entity_group"] in TIPOS_PER:
            if texto_ent and len(texto_ent) >= 2 and not _SUBWORD.match(texto_ent):
                pers.append(texto_ent)
    return locs, pers

def ner_leximus_fragmento(frag: str) -> list[str]:
    """Devuelve nombres de personas musicales detectados por LexiMus."""
    try:
        doc = nlp_leximus(frag)
    except Exception:
        return []
    return [e.text.strip() for e in doc.ents if e.label_ in ETIQ_LEXIMUS]

# ── Extracción completa de un número ──────────────────────────────────────
def extraer_numero(texto: str, nrev: int) -> list[dict]:
    """
    Procesa un número completo y devuelve lista de menciones.
    Cada mención: lugar_tal_cual, frase_contexto, num_revista, persona_co_mencionada
    """
    fragmentos = segmentar(texto)
    menciones  = []
    personas_leximus_todo = set()  # acumuladas para filtro global

    for frag in fragmentos:
        locs_bert, pers_bert = ner_fragmento(frag)
        pers_lx = ner_leximus_fragmento(frag)

        # nombres de personas en este fragmento (BERT + LexiMus)
        personas_frag = list(dict.fromkeys(pers_bert + pers_lx))
        personas_leximus_todo.update(pers_lx)

        for loc in locs_bert:
            # filtro: si el modelo BERT lo marcó PER en otro fragmento, skip
            # (no aplicamos filtro inter-fragmento para no perder ciudades homónimas)
            menciones.append({
                "lugar_tal_cual":       loc,
                "frase_contexto":       frag[:400],
                "num_revista":          nrev,
                "persona_co_mencionada": personas_frag,
            })

    return menciones

# ════════════════════════════════════════════════════════════════════════════
# PASO 1 – EXTRACCIÓN NER
# ════════════════════════════════════════════════════════════════════════════
print("── PASO 1: Extracción NER (mrm8488 + LexiMus-BETO) ──")

# Caché por número
cache: dict[int, list] = {}
if CACHE_FILE.exists():
    for line in CACHE_FILE.read_text(encoding='utf-8').splitlines():
        if line.strip():
            obj = json.loads(line)
            cache[obj['num']] = obj['menciones']

ficheros = sorted(DIR.glob("iberiamusical_1842_*.txt"))
todas    = []

for fpath in ficheros:
    nrev  = num_revista(fpath.name)
    texto = limpiar(fpath.read_text(encoding='utf-8'))

    if nrev in cache:
        menciones = cache[nrev]
        print(f"  n{nrev:02d} — {len(menciones):3d} menciones  [caché]")
    else:
        print(f"  n{nrev:02d} — procesando…", end=' ', flush=True)
        menciones = extraer_numero(texto, nrev)
        with open(CACHE_FILE, 'a', encoding='utf-8') as cf:
            cf.write(json.dumps({'num': nrev, 'menciones': menciones},
                                ensure_ascii=False) + '\n')
        print(f"{len(menciones):3d} menciones")

    todas.extend(menciones)

print(f"\n  Total bruto: {len(todas)} menciones en {len(ficheros)} números.")

# ── Filtro post-NER (sobre resultados de caché y nuevas extracciones) ──────
# Elimina artefactos que pasaron por la caché antes de las mejoras al filtro.
_artefactos_excl = []
todas_limpias = []
for m in todas:
    lc = m.get("lugar_tal_cual", "").strip()
    es_artefacto = (
        not lc
        or len(lc) < 4
        or lc in EXCLUIR
        or _SUBWORD.match(lc)
        or _SOLO_DIG.match(lc)
        or _ABREV.match(lc)
        or (lc not in _CORTOS_VALIDOS and _TRUNC.match(lc) and len(lc) < 5)
    )
    if es_artefacto:
        _artefactos_excl.append(lc)
    else:
        todas_limpias.append(m)

todas = todas_limpias
print(f"  Tras filtro:  {len(todas)} menciones ({len(_artefactos_excl)} artefactos eliminados).")

JSONL.write_text(
    '\n'.join(json.dumps(m, ensure_ascii=False) for m in todas) + '\n',
    encoding='utf-8'
)
print("  → menciones.jsonl  (sin normalizar)")

# ════════════════════════════════════════════════════════════════════════════
# PASO 2 – NORMALIZACIÓN
# ════════════════════════════════════════════════════════════════════════════
print("\n── PASO 2: Normalización ──")

# (variante exacta o .lower()) → (canónico, tipo)
# tipo: ciudad | pais | region | sala
NORMA: dict[str, tuple[str, str]] = {
    # España — país y regiones
    "España":             ("España", "pais"),
    "la Península":       ("España", "pais"),
    "la península":       ("España", "pais"),
    "Iberia":             ("España", "pais"),
    "Andalucía":          ("Andalucía", "region"),
    "Andalucia":          ("Andalucía", "region"),
    "Cataluña":           ("Cataluña", "region"),
    "Galicia":            ("Galicia", "region"),
    "Castilla":           ("Castilla", "region"),
    "Castilla la Nueva":  ("Castilla", "region"),
    "Navarra":            ("Navarra", "region"),
    "Aragón":             ("Aragón", "region"),
    "Aragon":             ("Aragón", "region"),
    "Rosellón":           ("Rosellón", "region"),
    "Rosellon":           ("Rosellón", "region"),
    "Provenza":           ("Provenza", "region"),
    "Gascuña":            ("Gascuña", "region"),
    "Lemosín":            ("Lemosín", "region"),
    "Lemosin":            ("Lemosín", "region"),
    "La Mancha":          ("La Mancha", "region"),
    # España — ciudades
    "Madrid":             ("Madrid", "ciudad"),
    "la córte":           ("Madrid", "ciudad"),
    "la corte":           ("Madrid", "ciudad"),
    "Barcelona":          ("Barcelona", "ciudad"),
    "Valencia":           ("Valencia", "ciudad"),
    "Sevilla":            ("Sevilla", "ciudad"),
    "Granada":            ("Granada", "ciudad"),
    "Zaragoza":           ("Zaragoza", "ciudad"),
    "Cádiz":              ("Cádiz", "ciudad"),
    "Cadiz":              ("Cádiz", "ciudad"),
    "Málaga":             ("Málaga", "ciudad"),
    "Malaga":             ("Málaga", "ciudad"),
    "Bilbao":             ("Bilbao", "ciudad"),
    "Santander":          ("Santander", "ciudad"),
    "Valladolid":         ("Valladolid", "ciudad"),
    "Burgos":             ("Burgos", "ciudad"),
    "Toledo":             ("Toledo", "ciudad"),
    "Córdoba":            ("Córdoba", "ciudad"),
    "Córdova":            ("Córdoba", "ciudad"),
    "Murcia":             ("Murcia", "ciudad"),
    "Salamanca":          ("Salamanca", "ciudad"),
    "Zamora":             ("Zamora", "ciudad"),
    "Teruel":             ("Teruel", "ciudad"),
    "Reus":               ("Reus", "ciudad"),
    "Carmona":            ("Carmona", "ciudad"),
    "Daroca":             ("Daroca", "ciudad"),
    "Alicante":           ("Alicante", "ciudad"),
    "Cuenca":             ("Cuenca", "ciudad"),
    "Palma":              ("Palma de Mallorca", "ciudad"),
    # Italia — país y regiones
    "Italia":             ("Italia", "pais"),
    "Toscana":            ("Toscana", "region"),
    "Lombardía":          ("Lombardía", "region"),
    "Lombardia":          ("Lombardía", "region"),
    "Sicilia":            ("Sicilia", "region"),
    "Piamonte":           ("Piamonte", "region"),
    "Cerdeña":            ("Cerdeña", "region"),
    "Estados Romanos":    ("Estados Pontificios", "region"),
    # Italia — ciudades
    "Roma":               ("Roma", "ciudad"),
    "Nápoles":            ("Nápoles", "ciudad"),
    "Napoles":            ("Nápoles", "ciudad"),
    "Napóles":            ("Nápoles", "ciudad"),
    "Milán":              ("Milán", "ciudad"),
    "Milan":              ("Milán", "ciudad"),
    "Venecia":            ("Venecia", "ciudad"),
    "Florencia":          ("Florencia", "ciudad"),
    "Turín":              ("Turín", "ciudad"),
    "Turin":              ("Turín", "ciudad"),
    "Génova":             ("Génova", "ciudad"),
    "Gènova":             ("Génova", "ciudad"),
    "Bolonia":            ("Bolonia", "ciudad"),
    "Bologna":            ("Bolonia", "ciudad"),
    "Bérgamo":            ("Bérgamo", "ciudad"),
    "Bergamo":            ("Bérgamo", "ciudad"),
    "Pésaro":             ("Pésaro", "ciudad"),
    "Pesaro":             ("Pésaro", "ciudad"),
    "Arezzo":             ("Arezzo", "ciudad"),
    "Ferrara":            ("Ferrara", "ciudad"),
    "Verona":             ("Verona", "ciudad"),
    "Trieste":            ("Trieste", "ciudad"),
    "Pisa":               ("Pisa", "ciudad"),
    "Pádua":              ("Pádua", "ciudad"),
    "Padua":              ("Pádua", "ciudad"),
    "Siracusa":           ("Siracusa", "ciudad"),
    "Perugia":            ("Perugia", "ciudad"),
    "Perusa":             ("Perugia", "ciudad"),
    "PERUSA":             ("Perugia", "ciudad"),
    "Reggio":             ("Reggio Emilia", "ciudad"),
    "Orvieto":            ("Orvieto", "ciudad"),
    "Brescia":            ("Brescia", "ciudad"),
    "Castenaso":          ("Castenaso", "ciudad"),
    # Francia
    "Francia":            ("Francia", "pais"),
    "París":              ("París", "ciudad"),
    "Paris":              ("París", "ciudad"),
    "Lyon":               ("Lyon", "ciudad"),
    "Marsella":           ("Marsella", "ciudad"),
    "Burdeos":            ("Burdeos", "ciudad"),
    "Grenoble":           ("Grenoble", "ciudad"),
    "Limoges":            ("Limoges", "ciudad"),
    "Versalles":          ("Versalles", "ciudad"),
    "Bayona":             ("Bayona (Francia)", "ciudad"),
    "Estrasburgo":        ("Estrasburgo", "ciudad"),
    "Orleans":            ("Orléans", "ciudad"),
    "Orange":             ("Orange", "ciudad"),
    "Montpellier":        ("Montpellier", "ciudad"),
    "Perpiñán":           ("Perpiñán", "ciudad"),
    "Perpinan":           ("Perpiñán", "ciudad"),
    # Alemania y Austria
    "Alemania":           ("Alemania", "pais"),
    "Austria":            ("Austria", "pais"),
    "Baviera":            ("Baviera", "region"),
    "BAVIERA":            ("Baviera", "region"),
    "Sajonia":            ("Sajonia", "region"),
    "Bohemia":            ("Bohemia", "region"),
    "Viena":              ("Viena", "ciudad"),
    "Vienna":             ("Viena", "ciudad"),
    "Wiena":              ("Viena", "ciudad"),
    "Berlín":             ("Berlín", "ciudad"),
    "Berlin":             ("Berlín", "ciudad"),
    "BERLIN":             ("Berlín", "ciudad"),
    "Múnich":             ("Múnich", "ciudad"),
    "Munich":             ("Múnich", "ciudad"),
    "Dresde":             ("Dresde", "ciudad"),
    "Hamburgo":           ("Hamburgo", "ciudad"),
    "Hannover":           ("Hannover", "ciudad"),
    "Bonn":               ("Bonn", "ciudad"),
    "Darmstadt":          ("Darmstadt", "ciudad"),
    "Dusseldorf":         ("Düsseldorf", "ciudad"),
    "Dusseldorff":        ("Düsseldorf", "ciudad"),
    "Breslau":            ("Breslau", "ciudad"),
    "Leipzig":            ("Leipzig", "ciudad"),
    "Leipsick":           ("Leipzig", "ciudad"),
    "Lipsia":             ("Leipzig", "ciudad"),
    "Leisipeck":          ("Leipzig", "ciudad"),
    "Brunswick":          ("Brunswick", "ciudad"),
    "Innsbruck":          ("Innsbruck", "ciudad"),
    "INSPRUK":            ("Innsbruck", "ciudad"),
    "Praga":              ("Praga", "ciudad"),
    "PRAGA":              ("Praga", "ciudad"),
    # Reino Unido
    "Inglaterra":         ("Reino Unido", "pais"),
    "Gran Bretaña":       ("Reino Unido", "pais"),
    "Escocia":            ("Escocia", "region"),
    "Londres":            ("Londres", "ciudad"),
    "LONDRES":            ("Londres", "ciudad"),
    "Edimburgo":          ("Edimburgo", "ciudad"),
    "Liverpool":          ("Liverpool", "ciudad"),
    # Otros países europeos
    "Portugal":           ("Portugal", "pais"),
    "Lisboa":             ("Lisboa", "ciudad"),
    "LISBOA":             ("Lisboa", "ciudad"),
    "Bélgica":            ("Bélgica", "pais"),
    "Bruselas":           ("Bruselas", "ciudad"),
    "Países Bajos":       ("Países Bajos", "pais"),
    "Holanda":            ("Países Bajos", "pais"),
    "Paises-bajos":       ("Países Bajos", "pais"),
    "Ámsterdam":          ("Ámsterdam", "ciudad"),
    "Amsterdam":          ("Ámsterdam", "ciudad"),
    "Amsterdan":          ("Ámsterdam", "ciudad"),
    "La Haya":            ("La Haya", "ciudad"),
    "la Haya":            ("La Haya", "ciudad"),
    "el Haya":            ("La Haya", "ciudad"),
    "Luxemburgo":         ("Luxemburgo", "ciudad"),
    "Suiza":              ("Suiza", "pais"),
    "Rusia":              ("Rusia", "pais"),
    "San Petersburgo":    ("San Petersburgo", "ciudad"),
    "Petersburgo":        ("San Petersburgo", "ciudad"),
    "Hungría":            ("Hungría", "pais"),
    "Hungria":            ("Hungría", "pais"),
    "Polonia":            ("Polonia", "pais"),
    "Varsovia":           ("Varsovia", "ciudad"),
    "Suecia":             ("Suecia", "pais"),
    "Estocolmo":          ("Estocolmo", "ciudad"),
    "Dinamarca":          ("Dinamarca", "pais"),
    "Noruega":            ("Noruega", "pais"),
    "Grecia":             ("Grecia", "pais"),
    "Chipre":             ("Chipre", "pais"),
    "Montenegro":         ("Montenegro", "pais"),
    "Mónaco":             ("Mónaco", "ciudad"),
    "Monaco":             ("Mónaco", "ciudad"),
    # Oriente Medio y África
    "Constantinopla":     ("Constantinopla", "ciudad"),
    "CONSTANTINOPLA":     ("Constantinopla", "ciudad"),
    "Egipto":             ("Egipto", "pais"),
    "Alejandría":         ("Alejandría", "ciudad"),
    "Alejandria":         ("Alejandría", "ciudad"),
    "Argel":              ("Argel", "ciudad"),
    "Siria":              ("Siria", "pais"),
    "Perú":               ("Perú", "pais"),
    # América
    "América":            ("América", "region"),
    "Estados Unidos":     ("Estados Unidos", "pais"),
    "Estados-Unidos":     ("Estados Unidos", "pais"),
    "La Habana":          ("La Habana", "ciudad"),
    "la Habana":          ("La Habana", "ciudad"),
    "Habana":             ("La Habana", "ciudad"),
    "México":             ("México D.F.", "ciudad"),
    "Méjico":             ("México D.F.", "ciudad"),
    "Mejico":             ("México D.F.", "ciudad"),
    "Nueva Orleans":      ("Nueva Orleans", "ciudad"),
    "Nueva-York":         ("Nueva York", "ciudad"),
    "NuevaYork":          ("Nueva York", "ciudad"),
    "Lima":               ("Lima", "ciudad"),
    "LIMA":               ("Lima", "ciudad"),
    "Veracruz":           ("Veracruz", "ciudad"),
    # Continentes y zonas
    "Europa":             ("Europa", "region"),
    "Oriente":            ("Oriente", "region"),
    "África":             ("África", "region"),
    "Africa":             ("África", "region"),
    # Teatros y salas — Madrid
    "Teatro Real":            ("Teatro Real (Madrid)", "sala"),
    "Teatro de Oriente":      ("Teatro Real (Madrid)", "sala"),
    "Teatro del Circo":       ("Teatro del Circo (Madrid)", "sala"),
    "Teatro de la Cruz":      ("Teatro de la Cruz (Madrid)", "sala"),
    "Teatro del Príncipe":    ("Teatro del Príncipe (Madrid)", "sala"),
    "Circo":                  ("Teatro del Circo (Madrid)", "sala"),
    "Cruz":                   ("Teatro de la Cruz (Madrid)", "sala"),
    "Museo Lírico":           ("Museo Lírico (Madrid)", "sala"),
    "Museo":                  ("Museo Lírico (Madrid)", "sala"),
    "Conservatorio":          ("Conservatorio (Madrid)", "sala"),
    "Conservatorio de Madrid":("Conservatorio (Madrid)", "sala"),
    "Capilla Real":           ("Capilla Real (Madrid)", "sala"),
    "Instituto Español":      ("Instituto Español (Madrid)", "sala"),
    "Instituto":              ("Instituto Español (Madrid)", "sala"),
    # Teatros y salas — Barcelona
    "Liceo":                  ("Gran Teatro del Liceo (Barcelona)", "sala"),
    "Licéo":                  ("Gran Teatro del Liceo (Barcelona)", "sala"),
    "Gran Teatro del Liceo":  ("Gran Teatro del Liceo (Barcelona)", "sala"),
    "Liceo de Barcelona":     ("Gran Teatro del Liceo (Barcelona)", "sala"),
    "Liceo Artístico":        ("Liceo Artístico (Madrid)", "sala"),
    # Teatros Italia
    "San Carlos":             ("Teatro San Carlo (Nápoles)", "sala"),
    "San Carlo":              ("Teatro San Carlo (Nápoles)", "sala"),
    "San Carlos de Nápoles":  ("Teatro San Carlo (Nápoles)", "sala"),
    "San Cárlos de Nápoles":  ("Teatro San Carlo (Nápoles)", "sala"),
    "La Scala":               ("Teatro alla Scala (Milán)", "sala"),
    "la Scala":               ("Teatro alla Scala (Milán)", "sala"),
    "La Fenice":              ("La Fenice (Venecia)", "sala"),
    "la Fenice":              ("La Fenice (Venecia)", "sala"),
    "teatro de la Fénice":    ("La Fenice (Venecia)", "sala"),
    "Teatro Carlo Felice":    ("Teatro Carlo Felice (Génova)", "sala"),
    "Teatro Regio":           ("Teatro Regio (Turín)", "sala"),
    "Teatro San Benedetto":   ("Teatro San Benedetto (Venecia)", "sala"),
    "teatro San Benedetto":   ("Teatro San Benedetto (Venecia)", "sala"),
    "Teatro filarmónico":     ("Teatro Filarmónico (Verona)", "sala"),
    # Teatros París y otros franceses
    "Ópera de París":              ("Ópera de París", "sala"),
    "Grand Opéra":                 ("Ópera de París", "sala"),
    "Grande Opera":                ("Ópera de París", "sala"),
    "Gran Opera":                  ("Ópera de París", "sala"),
    "la Grandeópera":              ("Ópera de París", "sala"),
    "Opéra":                       ("Ópera de París", "sala"),
    "teatro de la Opera":          ("Ópera de París", "sala"),
    "Théâtre-Italien":             ("Théâtre-Italien (París)", "sala"),
    "Teatro Italiano":             ("Théâtre-Italien (París)", "sala"),
    "teatro Ventadour":            ("Théâtre Ventadour (París)", "sala"),
    "Ventadour":                   ("Théâtre Ventadour (París)", "sala"),
    "L ' ópera Comique":           ("Opéra-Comique (París)", "sala"),
    "Theatre de l ' OperaComique": ("Opéra-Comique (París)", "sala"),
    "Favart":                      ("Opéra-Comique (París)", "sala"),
    "Catedral de Paris":           ("Catedral de Notre-Dame (París)", "sala"),
    "Montmartre":                  ("Montmartre (París)", "ciudad"),
    # Teatros en otras ciudades italianas
    "teatro de la Scala":          ("Teatro alla Scala (Milán)", "sala"),
    "teatro de la Escala":         ("Teatro alla Scala (Milán)", "sala"),
    "R. de la Scala":              ("Teatro alla Scala (Milán)", "sala"),
    "R. della Canobiana":          ("Teatro della Canobbiana (Milán)", "sala"),
    "teatro Cocomero":             ("Teatro Cocomero (Florencia)", "sala"),
    "teatro Comunal":              ("Teatro Comunale (Bolonia)", "sala"),
    "Carlo felice":                ("Teatro Carlo Felice (Génova)", "sala"),
    "Fenice":                      ("La Fenice (Venecia)", "sala"),
    "Fenice de Venecia":           ("La Fenice (Venecia)", "sala"),
    "da Fenice":                   ("La Fenice (Venecia)", "sala"),
    "teatro de San Cárlos de Nápoles": ("Teatro San Carlo (Nápoles)", "sala"),
    "teatro de San Carlos":        ("Teatro San Carlo (Nápoles)", "sala"),
    "teatro de San Cárlos":        ("Teatro San Carlo (Nápoles)", "sala"),
    # Teatros en Londres
    "teatro de la Reina de Londres": ("Her Majesty's Theatre (Londres)", "sala"),
    "teatro de la reina":          ("Her Majesty's Theatre (Londres)", "sala"),
    # Teatros en España (otras ciudades)
    "Liceo de Granada":            ("Liceo de Granada", "sala"),
    "Liceo de Valencia":           ("Liceo de Valencia", "sala"),
    "Liceo de Madrid":             ("Liceo Artístico (Madrid)", "sala"),
    "Licéo de Madrid":             ("Liceo Artístico (Madrid)", "sala"),
    "Liceo Artístico y Literario": ("Liceo Artístico (Madrid)", "sala"),
    "LICEO VALENCIANO":            ("Liceo de Valencia", "sala"),
    "Liceo Valenciano":            ("Liceo de Valencia", "sala"),
    "teatro del Liceo":            ("Gran Teatro del Liceo (Barcelona)", "sala"),
    "teatro del Licéo":            ("Gran Teatro del Liceo (Barcelona)", "sala"),
    "teatro del Principe":         ("Teatro del Príncipe (Madrid)", "sala"),
    "teatro del Circo ;":          ("Teatro del Circo (Madrid)", "sala"),
    "teatro de la Cruz de esa":    ("Teatro de la Cruz (Madrid)", "sala"),
    "teatro de Sta. Cruz":         ("Teatro de la Cruz (Madrid)", "sala"),
    "LA CRUZ":                     ("Teatro de la Cruz (Madrid)", "sala"),
    "DE LA CRUZ":                  ("Teatro de la Cruz (Madrid)", "sala"),
    "teatro del Museo":            ("Museo Lírico (Madrid)", "sala"),
    "Museo - Lírico":              ("Museo Lírico (Madrid)", "sala"),
    "Museo Lirico":                ("Museo Lírico (Madrid)", "sala"),
    "Museo lirico":                ("Museo Lírico (Madrid)", "sala"),
    "Museo lí":                    ("Museo Lírico (Madrid)", "sala"),
    "Museo lírico ;":              ("Museo Lírico (Madrid)", "sala"),
    "Muséo":                       ("Museo Lírico (Madrid)", "sala"),
    "Conservatorio de Música":     ("Conservatorio (Madrid)", "sala"),
    "Conservatorio Nacional de Música": ("Conservatorio (Madrid)", "sala"),
    "Real Capilla":                ("Capilla Real (Madrid)", "sala"),
    "Capilla Real":                ("Capilla Real (Madrid)", "sala"),
    "Sala de la Filarmónica":      ("Conservatorio (Madrid)", "sala"),
    "Liceo de Murcia":             ("Liceo de Murcia", "sala"),
    "Liceo musical":               ("Liceo Artístico (Madrid)", "sala"),
    "Liceo «":                     ("Liceo Artístico (Madrid)", "sala"),
    # Viena — Palacios y salas
    "Schœnnbrunn":                 ("Schönbrunn (Viena)", "sala"),
    "Scombrum":                    ("Schönbrunn (Viena)", "sala"),
    "Schebroum":                   ("Schönbrunn (Viena)", "sala"),
    "Schwartzemberg":              ("Schwarzenberg (Viena)", "sala"),
    "Scwrartzemberg":              ("Schwarzenberg (Viena)", "sala"),
    "Shovartzemberg":              ("Schwarzenberg (Viena)", "sala"),
    "Swartemberg":                 ("Schwarzenberg (Viena)", "sala"),
    "bosque de Scombrum":          ("Schönbrunn (Viena)", "sala"),
    # Variantes de ciudades ya en NORMA
    "San Petesburgo":              ("San Petersburgo", "ciudad"),
    "Stocolmo":                    ("Estocolmo", "ciudad"),
    "LONDRE":                      ("Londres", "ciudad"),
    "BERLIN":                      ("Berlín", "ciudad"),
    "PRAGA":                       ("Praga", "ciudad"),
    "LIMA":                        ("Lima", "ciudad"),
    "LISBOA":                      ("Lisboa", "ciudad"),
    "LONDRE":                      ("Londres", "ciudad"),
    "PERUSA":                      ("Perugia", "ciudad"),
    "INSPRUK":                     ("Innsbruck", "ciudad"),
    "BAVIERA":                     ("Baviera", "region"),
    "CONSTANTINOPLA":              ("Constantinopla", "ciudad"),
    "WILNA":                       ("Vilna", "ciudad"),
    "Amburgo":                     ("Hamburgo", "ciudad"),
    "Montpeller":                  ("Montpellier", "ciudad"),
    "América meridional":          ("América del Sur", "region"),
    "Helvecia":                    ("Suiza", "pais"),
    "Estados - Unidos":            ("Estados Unidos", "pais"),
    "Nueva - York":                ("Nueva York", "ciudad"),
    "Prusia":                      ("Prusia", "region"),
    "Suavia":                      ("Suabia", "region"),
    "Valencia del Cid":            ("Valencia", "ciudad"),
    "Castellar de Aragon":         ("Castellar de Aragon", "ciudad"),
    "Calatayud":                   ("Calatayud", "ciudad"),
    "Capital de las Españas":      ("Madrid", "ciudad"),
    "Corte":                       ("Madrid", "ciudad"),
    "corte":                       ("Madrid", "ciudad"),
    # Madrid — lugares específicos
    "Buen Retiro":                 ("El Retiro (Madrid)", "ciudad"),
    "Retiro":                      ("El Retiro (Madrid)", "ciudad"),
    "Vallecas":                    ("Vallecas", "ciudad"),
    "Montjuich":                   ("Montjuïc (Barcelona)", "ciudad"),
    "Manzanares":                  ("Río Manzanares (Madrid)", "ciudad"),
    "Escorial":                    ("El Escorial", "ciudad"),
    "Vaticano":                    ("Ciudad del Vaticano", "ciudad"),
    "Reims":                       ("Reims", "ciudad"),
    "Oxford":                      ("Oxford", "ciudad"),
    # Salas/lugares sin ciudad aún determinada — se normalizan y geocodifican
    "Cercle Philharmonique":       ("Cercle Philharmonique (Bruselas)", "sala"),
    "Academia Filarmónica":        ("Accademia Filarmonica (Bolonia)", "sala"),
    "Academia Filarmónica Matritense": ("Academia Filarmónica Matritense (Madrid)", "sala"),
    "Academia filarmónica":        ("Accademia Filarmonica (Bolonia)", "sala"),
    "Academia Matritense":         ("Academia Filarmónica Matritense (Madrid)", "sala"),
    "Academia Real de música":     ("Académie Royale de Musique (París)", "sala"),
    "Academia de ciencias de Berlin": ("Academia de Ciencias de Berlín", "sala"),
    "San Isidro":                  ("Real Colegiata de San Isidro (Madrid)", "sala"),
    "san Pedro del Vaticano":      ("Basílica de San Pedro (Vaticano)", "sala"),
    "monasterio de la Pomposa":    ("Abadía de Pomposa (Ferrara)", "sala"),
    "monte Casino":                ("Montecasino", "sala"),
    "iglesia de San Felipe el Real": ("San Felipe el Real (Madrid)", "sala"),
    "iglesia de san Felipe el Real": ("San Felipe el Real (Madrid)", "sala"),
    "iglesia de San Justo":        ("San Justo (Madrid)", "sala"),
    "iglesia de San Luis":         ("San Luis (Madrid)", "sala"),
    "iglesia de San Roque":        ("San Roque (Madrid)", "sala"),
    "iglesia de Santo Tomas":      ("Santo Tomás (Madrid)", "sala"),
    "iglesia de Sto. Tomas":       ("Santo Tomás (Madrid)", "sala"),
    "iglesia de santo Tomas":      ("Santo Tomás (Madrid)", "sala"),
    "iglesia del Cármen Calzado":  ("Carmelitas Calzados (Madrid)", "sala"),
    "N. Sra. de Monserrat":        ("Montserrat (Barcelona)", "sala"),
    "Ntra. Sra. del Cármen":       ("Carmelitas (Madrid)", "sala"),
    # Calles de Madrid (dirección de publicación o evento documentado)
    "calle de la Madera":          ("Madrid", "ciudad"),
    "calle del Sordo":             ("Madrid", "ciudad"),
    "calle del Sordo n":           ("Madrid", "ciudad"),
    "calle del Sordo número 11":   ("Madrid", "ciudad"),
    "Carrera de San Gerónimo":     ("Madrid", "ciudad"),
    "carrera de San Gerónimo":     ("Madrid", "ciudad"),
    "calle de Fuencarral":         ("Madrid", "ciudad"),
    "calle de Juan de Dios":       ("Madrid", "ciudad"),
    "calle de Toledo":             ("Madrid", "ciudad"),
    "calle del Alamo":             ("Madrid", "ciudad"),
    "calle del Duque de la Victoria": ("Madrid", "ciudad"),
    "calle del Olivo":             ("Madrid", "ciudad"),
    "calle del Principe":          ("Madrid", "ciudad"),
    "calle del Príncipe":          ("Madrid", "ciudad"),
    "Angosta de Peligros":         ("Madrid", "ciudad"),
    "Prado":                       ("El Prado (Madrid)", "ciudad"),
    "Palacio":                     ("Palacio Real (Madrid)", "sala"),
    "Villahermosa":                ("Palacio de Villahermosa (Madrid)", "sala"),
    "Quinta la Bella":             ("La Quinta de la Bella (Madrid)", "sala"),
    "Granja":                      ("La Granja de San Ildefonso", "ciudad"),
    "San Nicolas":                 ("San Nicolás (Madrid)", "sala"),
    "Alcalá":                      ("Alcalá de Henares", "ciudad"),
    # Lugares bibliográficos no geográficos (excluir de mapa pero registrar)
    "sala del Jager":              ("Sala del Jáger", "sala"),
    "teatro de Pera":              ("Teatro de Pera (Constantinopla)", "sala"),
    # Variantes OCR adicionales detectadas en corpus
    "Córdo":                       ("Córdoba", "ciudad"),
    "San Cárlos":                  ("Teatro San Carlo (Nápoles)", "sala"),
    "S. Carlos":                   ("Teatro San Carlo (Nápoles)", "sala"),
    "VICENZA":                     ("Vicenza", "ciudad"),
    "TICEO":                       ("Gran Teatro del Liceo (Barcelona)", "sala"),
    "glaterra":                    ("Reino Unido", "pais"),
    "teatro de los Caños del Peral": ("Teatro de los Caños del Peral (Madrid)", "sala"),
    "teatro Ita":                  ("Théâtre-Italien (París)", "sala"),
    "teatro I":                    ("Théâtre-Italien (París)", "sala"),
    "teatro I.":                   ("Théâtre-Italien (París)", "sala"),
    "Escala":                      ("Teatro alla Scala (Milán)", "sala"),
    "La Alhambra":                 ("La Alhambra (Granada)", "sala"),
    "Alhambra":                    ("La Alhambra (Granada)", "sala"),
    "INSPRUK el Clero":            ("Innsbruck", "ciudad"),
    "La Union":                    ("La Unión (Murcia)", "ciudad"),
    "San Etienne":                 ("Saint-Étienne", "ciudad"),
    "Santa Cecilia":               ("Accademia di Santa Cecilia (Roma)", "sala"),
    "Sta. Cecilia":                ("Accademia di Santa Cecilia (Roma)", "sala"),
    "Sta. Cruz":                   ("Teatro de la Cruz (Madrid)", "sala"),
    "Santo Tomas":                 ("Santo Tomás (Madrid)", "sala"),
    "Ayuntamiento de Madrid":      ("Madrid", "ciudad"),
    "Principe":                    ("Teatro del Príncipe (Madrid)", "sala"),
    "Príncipe":                    ("Teatro del Príncipe (Madrid)", "sala"),
    "Circo ;":                     ("Teatro del Circo (Madrid)", "sala"),
    "teatro del Gimnasio":         ("Théâtre du Gymnase (París)", "sala"),
    "teatro de la Cour":           ("Théâtre de la Cour (Bruselas)", "sala"),
    "iglesia de los Inválidos de París": ("Hôtel des Invalides (París)", "sala"),
    "cementerio del Padre Lachaise": ("Père Lachaise (París)", "ciudad"),
    "plaza de la Constitucion":    ("Madrid", "ciudad"),
    "Leucades":                    ("Leucadia (Grecia)", "ciudad"),
    "Buena - Vista":               ("Buenavista (Madrid)", "ciudad"),
    "Valenciana":                  ("Valencia", "ciudad"),
    "Venecia la bella":            ("Venecia", "ciudad"),
    "Veron":                       ("Verona", "ciudad"),
    "Sútera":                      ("Sutera (Sicilia)", "ciudad"),
    "Támesis":                     ("Río Támesis (Londres)", "ciudad"),
    "Carmen Calzado":              ("Carmelitas Calzados (Madrid)", "sala"),
    "Museo edificio de las Vallecas": ("Vallecas", "ciudad"),
    "Santa María":                 ("Santa María (iglesia, Madrid)", "sala"),
    "Sta. Clara":                  ("Convento de Santa Clara", "sala"),
}

# Conjunto de variantes para búsqueda case-insensitive
_NORMA_LOWER = {k.lower(): v for k, v in NORMA.items()}

def normalizar(variante: str) -> tuple[str, str]:
    if variante in NORMA:
        return NORMA[variante]
    if variante.lower() in _NORMA_LOWER:
        return _NORMA_LOWER[variante.lower()]
    return variante, "REVISAR"

for m in todas:
    m["canonico"], m["tipo"] = normalizar(m["lugar_tal_cual"])

sin_norma = sorted({m["lugar_tal_cual"] for m in todas if m["tipo"] == "REVISAR"})
print(f"  Normalizados. Pendientes de revisión: {len(sin_norma)}")
if sin_norma:
    for p in sin_norma:
        f = sum(1 for m in todas if m["lugar_tal_cual"] == p)
        print(f"    [{f:3d}x] {p}")

JSONL.write_text(
    '\n'.join(json.dumps(m, ensure_ascii=False) for m in todas) + '\n',
    encoding='utf-8'
)

# ════════════════════════════════════════════════════════════════════════════
# PASO 3 – GEOCODIFICACIÓN
# ════════════════════════════════════════════════════════════════════════════
print("\n── PASO 3: Geocodificación ──")
geolocator = Nominatim(user_agent="leximus_iberia_musical_1842_mpalacios@usal.es")

COORDS_FIJAS = {
    # Madrid — teatros y salas
    "Teatro del Circo (Madrid)":         (40.4085, -3.6965),
    "Teatro de la Cruz (Madrid)":        (40.4155, -3.7017),
    "Teatro del Príncipe (Madrid)":      (40.4143, -3.7012),
    "Teatro Real (Madrid)":              (40.4182, -3.7107),
    "Liceo Artístico (Madrid)":          (40.4168, -3.7035),
    "Museo Lírico (Madrid)":             (40.4168, -3.7035),
    "Conservatorio (Madrid)":            (40.4212, -3.6964),
    "Capilla Real (Madrid)":             (40.4182, -3.7145),
    "Instituto Español (Madrid)":        (40.4168, -3.7035),
    "Academia Filarmónica Matritense (Madrid)": (40.4168, -3.7035),
    "San Felipe el Real (Madrid)":       (40.4159, -3.7073),
    "San Justo (Madrid)":                (40.4150, -3.7099),
    "San Nicolás (Madrid)":              (40.4190, -3.7143),
    "El Retiro (Madrid)":                (40.4153, -3.6844),
    "Palacio Real (Madrid)":             (40.4179, -3.7143),
    "Palacio de Villahermosa (Madrid)":  (40.4153, -3.6960),
    "La Quinta de la Bella (Madrid)":    (40.4750, -3.7170),
    # Barcelona
    "Gran Teatro del Liceo (Barcelona)": (41.3796,  2.1726),
    "Liceo de Granada":                  (37.1773, -3.5997),
    "Liceo de Valencia":                 (39.4699, -0.3763),
    # Italia
    "Teatro San Carlo (Nápoles)":        (40.8333, 14.2501),
    "Teatro alla Scala (Milán)":         (45.4674,  9.1892),
    "Teatro della Canobbiana (Milán)":   (45.4641,  9.1873),
    "La Fenice (Venecia)":               (45.4334, 12.3317),
    "Teatro Carlo Felice (Génova)":      (44.4073,  8.9339),
    "Teatro Regio (Turín)":              (45.0706,  7.6880),
    "Teatro San Benedetto (Venecia)":    (45.4366, 12.3350),
    "Teatro Filarmónico (Verona)":       (45.4425, 10.9980),
    "Teatro Cocomero (Florencia)":       (43.7760,  11.2549),
    "Teatro Comunale (Bolonia)":         (44.4949,  11.3426),
    "Accademia Filarmonica (Bolonia)":   (44.4948,  11.3427),
    "Abadía de Pomposa (Ferrara)":       (44.8607,  12.1694),
    "Basílica de San Pedro (Vaticano)":  (41.9022,  12.4534),
    # París y Francia
    "Ópera de París":                    (48.8719,  2.3316),
    "Théâtre-Italien (París)":           (48.8706,  2.3449),
    "Théâtre Ventadour (París)":         (48.8686,  2.3410),
    "Opéra-Comique (París)":             (48.8706,  2.3472),
    "Catedral de Notre-Dame (París)":    (48.8530,  2.3499),
    # Viena
    "Schönbrunn (Viena)":                (48.1845,  16.3122),
    "Schwarzenberg (Viena)":             (48.2002,  16.3812),
    # Londres
    "Her Majesty's Theatre (Londres)":   (51.5071, -0.1336),
    # Bruselas
    "Cercle Philharmonique (Bruselas)":  (50.8476,  4.3572),
    # Miscelánea
    "Montecasino":                       (41.4736,  13.8136),
    "Teatro de Pera (Constantinopla)":   (41.0338,  28.9789),
    "La Granja de San Ildefonso":        (40.8985,  -4.0127),
    "La Alhambra (Granada)":             (37.1760,  -3.5881),
    "Teatro de los Caños del Peral (Madrid)": (40.4178, -3.7093),
    "Accademia di Santa Cecilia (Roma)": (41.9000,  12.4797),
    "Théâtre du Gymnase (París)":        (48.8721,   2.3481),
    "Hôtel des Invalides (París)":       (48.8556,   2.3123),
    "Père Lachaise (París)":             (48.8600,   2.3932),
    "Vicenza":                           (45.5455,  11.5353),
    "La Unión (Murcia)":                 (37.6216,  -0.8753),
    "Leucadia (Grecia)":                 (38.7167,  20.6500),
    "Buenavista (Madrid)":               (40.4230,  -3.6889),
    "Sutera (Sicilia)":                  (37.5175,  13.7436),
    "Saint-Étienne":                     (45.4397,   4.3872),
    # Corrección de coordenadas erróneas de Nominatim (nombres ambiguos)
    "Europa":                            (50.0000,  15.0000),
    "Bohemia":                           (50.0000,  14.5000),
    "Prusia":                            (52.5000,  20.0000),
    "Sajonia":                           (51.0000,  13.5000),
    "Suabia":                            (48.5000,   9.5000),
    "América del Sur":                   (-15.0000, -60.0000),
    "América":                           (10.0000,  -80.0000),
    "Oriente":                           (35.0000,  40.0000),
    "El Retiro (Madrid)":                (40.4153,  -3.6844),
    "El Prado (Madrid)":                 (40.4138,  -3.6922),
    "Río Manzanares (Madrid)":           (40.4050,  -3.7100),
    "San Luis (Madrid)":                 (40.4157,  -3.7047),
    "San Roque (Madrid)":                (40.4140,  -3.7070),
    "Carmelitas (Madrid)":               (40.4165,  -3.7050),
    "Carmelitas Calzados (Madrid)":      (40.4165,  -3.7050),
    # España — ciudades y regiones con geocodificación errónea en Nominatim
    "Granada":                           (37.1760,  -3.5973),
    "Castilla":                          (41.5000,  -3.5000),
    "La Mancha":                         (39.0000,  -2.5000),
    "Rosellón":                          (42.7000,   2.7000),
    "Gascuña":                           (43.5000,   0.5000),
    "Montserrat (Barcelona)":            (41.5934,   1.8407),
    "Carmona":                           (37.4708,  -5.6411),
    "Alicante":                          (38.3453,  -0.4831),
    "Palma de Mallorca":                 (39.5696,   2.6502),
    # Italia
    "Perugia":                           (43.1107,  12.3908),
    "Pádua":                             (45.4077,  11.8762),
    # Latinoamérica — corregir México (país vs. ciudad)
    "México D.F.":                       (19.4326,  -99.1332),
    # Otros
    "Río Támesis":                       (51.5074,  -0.1278),
    "Támesis":                           (51.5074,  -0.1278),
    "Santo Tomás (Madrid)":              (40.4155,  -3.7080),
    "San Justo (Madrid)":                (40.4150,  -3.7099),
}

# Agrupa por canónico
lugares_u: dict[str, dict] = {}
for m in todas:
    c = m["canonico"]
    if c not in lugares_u:
        lugares_u[c] = {"tipo": m["tipo"], "frecuencia": 0,
                        "contextos": [], "personas": set()}
    lugares_u[c]["frecuencia"] += 1
    lugares_u[c]["contextos"].append(m["frase_contexto"])
    lugares_u[c]["personas"].update(m.get("persona_co_mencionada") or [])

geo_cache: dict[str, tuple] = {}

def geocodificar(nombre: str, tipo: str) -> tuple:
    if tipo == "REVISAR":
        return None, None
    if nombre in COORDS_FIJAS:
        return COORDS_FIJAS[nombre]
    query = (nombre
             .replace(" (Madrid)", "").replace(" (Barcelona)", "")
             .replace(" (Nápoles)", "").replace(" (Milán)", "")
             .replace(" (Venecia)", "").replace(" (Génova)", "")
             .replace(" (Turín)", "").replace(" (Verona)", "")
             .replace(" (París)", "").replace(" D.F.", ""))
    if query in geo_cache:
        return geo_cache[query]
    try:
        loc = geolocator.geocode(
            query, language="es", timeout=10,
            featuretype=["country", "city", "state", "region"],
        )
        time.sleep(1)
        if loc:
            geo_cache[query] = (loc.latitude, loc.longitude)
            return loc.latitude, loc.longitude
    except GeocoderTimedOut:
        time.sleep(3)
    geo_cache[query] = (None, None)
    return None, None

for nombre, datos in lugares_u.items():
    lat, lon = geocodificar(nombre, datos["tipo"])
    datos["lat"] = lat
    datos["lon"] = lon
    if lat:
        print(f"  ✓ {nombre:<45} {lat:.4f}, {lon:.4f}")
    else:
        print(f"  · {nombre}")

# ════════════════════════════════════════════════════════════════════════════
# PASO 4 – LUGARES.CSV
# ════════════════════════════════════════════════════════════════════════════
print("\n── PASO 4: lugares.csv ──")
filas = []
for nombre, d in sorted(lugares_u.items(), key=lambda x: -x[1]["frecuencia"]):
    filas.append({
        "lugar":              nombre,
        "lat":                d["lat"] or "",
        "lon":                d["lon"] or "",
        "tipo":               d["tipo"],
        "frecuencia":         d["frecuencia"],
        "contextos":          " | ".join(dict.fromkeys(d["contextos"]))[:600],
        "personas_asociadas": "; ".join(sorted(d["personas"]))[:300],
    })
if filas:
    with open(CSV_OUT, 'w', newline='', encoding='utf-8') as f:
        w = csv.DictWriter(f, fieldnames=filas[0].keys())
        w.writeheader()
        w.writerows(filas)
    print(f"  → {CSV_OUT.name}  ({len(filas)} lugares únicos)")
else:
    print("  Sin lugares geocodificados.")

# ════════════════════════════════════════════════════════════════════════════
# PASO 5 – LUGARES.GEOJSON
# ════════════════════════════════════════════════════════════════════════════
print("\n── PASO 5: lugares.geojson ──")
features = []
for f in filas:
    if not f["lat"]:
        continue
    features.append({
        "type": "Feature",
        "geometry": {"type": "Point",
                     "coordinates": [float(f["lon"]), float(f["lat"])]},
        "properties": {k: v for k, v in f.items() if k not in ("lat", "lon")},
    })
GEO_OUT.write_text(
    json.dumps({"type": "FeatureCollection", "features": features},
               ensure_ascii=False, indent=2),
    encoding='utf-8'
)
print(f"  → {GEO_OUT.name}  ({len(features)} puntos geocodificados)")

# ════════════════════════════════════════════════════════════════════════════
# PASO 6 – MAPA.HTML
# ════════════════════════════════════════════════════════════════════════════
print("\n── PASO 6: mapa.html ──")
COLORES = {"ciudad": "blue", "pais": "red", "region": "green",
           "sala": "purple", "REVISAR": "orange"}

mapa     = folium.Map(location=[44, 5], zoom_start=4, tiles="CartoDB positron")
freq_max = max((d["frecuencia"] for d in lugares_u.values()), default=1)

for nombre, d in lugares_u.items():
    if not d["lat"]:
        continue
    radio = 5 + 22 * (d["frecuencia"] / freq_max)
    color = COLORES.get(d["tipo"], "gray")
    perso = ", ".join(sorted(d["personas"]))[:250] or "—"
    ctx   = d["contextos"][0][:300] if d["contextos"] else "—"
    popup = folium.Popup(
        f"<b>{nombre}</b><br>"
        f"<i>Tipo:</i> {d['tipo']} &nbsp; <i>Menciones:</i> {d['frecuencia']}<br>"
        f"<i>Personas:</i> {perso}<hr>"
        f"<small>{ctx}…</small>",
        max_width=380,
    )
    folium.CircleMarker(
        location=[d["lat"], d["lon"]],
        radius=radio, color=color, fill=True, fill_opacity=0.65,
        popup=popup,
        tooltip=f"{nombre} ({d['frecuencia']}x)",
    ).add_to(mapa)

mapa.get_root().html.add_child(folium.Element("""
<div style="position:fixed;bottom:30px;left:30px;z-index:1000;
     background:white;padding:12px 16px;border-radius:8px;
     font-size:13px;border:1px solid #bbb;box-shadow:2px 2px 6px rgba(0,0,0,.15)">
  <b>La Iberia Musical 1842</b><br>Geografía musical<br><br>
  <span style="color:blue">●</span> Ciudad &nbsp;
  <span style="color:red">●</span> País &nbsp;
  <span style="color:green">●</span> Región<br>
  <span style="color:purple">●</span> Teatro/Sala<br>
  <small>Radio ∝ frecuencia de mención</small>
</div>"""))
mapa.save(str(MAP_OUT))
print(f"  → {MAP_OUT.name}")

# ════════════════════════════════════════════════════════════════════════════
# PASO 7 – DECISIONES.MD
# ════════════════════════════════════════════════════════════════════════════
excluidos_con_frec = []
for ex in sorted(EXCLUIR):
    f = sum(1 for m in todas if m["lugar_tal_cual"] == ex)
    if f > 0:
        excluidos_con_frec.append((ex, f))

dec = [
    "# Decisiones de normalización — La Iberia Musical (1842)",
    f"Generado: {date.today().isoformat()}  |  NER: mrm8488/bert-spanish-cased-finetuned-ner + LexiMusUSAL/LexiMus-BETO-per-v1",
    "",
    "## Criterios generales",
    "- **Extracción**: mrm8488 (BERT español) para LOC/ORG/PER.",
    "  LexiMus-BETO añade personas musicales (COMPOSITOR, INTERPRETE, CANTANTE, AGRUPACION).",
    "- **Canónico**: topónimo moderno en español normalizado (con tildes).",
    "- **Ortografía de época**: preservada en `lugar_tal_cual` de menciones.jsonl.",
    "- **Tipo**: ciudad | pais | region | sala.",
    "- **Salas**: geocodificadas con coordenadas fijas curadas manualmente.",
    "",
    "## Casos ambiguos resueltos",
    "",
    "| Variante | Canónico | Tipo | Criterio |",
    "|---|---|---|---|",
    "| la córte / la corte | Madrid | ciudad | Perífrasis para Madrid en prensa de época |",
    "| Capital de las Españas | Madrid | ciudad | Perífrasis para Madrid en prensa de época |",
    "| Iberia | España | pais | Referencia metonímica al territorio español |",
    "| Helvecia | Suiza | pais | Nombre histórico de Suiza |",
    "| Circo / Teatro del Circo | Teatro del Circo (Madrid) | sala | Teatro lírico madrileño, c/ Barquillo |",
    "| Cruz / Teatro de la Cruz | Teatro de la Cruz (Madrid) | sala | Teatro madrileño, demolido 1859 |",
    "| Museo / Museo Lírico | Museo Lírico (Madrid) | sala | Sala de conciertos, calle Alcalá |",
    "| Liceo / Licéo | Gran Teatro del Liceo (Barcelona) | sala | Contextos confirman Barcelona |",
    "| Liceo Artístico / Liceo de Madrid | Liceo Artístico (Madrid) | sala | Institución distinta del Liceo barcelonés |",
    "| Liceo de Granada / Valencia | Liceo de Granada / Valencia | sala | Sedes provinciales del movimiento licéico |",
    "| San Carlos / San Carlo | Teatro San Carlo (Nápoles) | sala | Principal teatro napolitano |",
    "| Teatro de Oriente | Teatro Real (Madrid) | sala | Nombre anterior al Teatro Real |",
    "| teatro de la Scala / Escala | Teatro alla Scala (Milán) | sala | Variantes del nombre italiano |",
    "| Scombrum / Schœnnbrunn | Schönbrunn (Viena) | sala | Grafías de época para Schönbrunn |",
    "| Schwartzemberg / Shovartzemberg | Schwarzenberg (Viena) | sala | Palais Schwarzenberg, conciertos de aristocracia |",
    "| Pésaro / Pesaro | Pésaro | ciudad | Ciudad natal de Rossini |",
    "| INSPRUK | Innsbruck | ciudad | Grafía de época para Innsbruck |",
    "| PERUSA | Perugia | ciudad | Grafía española de Perugia |",
    "| Leipsick / Lipsia / Leisipeck | Leipzig | ciudad | Variantes de época |",
    "| Méjico / Mejico | México D.F. | ciudad | Contexto: siempre ciudad, no país |",
    "| Rosellón | Rosellón | region | Región histórica franco-catalana |",
    "| Prusia | Prusia | region | Estado alemán histórico |",
    "| América meridional | América del Sur | region | Expresión geopolítica de época |",
    "| calle de la Madera / del Sordo | Madrid | ciudad | Dirección de impresión/redacción de la revista |",
    "| LODRE / LONDRE | Londres | ciudad | Variantes OCR de LONDRES |",
    "| San Petesburgo | San Petersburgo | ciudad | Variante OCR |",
    "| WILNA | Vilna | ciudad | Nombre histórico de Vilnius |",
    "",
]
if excluidos_con_frec:
    dec += [
        "## Entidades excluidas (no son lugares geográficos)",
        "",
        "BERT las detectó como ORG/LOC pero son personas, títulos de ópera o publicaciones.",
        "",
        "| Entidad excluida | Frec. | Motivo |",
        "|---|---|---|",
    ]
    for ex, f in excluidos_con_frec:
        dec.append(f"| {ex} | {f} | en lista EXCLUIR |")
    dec.append("")
if sin_norma:
    dec += [
        "## Lugares pendientes de revisión (tipo=REVISAR)",
        "",
        "| Lugar | Frec. | Decisión |",
        "|---|---|---|",
    ]
    for p in sin_norma:
        f = sum(1 for m in todas if m["lugar_tal_cual"] == p)
        dec.append(f"| {p} | {f} | ← PENDIENTE |")
else:
    dec.append("*(Todos los lugares normalizados — ningún REVISAR)*")

DEC_MD.write_text('\n'.join(dec) + '\n', encoding='utf-8')
print(f"  → {DEC_MD.name}")

# ── Resumen ───────────────────────────────────────────────────────────────
print("\n" + "═" * 55)
print("RESUMEN")
print("═" * 55)
print(f"  Menciones extraídas:      {len(todas)}")
print(f"  Lugares únicos:           {len(lugares_u)}")
con_c = sum(1 for d in lugares_u.values() if d["lat"])
print(f"  Con coordenadas:          {con_c}")
print(f"  Sin coordenadas:          {len(lugares_u) - con_c}")
print(f"  Pendientes de revisión:   {len(sin_norma)}")
