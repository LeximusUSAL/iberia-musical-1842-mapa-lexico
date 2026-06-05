#!/usr/bin/env python3
"""
añadir_enlaces.py
Enriquece mapa_iberia_1842.html con enlaces directos a pagina.php?id=Y

Uso:
    python3 añadir_enlaces.py \
        --html "/Users/maria/Downloads/mapa_iberia_1842.html" \
        --txts "/Users/maria/Desktop/LexiMus REVISTAS/REVISTAS LIMPIAS_BAJADASWEB/La Iberia Musical"
"""

import re, json, time, sys, argparse
from pathlib import Path
from urllib.request import urlopen, Request

BASE = "https://leximus.usal.es/revistas"

NUM_A_EJID = {
    0:44,  1:3,   2:10,  3:11,  4:12,  5:13,  6:14,  7:15,
    8:16,  9:17,  10:18, 11:19, 12:20, 13:21, 14:22, 15:23,
    16:24, 17:25, 18:26, 19:27, 20:28, 21:29, 22:30, 23:31,
    24:32, 25:33, 26:34, 27:35, 28:36, 29:37, 30:38, 31:39,
    32:40, 33:41, 34:42, 35:43,
}

_SEP = re.compile(r'^=== Pág\. (\d+).*?===$', re.MULTILINE)


def fetch(url: str) -> str:
    req = Request(url, headers={"User-Agent": "leximus_iberia/1.0 mpalacios@usal.es"})
    with urlopen(req, timeout=15) as r:
        return r.read().decode('utf-8', errors='replace')


def get_pagina_ids(ejid: int) -> dict:
    """Devuelve {page_num: pagina_id} extrayendo pagina.php?id=Y del HTML del ejemplar."""
    html = fetch(f"{BASE}/ejemplar.php?id={ejid}")
    # Captura id de pagina y número de página en el alt de la imagen
    pags = re.findall(
        r'href="pagina\.php\?id=(\d+)"[^>]*>.*?alt="P[aá]gina (\d+)"',
        html, re.DOTALL | re.IGNORECASE
    )
    return {int(pnum): int(pid) for pid, pnum in pags}


def paginas_del_txt(path: Path) -> dict:
    """Devuelve {page_num: text_block} parseando los marcadores === Pág. N ===."""
    raw = path.read_text(encoding='utf-8')
    partes = _SEP.split(raw)
    # partes = [texto_previo, n1, bloque1, n2, bloque2, ...]
    result = {}
    i = 1
    while i + 1 < len(partes):
        pnum  = int(partes[i])
        bloque = partes[i + 1]
        result[pnum] = bloque
        i += 2
    return result


def nws(s: str) -> str:
    """Normaliza espacios en blanco."""
    return re.sub(r'\s+', ' ', s).strip()


def buscar_pagina(txt_mencion: str, paginas_txt: dict) -> int | None:
    """Busca txt_mencion en los bloques de página y devuelve el número de página."""
    if not txt_mencion or not paginas_txt:
        return None
    for length in (80, 60, 40, 25):
        needle = nws(txt_mencion)[:length]
        if not needle:
            continue
        for pnum, bloque in sorted(paginas_txt.items()):
            if needle in nws(bloque):
                return pnum
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--html", required=True)
    ap.add_argument("--txts", required=True)
    args = ap.parse_args()

    html_path = Path(args.html)
    txts_dir  = Path(args.txts)

    print(f"Leyendo {html_path.name} …")
    html_orig = html_path.read_text(encoding='utf-8')

    # Extrae el JSON del DATA (todo en una línea: const DATA = {...};)
    m = re.search(r'const DATA = (\{.*?\});', html_orig, re.DOTALL)
    if not m:
        sys.exit("No se encontró 'const DATA = {...}' en el HTML.")
    data_str = m.group(1)
    data     = json.loads(data_str)

    # ── 1. Pagina IDs de la web ───────────────────────────────────────────
    print("Obteniendo IDs de páginas de leximus.usal.es (1 req/s) …")
    ejid_paginas: dict = {}
    for nrev, ejid in sorted(NUM_A_EJID.items()):
        if ejid in ejid_paginas:
            continue
        try:
            pmap = get_pagina_ids(ejid)
            ejid_paginas[ejid] = pmap
            print(f"  n{nrev:02d} (ej={ejid}): {len(pmap)} páginas")
        except Exception as e:
            print(f"  n{nrev:02d} (ej={ejid}): ERROR — {e}")
            ejid_paginas[ejid] = {}
        time.sleep(1)

    # ── 2. TXTs locales ────────────────────────────────────────────────────
    print("\nCargando TXTs locales …")
    txt_paginas: dict = {}
    for nrev in NUM_A_EJID:
        p = txts_dir / f"iberiamusical_1842_n{nrev:02d}.txt"
        txt_paginas[nrev] = paginas_del_txt(p) if p.exists() else {}

    # ── 3. Enriquecer menciones ────────────────────────────────────────────
    print("\nEnriqueciendo menciones con URLs …")
    total = exactas = fallback = 0
    for place in data["places"]:
        for men in place["menciones"]:
            total += 1
            nrev = men.get("n", -1)
            ejid = NUM_A_EJID.get(nrev)
            if ejid is None:
                men["url"] = BASE
                continue

            pnum = buscar_pagina(men.get("txt", ""), txt_paginas.get(nrev, {}))
            pid  = ejid_paginas.get(ejid, {}).get(pnum) if pnum else None

            if pid:
                men["url"] = f"{BASE}/pagina.php?id={pid}"
                men["pag"] = pnum
                exactas += 1
            else:
                men["url"] = f"{BASE}/ejemplar.php?id={ejid}"
                men["pag"] = 0
                fallback  += 1

    print(f"  Página exacta:  {exactas}/{total}")
    print(f"  Fallback (nº):  {fallback}/{total}")

    # ── 4. Reemplazar DATA ─────────────────────────────────────────────────
    data_nuevo = json.dumps(data, ensure_ascii=False, separators=(',', ':'))
    html_nuevo = html_orig.replace(data_str, data_nuevo, 1)

    # ── 5. Actualizar el JS del enlace ─────────────────────────────────────
    # Línea original (aproximada):
    #   '<a href="'+URL_REVISTA(m.n)+'" target="_blank" rel="noopener">Leer · núm. '+m.n+' &rsaquo;</a>'
    # Nueva:
    #   '<a href="'+m.url+'" target="_blank" rel="noopener">Ver pág. '+(m.pag||m.n)+' &rsaquo;</a>'
    OLD_LINK = (
        "'<a href=\"'+URL_REVISTA(m.n)+'\" target=\"_blank\" rel=\"noopener\">"
        "Leer · núm. '+m.n+' &rsaquo;</a>'"
    )
    NEW_LINK = (
        "'<a href=\"'+(m.url||URL_REVISTA(m.n))+'\" target=\"_blank\" rel=\"noopener\">"
        "Ver pág. '+(m.pag||m.n)+' &rsaquo;</a>'"
    )
    if OLD_LINK in html_nuevo:
        html_nuevo = html_nuevo.replace(OLD_LINK, NEW_LINK, 1)
        print("Función de enlace actualizada en popupHtml.")
    else:
        print("⚠ No se encontró el patrón exacto del enlace — revisa manualmente.")

    # ── 6. Guardar ─────────────────────────────────────────────────────────
    out = html_path.parent / (html_path.stem + "_con_enlaces.html")
    out.write_text(html_nuevo, encoding='utf-8')
    print(f"\n✓  {out}  ({out.stat().st_size // 1024} KB)")


if __name__ == "__main__":
    main()
