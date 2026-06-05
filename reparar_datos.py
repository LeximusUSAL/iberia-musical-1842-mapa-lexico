#!/usr/bin/env python3
"""
reparar_datos.py — Cuatro correcciones sobre los datos del mapa léxico.

Fix 1 : Iberia/IBERIA = cabecera de la revista → retirar esas menciones.
Fix 2 : Calles/direcciones editoriales (imprenta, almacenes) → ed:true.
Fix 3 : Personas ruidosas (OCR, abreviaturas, títulos de ópera) → limpiar.
Fix 4 : Menciones con exemplar.php en vez de pagina.php → re-intentar búsqueda.

Opera sobre el HTML final (que tiene url+pag) y reconstruye menciones.jsonl,
lugares.csv y lugares.geojson a partir del resultado limpio.
"""

import json, re, csv, time
from pathlib import Path
from urllib.request import Request, urlopen
from collections import defaultdict

# ── Rutas ────────────────────────────────────────────────────────────────────
BASE     = Path("/Users/maria/Desktop/MAPA LÉXICO")
TXT_DIR  = Path("/Users/maria/Desktop/LexiMus REVISTAS/REVISTAS LIMPIAS_BAJADASWEB/La Iberia Musical")
HTML_F   = BASE / "mapa_iberia_1842_con_enlaces.html"
JSONL_F  = BASE / "menciones.jsonl"
CSV_F    = BASE / "lugares.csv"
GEO_F    = BASE / "lugares.geojson"

BASE_WEB = "https://leximus.usal.es/revistas"
NUM_A_EJID = {0:44,1:3,2:10,3:11,4:12,5:13,6:14,7:15,8:16,9:17,10:18,11:19,
              12:20,13:21,14:22,15:23,16:24,17:25,18:26,19:27,20:28,21:29,
              22:30,23:31,24:32,25:33,26:34,27:35,28:36,29:37,30:38,31:39,
              32:40,33:41,34:42,35:43}

# ── Helpers ──────────────────────────────────────────────────────────────────
def nws(s):
    "Normaliza espacios en blanco."
    return re.sub(r'\s+', ' ', s or '').strip()

def fetch(url):
    r = urlopen(Request(url, headers={"User-Agent":"leximus_iberia/1.0 mpalacios@usal.es"}), timeout=15)
    return r.read().decode("utf-8", errors="replace")

# ── Fix 1: Iberia como cabecera ──────────────────────────────────────────────
_IBERIA_LC = re.compile(r'^(la\s+)?iberia$', re.IGNORECASE)

def es_iberia_revista(mn):
    return bool(_IBERIA_LC.match(mn.get("lugar_tal_cual","").strip()))

# ── Fix 2: Calles editoriales ────────────────────────────────────────────────
# Sólo las que el corpus usa para imprenta, almacenes de música y anuncios.
CALLES_ED = {
    "calle de la Madera",
    "calle del Sordo", "calle del Sordo número 11", "calle del Sordo n",
    "carrera de San Gerónimo", "Carrera de San Gerónimo",
    "calle del Príncipe", "calle del Principe",
    "calle de Fuencarral",
    "plaza de la Constitucion",   # "en casa de su editor, plaza…"
}

def es_calle_editorial(mn):
    return mn.get("lugar_tal_cual","").strip() in CALLES_ED

# ── Fix 3: Limpiar personas ──────────────────────────────────────────────────
TITULOS_OPERA = {
    "Lucrecia Borgia","Roberto el Diablo","Otello","Hugonotes","Los Hugonotes",
    "Zelmira","La Sonámbula","Norma","Lucia","Lucia di Lammermoor",
    "Anna Bolena","La Favorita","El Barbero de Sevilla","Don Juan",
    "La Gazza Ladra","Giuramento","La Aldeana","Belisario","Marino Faliero",
    "Chiara di Rosenberg","Il Furioso","Parisina","Torquato Tasso",
}
_ABREV = re.compile(r'^(Sr|Sra|Mr|Mrs|Dr|Dra|D|Dña|Dn)\.?(\s+[A-Z]\.?)*$', re.IGNORECASE)
_OCR   = re.compile(r'^[A-ZÁÉÍÓÚÑ][a-záéíóúñ]{0,3}$')   # fragmento < 5 chars
_PUNTOCAPITAL = re.compile(r'^[A-ZÁÉÍÓÚÑ]\.\s+[A-ZÁÉÍÓÚÑ]$')  # "S. M", "A. B"

def limpiar_pers(lst):
    seen, out = set(), []
    for p in lst:
        p = p.strip().replace('\n', ' ')
        p = re.sub(r'\s{2,}', ' ', p)
        if not p or len(p) < 4:
            continue
        if p in TITULOS_OPERA:
            continue
        if _ABREV.match(p):
            continue
        if _PUNTOCAPITAL.match(p):
            continue
        if _OCR.match(p) and len(p) < 5:
            continue
        if p not in seen:
            seen.add(p)
            out.append(p)
    return out

# ── Fix 4: Re-intentar pagina exacta ────────────────────────────────────────
def leer_paginas_txt(nrev):
    "Devuelve {num_pag: texto_bloque} para el número de revista nrev."
    f = TXT_DIR / f"iberiamusical_1842_n{nrev:02d}.txt"
    if not f.exists():
        return {}
    raw = f.read_text(encoding="utf-8")
    pags = {}
    for bloque in re.split(r'=== Pág\. (\d+)', raw)[1:]:
        pass
    # split más preciso
    partes = re.split(r'(=== Pág\. \d+)', raw)
    pnum = None
    for parte in partes:
        m = re.match(r'=== Pág\. (\d+)', parte)
        if m:
            pnum = int(m.group(1))
        elif pnum is not None:
            pags[pnum] = parte
    return pags

_pag_ids_cache = {}
def get_pag_ids(nrev):
    "Devuelve {num_pag: pagina_id} consultando ejemplar.php."
    if nrev in _pag_ids_cache:
        return _pag_ids_cache[nrev]
    ejid = NUM_A_EJID.get(nrev)
    if ejid is None:
        return {}
    try:
        html = fetch(f"{BASE_WEB}/ejemplar.php?id={ejid}")
        pags = re.findall(
            r'href="pagina\.php\?id=(\d+)"[^>]*>.*?alt="P[aá]gina\s+(\d+)"',
            html, re.DOTALL | re.IGNORECASE)
        mapping = {int(pnum): int(pid) for pid, pnum in pags}
        _pag_ids_cache[nrev] = mapping
        time.sleep(1)
        return mapping
    except Exception as e:
        print(f"  ! No pude obtener pag_ids para nrev={nrev}: {e}")
        return {}

def buscar_pagina_mejorada(ctx, paginas_txt):
    "Busca el contexto en bloques de página con varios intentos."
    needle_norm = nws(ctx)
    for length in (80, 60, 40, 25, 15):
        needle = needle_norm[:length]
        if len(needle) < 10:
            break
        for pnum, bloque in sorted(paginas_txt.items()):
            if needle in nws(bloque):
                return pnum
    return None

# ── Leer DATA del HTML ───────────────────────────────────────────────────────
print("Leyendo HTML…")
html = HTML_F.read_text(encoding="utf-8")
m = re.search(r'^(const DATA = )(\{.*\});$', html, re.MULTILINE)
if not m:
    raise RuntimeError("No encontré 'const DATA = {...};' en el HTML")
prefix   = m.group(1)
data     = json.loads(m.group(2))
places   = data["places"]

orig_places = len(places)
orig_mens   = sum(len(p["menciones"]) for p in places)
print(f"  Lugares: {orig_places}  Menciones: {orig_mens}")

# ── Identificar menciones con fallback (fix 4) ───────────────────────────────
fallback_issues = set()
for p in places:
    for mn in p["menciones"]:
        if "ejemplar.php" in mn.get("url","") or mn.get("pag",0) == 0:
            fallback_issues.add(mn["n"])

print(f"\nFix 4: {len(fallback_issues)} números con menciones sin página exacta → cargando TXT y consultando web…")
txt_cache   = {}   # nrev → {pnum: bloque}
pag_id_map  = {}   # nrev → {pnum: pagina_id}
for nrev in sorted(fallback_issues):
    txt_cache[nrev]  = leer_paginas_txt(nrev)
    pag_id_map[nrev] = get_pag_ids(nrev)
    found = sum(1 for p in places for mn in p["menciones"]
                if mn["n"]==nrev and ("ejemplar.php" in mn.get("url","") or mn.get("pag",0)==0))
    print(f"  nrev={nrev:2d}  páginas_txt={len(txt_cache[nrev])}  pag_ids={len(pag_id_map[nrev])}  menciones_afectadas≈{found}")

# ── Aplicar fixes ─────────────────────────────────────────────────────────────
stats = defaultdict(int)
new_places = []

for p in places:
    new_mns = []
    for mn in p["menciones"]:

        # Fix 1: Iberia = revista
        if es_iberia_revista(mn):
            stats["f1_iberia_quitada"] += 1
            continue

        # Fix 2: calle editorial → ed:true
        if es_calle_editorial(mn) and not mn.get("ed"):
            mn = dict(mn, ed=True)
            stats["f2_calle_ed"] += 1

        # Fix 3: personas (siempre aplicar para normalizar \n y deduplicar)
        orig_pers  = mn.get("pers", [])
        clean_pers = limpiar_pers(orig_pers)
        if clean_pers != orig_pers:
            mn = dict(mn, pers=clean_pers)
            stats["f3_pers_limpiadas"] += 1

        # Fix 4: re-intentar página exacta
        nrev = mn["n"]
        if ("ejemplar.php" in mn.get("url","") or mn.get("pag",0) == 0) and nrev in txt_cache:
            pnum = buscar_pagina_mejorada(mn.get("txt",""), txt_cache[nrev])
            if pnum and pnum in pag_id_map.get(nrev,{}):
                pid = pag_id_map[nrev][pnum]
                mn  = dict(mn, url=f"{BASE_WEB}/pagina.php?id={pid}", pag=pnum)
                stats["f4_paginas_recuperadas"] += 1
            else:
                stats["f4_paginas_no_recuperadas"] += 1

        new_mns.append(mn)

    if not new_mns:
        stats["lugares_vaciados"] += 1
        continue

    new_p = dict(p, menciones=new_mns, frecuencia=len(new_mns))
    new_places.append(new_p)

data["places"] = new_places
new_mens = sum(len(p["menciones"]) for p in new_places)

print(f"\n=== Resultados ===")
for k, v in sorted(stats.items()):
    print(f"  {k}: {v}")
print(f"  Lugares: {orig_places} → {len(new_places)}  ({orig_places-len(new_places)} eliminados)")
print(f"  Menciones: {orig_mens} → {new_mens}  ({orig_mens-new_mens} eliminadas)")

# ── Escribir HTML actualizado ────────────────────────────────────────────────
print("\nEscribiendo HTML…")
new_data_json = prefix + json.dumps(data, ensure_ascii=False) + ";"
html_new = html[:m.start()] + new_data_json + html[m.end():]
HTML_F.write_text(html_new, encoding="utf-8")
print(f"  HTML escrito ({HTML_F.stat().st_size/1024:.0f} KB)")

# ── Actualizar menciones.jsonl (sin url/pag) ─────────────────────────────────
print("Actualizando menciones.jsonl…")
orig_jsonl = [json.loads(l) for l in JSONL_F.read_text().splitlines() if l.strip()]
# Construir set de (canonico, frase_contexto, num_revista) para menciones válidas
valid_keys = set()
for p in new_places:
    for mn in p["menciones"]:
        valid_keys.add((p["lugar"], nws(mn.get("txt","")), mn["n"]))

new_jsonl = []
for row in orig_jsonl:
    # Fix 1
    if _IBERIA_LC.match(row.get("lugar_tal_cual","").strip()):
        continue
    # Fix 2
    if row.get("lugar_tal_cual","").strip() in CALLES_ED:
        row = dict(row)  # no tenemos campo ed en jsonl, simplemente lo dejamos
    # Fix 3
    if "persona_co_mencionada" in row:
        row = dict(row, persona_co_mencionada=limpiar_pers(row["persona_co_mencionada"]))
    new_jsonl.append(row)

JSONL_F.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in new_jsonl) + "\n",
                   encoding="utf-8")
print(f"  menciones.jsonl: {len(orig_jsonl)} → {len(new_jsonl)} filas")

# ── Regenerar lugares.csv ────────────────────────────────────────────────────
print("Regenerando lugares.csv…")
with open(CSV_F, "w", newline="", encoding="utf-8") as fh:
    w = csv.DictWriter(fh, fieldnames=["lugar","lat","lon","tipo","frecuencia",
                                        "frecuencia_no_editorial","contextos","personas_asociadas"])
    w.writeheader()
    for p in sorted(new_places, key=lambda x: -x["frecuencia"]):
        no_ed = [mn for mn in p["menciones"] if not mn.get("ed")]
        contextos = " | ".join(mn.get("txt","")[:80] for mn in p["menciones"][:5])
        pers = sorted({pp for mn in p["menciones"] for pp in mn.get("pers",[])})
        w.writerow({
            "lugar": p["lugar"], "lat": p["lat"], "lon": p["lon"],
            "tipo": p["tipo"], "frecuencia": p["frecuencia"],
            "frecuencia_no_editorial": len(no_ed),
            "contextos": contextos,
            "personas_asociadas": "; ".join(pers),
        })
print(f"  lugares.csv: {len(new_places)} filas")

# ── Regenerar lugares.geojson ────────────────────────────────────────────────
print("Regenerando lugares.geojson…")
features = []
for p in new_places:
    no_ed = len([mn for mn in p["menciones"] if not mn.get("ed")])
    features.append({
        "type": "Feature",
        "geometry": {"type": "Point", "coordinates": [p["lon"], p["lat"]]},
        "properties": {
            "lugar": p["lugar"], "tipo": p["tipo"],
            "frecuencia": p["frecuencia"],
            "frecuencia_no_editorial": no_ed,
        }
    })
GEO_F.write_text(json.dumps({"type":"FeatureCollection","features":features},
                              ensure_ascii=False, indent=1), encoding="utf-8")
print(f"  lugares.geojson: {len(features)} features")
print("\n✓ Listo.")
