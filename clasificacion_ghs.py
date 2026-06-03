"""Motor de clasificacion GHS para mezclas quimicas.

Implementa:
- Metodo de aditividad para toxicidad aguda (formula ATE)
- Metodo de suma de fracciones para peligro acuatico
- Clasificacion por mayor peligro para clases no aditivas
- Asignacion de pictogramas GHS
"""

import csv
import json
import os
import re

from config import Config
from database import db
from models import CategoriaUmbral, ClasePeligro, FraseH


def _cargar_frases_h_dict():
    """Devuelve dict {codigo_h: {texto_es, clase_peligro, categoria, pictograma}}."""
    frases = FraseH.query.all()
    resultado = {}
    for f in frases:
        resultado[f.codigo_h] = {
            "texto_es": f.texto_es,
            "clase_peligro": f.clase_peligro,
            "categoria": f.categoria,
            "pictograma": f.pictograma_codigo,
        }
    return resultado


def _cargar_umbrales():
    """Devuelve dict {clase_peligro: [{categoria, umbral, unidad}]}."""
    umbrales = CategoriaUmbral.query.all()
    resultado = {}
    for u in umbrales:
        clase = ClasePeligro.query.get(u.clase_peligro_id)
        if not clase:
            continue
        nombre = clase.nombre_clase
        if nombre not in resultado:
            resultado[nombre] = []
        resultado[nombre].append({
            "categoria": u.categoria,
            "umbral": u.umbral_generico,
            "unidad": u.unidad,
            "metodo": clase.metodo_calculo,
        })
    return resultado


def calcular_ate_mezcla(componentes_con_ate, via="oral"):
    """Calcula el ATE de la mezcla usando formula aditiva.

    componentes_con_ate: lista de dicts {porcentaje, ate_valor}
    Retorna ATE de la mezcla o None si no hay datos.

    Formula: 100 / sum(Ci / ATEi)
    donde Ci es el porcentaje del componente i y ATEi es su valor ATE.
    """
    suma = 0.0
    for comp in componentes_con_ate:
        ate = comp.get("ate_valor")
        pct = comp.get("porcentaje", 0)
        if ate and ate > 0 and pct > 0:
            suma += pct / ate

    if suma <= 0:
        return None

    return 100.0 / suma


def clasificar_toxicidad_aguda(ate_mezcla, via="oral"):
    """Clasifica la toxicidad aguda de la mezcla segun su ATE.

    Retorna dict con categoria, codigo_h, pictograma o None.
    """
    if ate_mezcla is None:
        return None

    # Umbrales segun GHS para toxicidad aguda oral (mg/kg)
    umbrales_oral = [
        (5, "1", "H300", "GHS06"),
        (50, "2", "H300", "GHS06"),
        (300, "3", "H301", "GHS06"),
        (2000, "4", "H302", "GHS07"),
        (5000, "5", "H303", "GHS07"),
    ]

    umbrales_cutanea = [
        (50, "1", "H310", "GHS06"),
        (200, "2", "H310", "GHS06"),
        (1000, "3", "H311", "GHS06"),
        (2000, "4", "H312", "GHS07"),
    ]

    umbrales_inhalacion = [
        (0.5, "1", "H330", "GHS06"),
        (2.0, "2", "H330", "GHS06"),
        (10, "3", "H331", "GHS06"),
        (20, "4", "H332", "GHS07"),
    ]

    if via == "oral":
        tabla = umbrales_oral
    elif via == "cutanea":
        tabla = umbrales_cutanea
    else:
        tabla = umbrales_inhalacion

    for umbral, cat, codigo_h, picto in tabla:
        if ate_mezcla <= umbral:
            return {
                "categoria": cat,
                "codigo_h": codigo_h,
                "pictograma": picto,
                "ate_mezcla": round(ate_mezcla, 2),
                "via": via,
            }

    return None


def clasificar_peligro_acuatico(componentes_con_datos):
    """Clasifica peligro acuatico usando metodo de suma de fracciones.

    componentes_con_datos: lista de dicts {porcentaje, codigos_h: []}
    Retorna lista de clasificaciones acuaticas.
    """
    # Factores de multiplicacion segun codigo H acuatico
    factores = {
        "H400": {"M": 1, "tipo": "agudo"},
        "H410": {"M": 10, "tipo": "cronico_1"},
        "H411": {"M": 1, "tipo": "cronico_2"},
        "H412": {"M": 0.1, "tipo": "cronico_3"},
        "H413": {"M": 0.01, "tipo": "cronico_4"},
    }

    suma_agudo = 0.0
    suma_cronico_1 = 0.0
    suma_cronico_2 = 0.0
    suma_cronico_3 = 0.0

    for comp in componentes_con_datos:
        pct = comp.get("porcentaje", 0)
        codigos = comp.get("codigos_h", [])
        for cod in codigos:
            if cod in factores:
                info = factores[cod]
                if info["tipo"] == "agudo":
                    suma_agudo += pct * info["M"]
                elif info["tipo"] == "cronico_1":
                    suma_cronico_1 += pct * info["M"]
                elif info["tipo"] == "cronico_2":
                    suma_cronico_2 += pct * info["M"]
                elif info["tipo"] == "cronico_3":
                    suma_cronico_3 += pct * info["M"]

    resultados = []
    if suma_agudo >= 25:
        resultados.append({"codigo_h": "H400", "pictograma": "GHS09", "tipo": "Peligro acuatico agudo 1"})
    if suma_cronico_1 >= 25:
        resultados.append({"codigo_h": "H410", "pictograma": "GHS09", "tipo": "Peligro acuatico cronico 1"})
    elif suma_cronico_2 >= 25:
        resultados.append({"codigo_h": "H411", "pictograma": "GHS09", "tipo": "Peligro acuatico cronico 2"})
    elif suma_cronico_3 >= 25:
        resultados.append({"codigo_h": "H412", "pictograma": None, "tipo": "Peligro acuatico cronico 3"})

    return resultados


def clasificar_por_mayor_peligro(componentes_con_datos, codigos_referencia):
    """Para clases no aditivas: la mezcla hereda la clasificacion del
    componente mas peligroso que supere el umbral de concentracion.

    componentes_con_datos: [{porcentaje, codigos_h: []}]
    codigos_referencia: set de codigos H a buscar (ej: {"H317"})

    Retorna lista de codigos H que aplican a la mezcla.
    """
    umbrales = _cargar_umbrales()
    codigos_resultado = []

    for comp in componentes_con_datos:
        pct = comp.get("porcentaje", 0)
        for codigo_h in comp.get("codigos_h", []):
            if codigo_h not in codigos_referencia:
                continue
            # Buscar si supera umbral
            info_h = _cargar_frases_h_dict().get(codigo_h, {})
            clase = info_h.get("clase_peligro", "")
            if clase in umbrales:
                for u in umbrales[clase]:
                    if pct >= u["umbral"]:
                        if codigo_h not in codigos_resultado:
                            codigos_resultado.append(codigo_h)
                        break
            else:
                # Si no hay umbral especifico, considerar presente si > 1%
                if pct >= 1.0 and codigo_h not in codigos_resultado:
                    codigos_resultado.append(codigo_h)

    return codigos_resultado


def clasificar_mezcla(componentes):
    """Clasificacion completa GHS de una mezcla.

    componentes: lista de dicts con keys:
        - nombre_inci, numero_cas, porcentaje, codigos_h, ate_oral, ate_cutanea, ate_inhalacion

    Retorna dict con:
        - codigos_h: lista de codigos H de la mezcla
        - pictogramas: lista de codigos GHS
        - clasificaciones: lista detallada
        - palabra_advertencia: 'Peligro' o 'Atencion'
    """
    frases_h_dict = _cargar_frases_h_dict()

    codigos_h_mezcla = set()
    pictogramas = set()
    clasificaciones = []

    # 1. Toxicidad aguda (metodo aditivo)
    for via in ["oral", "cutanea", "inhalacion"]:
        comps_ate = []
        for c in componentes:
            ate_key = f"ate_{via}"
            ate_val = c.get(ate_key)
            if ate_val:
                try:
                    comps_ate.append({"porcentaje": c["porcentaje"], "ate_valor": float(ate_val)})
                except (ValueError, TypeError):
                    pass
        if comps_ate:
            ate_mezcla = calcular_ate_mezcla(comps_ate, via)
            clasif = clasificar_toxicidad_aguda(ate_mezcla, via)
            if clasif:
                codigos_h_mezcla.add(clasif["codigo_h"])
                if clasif["pictograma"]:
                    pictogramas.add(clasif["pictograma"])
                clasificaciones.append({
                    "tipo": f"Toxicidad aguda ({via})",
                    "categoria": clasif["categoria"],
                    "codigo_h": clasif["codigo_h"],
                    "ate_mezcla": clasif["ate_mezcla"],
                })

    # 2. Peligro acuatico (metodo suma de fracciones)
    clasifs_acuaticas = clasificar_peligro_acuatico(componentes)
    for ca in clasifs_acuaticas:
        codigos_h_mezcla.add(ca["codigo_h"])
        if ca["pictograma"]:
            pictogramas.add(ca["pictograma"])
        clasificaciones.append({
            "tipo": ca["tipo"],
            "codigo_h": ca["codigo_h"],
        })

    # 3. Clases no aditivas (herencia por mayor peligro y umbral)
    codigos_no_aditivos = {
        "H314", "H315", "H317", "H318", "H319",
        "H334", "H335", "H336",
        "H340", "H341", "H350", "H351",
        "H360", "H361", "H362",
        "H370", "H371", "H372", "H373",
        "H304",
    }
    heredados = clasificar_por_mayor_peligro(componentes, codigos_no_aditivos)
    for codigo_h in heredados:
        codigos_h_mezcla.add(codigo_h)
        info = frases_h_dict.get(codigo_h, {})
        if info.get("pictograma"):
            pictogramas.add(info["pictograma"])
        clasificaciones.append({
            "tipo": f"Herencia ({info.get('clase_peligro', 'Desconocida')})",
            "codigo_h": codigo_h,
        })

    # 4. Codigos H directos de componentes con alta concentracion
    # (para clases fisicas como inflamables)
    codigos_fisicos = {
        "H220", "H221", "H222", "H223", "H224", "H225", "H226", "H228",
        "H240", "H241", "H242", "H250", "H251", "H252", "H260", "H261",
        "H270", "H271", "H272", "H280", "H281", "H290",
    }
    for c in componentes:
        pct = c.get("porcentaje", 0)
        for codigo_h in c.get("codigos_h", []):
            if codigo_h in codigos_fisicos and pct >= 1.0:
                codigos_h_mezcla.add(codigo_h)
                info = frases_h_dict.get(codigo_h, {})
                if info.get("pictograma"):
                    pictogramas.add(info["pictograma"])

    # Determinar palabra de advertencia
    codigos_peligro = {"H200", "H201", "H202", "H203", "H204", "H205",
                       "H220", "H224", "H240", "H250", "H260",
                       "H270", "H271", "H280", "H281",
                       "H300", "H310", "H314", "H318", "H330",
                       "H340", "H350", "H360", "H370", "H372",
                       "H304"}
    palabra = "Peligro" if codigos_h_mezcla & codigos_peligro else "Atencion"
    if not codigos_h_mezcla:
        palabra = ""

    codigos_ordenados = sorted(codigos_h_mezcla)

    # Construir textos de frases H
    textos_h = []
    for cod in codigos_ordenados:
        info = frases_h_dict.get(cod, {})
        textos_h.append(f"{cod}: {info.get('texto_es', 'Sin descripcion')}")

    return {
        "codigos_h": codigos_ordenados,
        "textos_h": textos_h,
        "pictogramas": sorted(pictogramas),
        "clasificaciones": clasificaciones,
        "palabra_advertencia": palabra,
    }
