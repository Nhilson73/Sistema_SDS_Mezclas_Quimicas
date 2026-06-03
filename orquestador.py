"""Orquestador de datos: SDS.md -> cache -> PubChem -> Wikipedia -> CSV descargables."""

import json
import os
import re
from datetime import datetime, timezone

import requests as http_requests

from database import db
from models import CacheApi, SdsSubida


# ---------------------------------------------------------------------------
# Parseo de archivos SDS en formato .md
# ---------------------------------------------------------------------------

_RE_CAS = re.compile(r"\b(\d{2,7}-\d{2}-\d)\b")
_RE_FRASE_H = re.compile(r"\b(H\d{3}[a-zA-Z]?)\b")
_RE_FRASE_P = re.compile(r"\b(P\d{3})\b")

_SECCION_PATRONES = [
    (2, re.compile(r"(?:SECCI[OÓ]N\s*2|2[\.\)]\s*Identificaci[oó]n)", re.IGNORECASE)),
    (3, re.compile(r"(?:SECCI[OÓ]N\s*3|3[\.\)]\s*Composici[oó]n)", re.IGNORECASE)),
    (4, re.compile(r"(?:SECCI[OÓ]N\s*4|4[\.\)]\s*Primeros\s*auxilios)", re.IGNORECASE)),
    (5, re.compile(r"(?:SECCI[OÓ]N\s*5|5[\.\)]\s*Medidas)", re.IGNORECASE)),
    (6, re.compile(r"(?:SECCI[OÓ]N\s*6|6[\.\)]\s*Medidas.*vertido)", re.IGNORECASE)),
    (7, re.compile(r"(?:SECCI[OÓ]N\s*7|7[\.\)]\s*Manipulaci[oó]n)", re.IGNORECASE)),
    (8, re.compile(r"(?:SECCI[OÓ]N\s*8|8[\.\)]\s*Control)", re.IGNORECASE)),
    (9, re.compile(r"(?:SECCI[OÓ]N\s*9|9[\.\)]\s*Propiedades\s*f[ií]sicas)", re.IGNORECASE)),
    (10, re.compile(r"(?:SECCI[OÓ]N\s*10|10[\.\)]\s*Estabilidad)", re.IGNORECASE)),
    (11, re.compile(r"(?:SECCI[OÓ]N\s*11|11[\.\)]\s*Informaci[oó]n\s*toxicol[oó]gica)", re.IGNORECASE)),
    (12, re.compile(r"(?:SECCI[OÓ]N\s*12|12[\.\)]\s*Informaci[oó]n\s*ecol[oó]gica)", re.IGNORECASE)),
    (13, re.compile(r"(?:SECCI[OÓ]N\s*13|13[\.\)]\s*Consideraciones)", re.IGNORECASE)),
    (14, re.compile(r"(?:SECCI[OÓ]N\s*14|14[\.\)]\s*Informaci[oó]n.*transporte)", re.IGNORECASE)),
    (15, re.compile(r"(?:SECCI[OÓ]N\s*15|15[\.\)]\s*Informaci[oó]n\s*reglamentaria)", re.IGNORECASE)),
    (16, re.compile(r"(?:SECCI[OÓ]N\s*16|16[\.\)]\s*Otra\s*informaci[oó]n)", re.IGNORECASE)),
]

_RE_PH = re.compile(r"pH\s*[:\-=]\s*([\d.,]+)", re.IGNORECASE)
_RE_PUNTO_INFLAMACION = re.compile(r"[Pp]unto\s*de\s*inflamaci[oó]n\s*[:\-=]\s*([\d.,]+\s*[°ºC]*)", re.IGNORECASE)
_RE_DENSIDAD = re.compile(r"[Dd]ensidad\s*(?:relativa)?\s*[:\-=]\s*([\d.,]+)", re.IGNORECASE)
_RE_PUNTO_EBULLICION = re.compile(r"[Pp]unto\s*de\s*ebullici[oó]n\s*[:\-=]\s*([\d.,]+\s*[°ºC]*)", re.IGNORECASE)
_RE_VISCOSIDAD = re.compile(r"[Vv]iscosidad\s*[:\-=]\s*([\d.,]+\s*\w*)", re.IGNORECASE)

_RE_DL50_ORAL = re.compile(r"DL50\s*(?:oral)?\s*[:\-=]\s*([\d.,]+\s*mg/kg)", re.IGNORECASE)
_RE_CL50_INHALACION = re.compile(r"CL50\s*(?:inhalaci[oó]n)?\s*[:\-=]\s*([\d.,]+\s*mg/[Ll])", re.IGNORECASE)


def _extraer_secciones(texto):
    """Divide el texto en secciones detectando encabezados."""
    lineas = texto.split("\n")
    secciones = {}
    seccion_actual = None
    buffer = []

    for linea in lineas:
        encontrada = None
        for num, patron in _SECCION_PATRONES:
            if patron.search(linea):
                encontrada = num
                break
        if encontrada is not None:
            if seccion_actual is not None:
                secciones[seccion_actual] = "\n".join(buffer)
            seccion_actual = encontrada
            buffer = [linea]
        elif seccion_actual is not None:
            buffer.append(linea)

    if seccion_actual is not None:
        secciones[seccion_actual] = "\n".join(buffer)

    return secciones


def parsear_sds_md(ruta_archivo):
    """Parsea un archivo .md de SDS y extrae datos estructurados.

    Returns:
        dict con claves: cas, frases_h, frases_p, secciones, propiedades_fisicas, toxicologia, epi
    """
    if not os.path.exists(ruta_archivo):
        return {}

    with open(ruta_archivo, "r", encoding="utf-8", errors="replace") as f:
        texto = f.read()

    cas_encontrados = list(set(_RE_CAS.findall(texto)))
    frases_h = sorted(set(_RE_FRASE_H.findall(texto)))
    frases_p = sorted(set(_RE_FRASE_P.findall(texto)))

    secciones = _extraer_secciones(texto)

    # Propiedades fisicas (Seccion 9)
    propiedades = {}
    texto_s9 = secciones.get(9, texto)
    m = _RE_PH.search(texto_s9)
    if m:
        propiedades["pH"] = m.group(1)
    m = _RE_PUNTO_INFLAMACION.search(texto_s9)
    if m:
        propiedades["punto_inflamacion"] = m.group(1)
    m = _RE_DENSIDAD.search(texto_s9)
    if m:
        propiedades["densidad"] = m.group(1)
    m = _RE_PUNTO_EBULLICION.search(texto_s9)
    if m:
        propiedades["punto_ebullicion"] = m.group(1)
    m = _RE_VISCOSIDAD.search(texto_s9)
    if m:
        propiedades["viscosidad"] = m.group(1)

    # Toxicologia (Seccion 11)
    toxicologia = {}
    texto_s11 = secciones.get(11, texto)
    m = _RE_DL50_ORAL.search(texto_s11)
    if m:
        toxicologia["DL50_oral"] = m.group(1)
    m = _RE_CL50_INHALACION.search(texto_s11)
    if m:
        toxicologia["CL50_inhalacion"] = m.group(1)

    # EPI (Seccion 8)
    epi = secciones.get(8, "")

    return {
        "cas": cas_encontrados,
        "frases_h": frases_h,
        "frases_p": frases_p,
        "secciones": {str(k): v for k, v in secciones.items()},
        "propiedades_fisicas": propiedades,
        "toxicologia": toxicologia,
        "epi": epi,
    }


# ---------------------------------------------------------------------------
# Consultas a fuentes externas
# ---------------------------------------------------------------------------

def _buscar_cache(cas, fuente=None):
    """Busca en cache_api por numero CAS."""
    query = CacheApi.query.filter_by(numero_cas=cas)
    if fuente:
        query = query.filter_by(fuente=fuente)
    registro = query.order_by(CacheApi.fecha_consulta.desc()).first()
    if registro:
        return json.loads(registro.datos_json)
    return None


def _guardar_cache(cas, fuente, datos):
    """Guarda datos en la tabla cache_api."""
    entrada = CacheApi(
        numero_cas=cas,
        fuente=fuente,
        datos_json=json.dumps(datos, ensure_ascii=False),
        fecha_consulta=datetime.now(timezone.utc),
    )
    db.session.add(entrada)
    db.session.commit()


def consultar_pubchem(cas):
    """Consulta la API REST de PubChem por numero CAS."""
    try:
        url_cid = (
            f"https://pubchem.ncbi.nlm.nih.gov/rest/pug/compound/name/{cas}/cids/JSON"
        )
        resp = http_requests.get(url_cid, timeout=10)
        if resp.status_code != 200:
            return None
        data = resp.json()
        cids = data.get("IdentifierList", {}).get("CID", [])
        if not cids:
            return None
        cid = cids[0]

        url_props = (
            f"https://pubchem.ncbi.nlm.nih.gov/rest/pug/compound/cid/{cid}"
            f"/property/MolecularWeight,MolecularFormula,IUPACName,"
            f"ExactMass,XLogP/JSON"
        )
        resp2 = http_requests.get(url_props, timeout=10)
        if resp2.status_code != 200:
            return None
        props = resp2.json().get("PropertyTable", {}).get("Properties", [{}])[0]

        resultado = {
            "cid": cid,
            "peso_molecular": props.get("MolecularWeight"),
            "formula": props.get("MolecularFormula"),
            "nombre_iupac": props.get("IUPACName"),
            "masa_exacta": props.get("ExactMass"),
            "logP": props.get("XLogP"),
            "fuente": "pubchem",
        }
        return resultado
    except Exception:
        return None


def consultar_wikipedia(cas):
    """Consulta la API de Wikipedia en espanol para obtener datos de la sustancia."""
    try:
        url = "https://es.wikipedia.org/w/api.php"
        params = {
            "action": "query",
            "list": "search",
            "srsearch": cas,
            "format": "json",
            "srlimit": 1,
        }
        resp = http_requests.get(url, params=params, timeout=10)
        if resp.status_code != 200:
            return None
        data = resp.json()
        results = data.get("query", {}).get("search", [])
        if not results:
            return None

        titulo = results[0]["title"]
        params_ext = {
            "action": "query",
            "titles": titulo,
            "prop": "extracts",
            "exintro": True,
            "explaintext": True,
            "format": "json",
        }
        resp2 = http_requests.get(url, params=params_ext, timeout=10)
        if resp2.status_code != 200:
            return None
        pages = resp2.json().get("query", {}).get("pages", {})
        for page_id, page in pages.items():
            if page_id == "-1":
                return None
            extracto = page.get("extract", "")
            return {
                "titulo": titulo,
                "extracto": extracto[:2000],
                "fuente": "wikipedia",
            }
    except Exception:
        return None
    return None


def obtener_datos_componente(cas):
    """Orquesta la busqueda de datos para un componente dado su numero CAS.

    Orden de prioridad:
    1. Cache local
    2. PubChem API
    3. Wikipedia API
    4. CSV descargables (si existen en BD)
    """
    if not cas:
        return {}

    # 1. Cache
    datos_cache = _buscar_cache(cas)
    if datos_cache:
        return datos_cache

    # 2. PubChem
    datos_pubchem = consultar_pubchem(cas)
    if datos_pubchem:
        _guardar_cache(cas, "pubchem", datos_pubchem)
        return datos_pubchem

    # 3. Wikipedia
    datos_wiki = consultar_wikipedia(cas)
    if datos_wiki:
        _guardar_cache(cas, "wikipedia", datos_wiki)
        return datos_wiki

    # 4. CSV descargables (busqueda en BD si se han importado)
    for fuente_csv in ["echa_csv", "gestis_csv", "niosh_csv"]:
        datos_csv = _buscar_cache(cas, fuente=fuente_csv)
        if datos_csv:
            return datos_csv

    return {}
