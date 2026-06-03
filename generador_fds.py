"""Generador de Fichas de Datos de Seguridad (FDS) - 16 secciones SGA/GHS.

Construye el texto completo de la FDS usando datos de la mezcla,
ensayos de laboratorio y clasificacion GHS.
Prioriza ensayos reales si existen.
"""

import json
from datetime import datetime, timezone


def _val_ensayo(ensayos, nombre_parametro, fallback="No disponible"):
    """Busca un valor de ensayo; si existe retorna el valor, si no el fallback."""
    for e in ensayos:
        if e["nombre_parametro"].lower() == nombre_parametro.lower():
            valor = e["valor"]
            if e.get("unidad"):
                valor += f" {e['unidad']}"
            return valor
    return fallback


def _frases_h_texto(clasificacion):
    """Construye texto de frases H."""
    textos = clasificacion.get("textos_h", [])
    if not textos:
        return "No clasificado como peligroso."
    return "\n".join(f"- {t}" for t in textos)


def _pictogramas_lista(clasificacion):
    """Retorna lista de pictogramas aplicables."""
    return clasificacion.get("pictogramas", [])


def generar_fds(mezcla_data, componentes, ensayos, clasificacion, info_empresa=None):
    """Genera las 16 secciones de la FDS.

    Args:
        mezcla_data: dict con nombre_producto, lote, fecha_creacion
        componentes: lista de dicts con nombre_inci, numero_cas, porcentaje, es_csp
        ensayos: lista de dicts con nombre_parametro, valor, unidad
        clasificacion: dict resultado de clasificar_mezcla()
        info_empresa: dict opcional con nombre, direccion, telefono, email

    Returns:
        dict con secciones 1-16
    """
    if info_empresa is None:
        info_empresa = {
            "nombre": "[Nombre de la empresa]",
            "direccion": "[Direccion de la empresa]",
            "telefono": "[Telefono de emergencia]",
            "email": "[Email de contacto]",
            "telefono_emergencia": "[Telefono de emergencias 24h]",
        }

    nombre = mezcla_data.get("nombre_producto", "Sin nombre")
    lote = mezcla_data.get("lote", "N/A")
    fecha = mezcla_data.get("fecha_creacion", datetime.now(timezone.utc).strftime("%Y-%m-%d"))
    if hasattr(fecha, "strftime"):
        fecha = fecha.strftime("%Y-%m-%d")

    palabra_adv = clasificacion.get("palabra_advertencia", "")
    codigos_h = clasificacion.get("codigos_h", [])
    textos_h = clasificacion.get("textos_h", [])
    pictogramas = clasificacion.get("pictogramas", [])

    # Construir tabla de componentes
    tabla_comp = []
    for c in componentes:
        pct_str = f"{c['porcentaje']:.1f}%" if c.get("porcentaje") else "c.s.p."
        tabla_comp.append(
            f"- {c['nombre_inci']} (CAS: {c.get('numero_cas', 'N/A')}) - {pct_str}"
        )
    comp_texto = "\n".join(tabla_comp) if tabla_comp else "No especificados."

    # Construir lista de codigos H y P
    frases_h_texto = _frases_h_texto(clasificacion)
    pictos_texto = ", ".join(pictogramas) if pictogramas else "Ninguno"

    secciones = {}

    # SECCION 1: Identificacion de la sustancia/mezcla y de la empresa
    secciones["1"] = {
        "titulo": "SECCION 1: Identificacion de la sustancia o la mezcla y de la sociedad o la empresa",
        "contenido": (
            f"1.1 Identificador del producto\n"
            f"Nombre del producto: {nombre}\n"
            f"Lote: {lote}\n"
            f"Fecha de elaboracion: {fecha}\n"
            f"Tipo: Mezcla\n\n"
            f"1.2 Usos pertinentes identificados\n"
            f"Uso: Producto cosmetico / de aseo / industrial (segun formulacion)\n\n"
            f"1.3 Datos del proveedor de la ficha de datos de seguridad\n"
            f"Empresa: {info_empresa['nombre']}\n"
            f"Direccion: {info_empresa['direccion']}\n"
            f"Telefono: {info_empresa['telefono']}\n"
            f"Email: {info_empresa['email']}\n\n"
            f"1.4 Telefono de emergencia\n"
            f"{info_empresa['telefono_emergencia']}"
        ),
    }

    # SECCION 2: Identificacion de los peligros
    secciones["2"] = {
        "titulo": "SECCION 2: Identificacion de los peligros",
        "contenido": (
            f"2.1 Clasificacion de la sustancia o de la mezcla\n"
            f"Clasificacion segun el SGA/GHS:\n"
            f"{frases_h_texto}\n\n"
            f"2.2 Elementos de la etiqueta\n"
            f"Pictogramas: {pictos_texto}\n"
            f"Palabra de advertencia: {palabra_adv if palabra_adv else 'Sin palabra de advertencia'}\n"
            f"Indicaciones de peligro (H):\n{frases_h_texto}\n\n"
            f"2.3 Otros peligros\n"
            f"No se conocen otros peligros adicionales."
        ),
    }

    # SECCION 3: Composicion/informacion sobre los componentes
    secciones["3"] = {
        "titulo": "SECCION 3: Composicion/informacion sobre los componentes",
        "contenido": (
            f"Tipo: Mezcla\n\n"
            f"Componentes:\n{comp_texto}"
        ),
    }

    # SECCION 4: Primeros auxilios
    primeros_aux = _generar_seccion_4(codigos_h)
    secciones["4"] = {
        "titulo": "SECCION 4: Primeros auxilios",
        "contenido": primeros_aux,
    }

    # SECCION 5: Medidas de lucha contra incendios
    secciones["5"] = {
        "titulo": "SECCION 5: Medidas de lucha contra incendios",
        "contenido": (
            "5.1 Medios de extincion\n"
            "Medios de extincion apropiados: Espuma resistente al alcohol, CO2, polvo seco, agua pulverizada.\n"
            "Medios de extincion no apropiados: Chorro directo de agua (puede propagar el producto).\n\n"
            "5.2 Peligros especificos derivados de la sustancia o la mezcla\n"
            f"{'Producto inflamable. Vapores pueden formar mezclas explosivas con el aire.' if any(c in codigos_h for c in ['H224', 'H225', 'H226']) else 'No se esperan peligros especiales de incendio.'}\n\n"
            "5.3 Recomendaciones para el personal de lucha contra incendios\n"
            "Utilizar equipo de respiracion autonomo y traje de proteccion completo."
        ),
    }

    # SECCION 6: Medidas en caso de vertido accidental
    secciones["6"] = {
        "titulo": "SECCION 6: Medidas en caso de vertido accidental",
        "contenido": (
            "6.1 Precauciones personales, equipos de proteccion y procedimientos de emergencia\n"
            "Utilizar equipo de proteccion individual (ver Seccion 8). "
            "Evacuar el area si es necesario. Ventilar la zona.\n\n"
            "6.2 Precauciones relativas al medio ambiente\n"
            f"{'Evitar que el producto entre en desagues, cursos de agua o el suelo. Producto toxico para organismos acuaticos.' if any(c in codigos_h for c in ['H400', 'H410', 'H411']) else 'Evitar que el producto entre en desagues o cursos de agua.'}\n\n"
            "6.3 Metodos y material de contencion y de limpieza\n"
            "Absorber con material inerte (arena, tierra, vermiculita). "
            "Recoger en recipientes adecuados para su eliminacion."
        ),
    }

    # SECCION 7: Manipulacion y almacenamiento
    seccion_7 = _generar_seccion_7(codigos_h)
    secciones["7"] = {
        "titulo": "SECCION 7: Manipulacion y almacenamiento",
        "contenido": seccion_7,
    }

    # SECCION 8: Controles de exposicion/proteccion individual
    seccion_8 = _generar_seccion_8(codigos_h)
    secciones["8"] = {
        "titulo": "SECCION 8: Controles de exposicion/proteccion individual",
        "contenido": seccion_8,
    }

    # SECCION 9: Propiedades fisicas y quimicas
    secciones["9"] = {
        "titulo": "SECCION 9: Propiedades fisicas y quimicas",
        "contenido": (
            f"Aspecto: {_val_ensayo(ensayos, 'Aspecto', _val_ensayo(ensayos, 'Color', 'No determinado'))}\n"
            f"Color: {_val_ensayo(ensayos, 'Color')}\n"
            f"Olor: {_val_ensayo(ensayos, 'Olor')}\n"
            f"pH: {_val_ensayo(ensayos, 'pH')}\n"
            f"Punto de fusion/congelacion: {_val_ensayo(ensayos, 'Punto de fusion')}\n"
            f"Punto de ebullicion: {_val_ensayo(ensayos, 'Punto de ebullicion')}\n"
            f"Punto de inflamacion: {_val_ensayo(ensayos, 'Punto de inflamacion')}\n"
            f"Velocidad de evaporacion: {_val_ensayo(ensayos, 'Velocidad de evaporacion')}\n"
            f"Inflamabilidad (solido, gas): {_val_ensayo(ensayos, 'Inflamabilidad')}\n"
            f"Presion de vapor: {_val_ensayo(ensayos, 'Presion de vapor')}\n"
            f"Densidad de vapor: {_val_ensayo(ensayos, 'Densidad de vapor')}\n"
            f"Densidad relativa: {_val_ensayo(ensayos, 'Densidad')}\n"
            f"Solubilidad: {_val_ensayo(ensayos, 'Solubilidad')}\n"
            f"Viscosidad: {_val_ensayo(ensayos, 'Viscosidad')}\n"
        ),
    }

    # SECCION 10: Estabilidad y reactividad
    secciones["10"] = {
        "titulo": "SECCION 10: Estabilidad y reactividad",
        "contenido": (
            "10.1 Reactividad\n"
            "No se dispone de datos especificos de reactividad.\n\n"
            "10.2 Estabilidad quimica\n"
            "Estable en condiciones normales de almacenamiento y manipulacion.\n\n"
            "10.3 Posibilidad de reacciones peligrosas\n"
            f"{'Puede reaccionar con oxidantes fuertes.' if any(c in codigos_h for c in ['H224', 'H225', 'H226']) else 'No se esperan reacciones peligrosas en condiciones normales.'}\n\n"
            "10.4 Condiciones que deben evitarse\n"
            f"{'Calor, llamas, chispas. Evitar fuentes de ignicion.' if any(c in codigos_h for c in ['H224', 'H225', 'H226', 'H228']) else 'Calor excesivo, luz solar directa.'}\n\n"
            "10.5 Materiales incompatibles\n"
            "Agentes oxidantes fuertes, acidos fuertes, bases fuertes.\n\n"
            "10.6 Productos de descomposicion peligrosos\n"
            "En caso de incendio puede generar CO, CO2 y humos toxicos."
        ),
    }

    # SECCION 11: Informacion toxicologica
    seccion_11 = _generar_seccion_11(clasificacion, ensayos, componentes)
    secciones["11"] = {
        "titulo": "SECCION 11: Informacion toxicologica",
        "contenido": seccion_11,
    }

    # SECCION 12: Informacion ecologica
    seccion_12 = _generar_seccion_12(codigos_h)
    secciones["12"] = {
        "titulo": "SECCION 12: Informacion ecologica",
        "contenido": seccion_12,
    }

    # SECCION 13: Consideraciones relativas a la eliminacion
    secciones["13"] = {
        "titulo": "SECCION 13: Consideraciones relativas a la eliminacion",
        "contenido": (
            "13.1 Metodos para el tratamiento de residuos\n"
            f"{'Producto clasificado como residuo peligroso. ' if any(c in codigos_h for c in ['H400', 'H410', 'H411']) else ''}"
            "Eliminar de acuerdo con la normativa local y nacional vigente.\n"
            "No verter en desagues ni cursos de agua.\n"
            "Entregar a un gestor autorizado de residuos.\n\n"
            "13.2 Envases\n"
            "Los envases contaminados deben tratarse como el propio residuo."
        ),
    }

    # SECCION 14: Informacion relativa al transporte
    secciones["14"] = {
        "titulo": "SECCION 14: Informacion relativa al transporte",
        "contenido": (
            "14.1 Numero ONU: No asignado (verificar segun clasificacion final)\n"
            f"14.2 Designacion oficial de transporte: {nombre}\n"
            "14.3 Clase(s) de peligro para el transporte: Consultar normativa local\n"
            "14.4 Grupo de embalaje: Consultar normativa local\n"
            "14.5 Peligros para el medio ambiente: "
            f"{'Si - Contaminante marino' if any(c in codigos_h for c in ['H400', 'H410']) else 'No determinado'}\n"
            "14.6 Precauciones particulares: Seguir las normativas de transporte vigentes."
        ),
    }

    # SECCION 15: Informacion reglamentaria
    secciones["15"] = {
        "titulo": "SECCION 15: Informacion reglamentaria",
        "contenido": (
            "15.1 Normativa y legislacion en materia de seguridad, salud y medio ambiente\n"
            "- Sistema Globalmente Armonizado (SGA/GHS) Rev. 9\n"
            "- Regulacion local aplicable segun jurisdiccion\n"
            "- Normativa cosmetica aplicable (si corresponde)\n\n"
            "15.2 Evaluacion de la seguridad quimica\n"
            "No se ha realizado una evaluacion de la seguridad quimica para esta mezcla."
        ),
    }

    # SECCION 16: Otra informacion
    secciones["16"] = {
        "titulo": "SECCION 16: Otra informacion",
        "contenido": (
            f"Fecha de elaboracion de la FDS: {datetime.now(timezone.utc).strftime('%Y-%m-%d')}\n"
            f"Version: {mezcla_data.get('version_actual', 1)}\n\n"
            "Abreviaturas:\n"
            "- SGA/GHS: Sistema Globalmente Armonizado de clasificacion y etiquetado de productos quimicos\n"
            "- FDS: Ficha de Datos de Seguridad\n"
            "- CAS: Chemical Abstracts Service\n"
            "- INCI: Nomenclatura Internacional de Ingredientes Cosmeticos\n"
            "- ATE: Estimacion de Toxicidad Aguda\n"
            "- EPI: Equipo de Proteccion Individual\n\n"
            "Esta FDS ha sido generada por el Sistema FSD 2026.\n"
            "La informacion contenida se basa en los datos disponibles a la fecha de elaboracion "
            "y no constituye garantia de las propiedades del producto."
        ),
    }

    return secciones


def _generar_seccion_4(codigos_h):
    """Genera Seccion 4: Primeros auxilios adaptada a los peligros."""
    partes = ["4.1 Descripcion de los primeros auxilios\n"]

    # Ingestion
    partes.append("En caso de ingestion:")
    if "H304" in codigos_h or "H314" in codigos_h:
        partes.append("NO provocar el vomito. Enjuagar la boca con agua. "
                      "Llamar inmediatamente a un centro de informacion toxicologica o a un medico.")
    elif any(c in codigos_h for c in ["H300", "H301"]):
        partes.append("Llamar inmediatamente a un centro de informacion toxicologica o a un medico. "
                      "Enjuagar la boca con agua.")
    elif "H302" in codigos_h:
        partes.append("Llamar a un centro de informacion toxicologica o a un medico si se siente mal. "
                      "Enjuagar la boca con agua.")
    else:
        partes.append("Enjuagar la boca con agua. Consultar a un medico si aparecen sintomas.")

    # Contacto cutaneo
    partes.append("\nEn caso de contacto con la piel:")
    if "H314" in codigos_h:
        partes.append("Quitar inmediatamente la ropa contaminada. Lavar con abundante agua durante al menos 15 minutos. "
                      "Llamar a un medico inmediatamente.")
    elif any(c in codigos_h for c in ["H310", "H311"]):
        partes.append("Quitar la ropa contaminada. Lavar con abundante agua y jabon. "
                      "Llamar a un centro de informacion toxicologica.")
    elif "H315" in codigos_h:
        partes.append("Lavar con abundante agua y jabon. Si persiste la irritacion, consultar a un medico.")
    else:
        partes.append("Lavar con agua y jabon. Consultar a un medico si aparecen sintomas.")

    # Contacto ocular
    partes.append("\nEn caso de contacto con los ojos:")
    if "H318" in codigos_h:
        partes.append("Lavar los ojos con agua limpia durante al menos 15 minutos. "
                      "Quitar las lentes de contacto si es posible. Consultar a un oftalmologo inmediatamente.")
    elif "H319" in codigos_h:
        partes.append("Aclarar los ojos con agua durante varios minutos. Quitar las lentes de contacto si es posible. "
                      "Si persiste la irritacion, consultar a un medico.")
    else:
        partes.append("Aclarar los ojos con agua durante varios minutos. Consultar a un medico si hay molestias.")

    # Inhalacion
    partes.append("\nEn caso de inhalacion:")
    if any(c in codigos_h for c in ["H330", "H331"]):
        partes.append("Transportar a la victima al aire fresco. Mantener en reposo. "
                      "Llamar inmediatamente a un centro de informacion toxicologica. "
                      "Si no respira, administrar respiracion artificial con proteccion respiratoria.")
    elif "H332" in codigos_h or "H334" in codigos_h:
        partes.append("Transportar al aire fresco. En caso de dificultad respiratoria, consultar a un medico.")
    else:
        partes.append("Transportar al aire fresco si hay sintomas. Consultar a un medico si persisten las molestias.")

    partes.append("\n4.2 Principales sintomas y efectos\n"
                  "Los sintomas dependen de la via y duracion de la exposicion. Consultar la Seccion 11.")
    partes.append("\n4.3 Indicacion de toda atencion medica y de los tratamientos especiales que deban dispensarse\n"
                  "Tratamiento sintomatico. No se conoce antidoto especifico.")

    return "\n".join(partes)


def _generar_seccion_7(codigos_h):
    """Genera Seccion 7: Manipulacion y almacenamiento."""
    partes = ["7.1 Precauciones para una manipulacion segura\n"]

    if any(c in codigos_h for c in ["H224", "H225", "H226"]):
        partes.append("Mantener alejado de fuentes de calor, chispas, llama abierta y superficies calientes. No fumar. "
                      "Eliminar fuentes de ignicion. Tomar medidas contra descargas electrostaticas.")
    if any(c in codigos_h for c in ["H228"]):
        partes.append("Evitar formacion de polvo. Mantener alejado de fuentes de ignicion.")
    if "H260" in codigos_h:
        partes.append("Evitar contacto con agua.")
    if "H270" in codigos_h:
        partes.append("Mantener alejado de materiales combustibles.")
    if any(c in codigos_h for c in ["H280", "H281"]):
        partes.append("Proteger de la luz solar. No exponer a temperaturas superiores a 50 C.")

    partes.append("Utilizar equipo de proteccion individual (ver Seccion 8). "
                  "Evitar el contacto con los ojos, la piel y la ropa.")

    partes.append("\n7.2 Condiciones de almacenamiento seguro\n"
                  "Almacenar en un lugar fresco y bien ventilado. "
                  "Mantener el recipiente cerrado hermeticamente. "
                  "Almacenar lejos de productos incompatibles (ver Seccion 10).")

    if any(c in codigos_h for c in ["H300", "H301", "H310", "H330", "H340", "H350", "H360"]):
        partes.append("Guardar bajo llave.")

    partes.append("\n7.3 Usos especificos finales\n"
                  "Consultar la ficha tecnica del producto para usos especificos.")

    return "\n".join(partes)


def _generar_seccion_8(codigos_h):
    """Genera Seccion 8: Controles de exposicion/proteccion individual."""
    partes = [
        "8.1 Parametros de control\n"
        "Consultar los limites de exposicion profesional nacionales aplicables.\n",
        "8.2 Controles de la exposicion\n"
    ]

    # Proteccion respiratoria
    if any(c in codigos_h for c in ["H300", "H310", "H330", "H331", "H334"]):
        partes.append("Proteccion respiratoria: Utilizar mascara con filtro adecuado "
                      "(tipo A para vapores organicos o P3 para particulas segun corresponda). "
                      "En caso de concentraciones elevadas, equipo de respiracion autonomo.")
    elif any(c in codigos_h for c in ["H332", "H335", "H336"]):
        partes.append("Proteccion respiratoria: Utilizar en areas bien ventiladas. "
                      "Si la ventilacion es insuficiente, utilizar mascara con filtro.")
    else:
        partes.append("Proteccion respiratoria: Normalmente no es necesaria si hay ventilacion adecuada.")

    # Proteccion de manos
    if "H314" in codigos_h:
        partes.append("Proteccion de las manos: Guantes resistentes a productos quimicos "
                      "(nitrilo, neopreno o equivalente). Tiempo de penetracion > 480 min.")
    elif any(c in codigos_h for c in ["H310", "H311", "H312", "H315", "H317"]):
        partes.append("Proteccion de las manos: Guantes de proteccion quimica "
                      "(nitrilo o equivalente).")
    else:
        partes.append("Proteccion de las manos: Guantes de proteccion adecuados al producto.")

    # Proteccion ocular
    if any(c in codigos_h for c in ["H318", "H314"]):
        partes.append("Proteccion de los ojos: Gafas de seguridad hermeticas o pantalla facial.")
    elif "H319" in codigos_h:
        partes.append("Proteccion de los ojos: Gafas de seguridad.")
    else:
        partes.append("Proteccion de los ojos: Gafas de proteccion si hay riesgo de salpicaduras.")

    # Proteccion cutanea
    partes.append("Proteccion cutanea: Ropa de proteccion adecuada. Delantal si hay riesgo de salpicaduras.")

    return "\n".join(partes)


def _generar_seccion_11(clasificacion, ensayos, componentes):
    """Genera Seccion 11: Informacion toxicologica."""
    codigos_h = clasificacion.get("codigos_h", [])
    clasificaciones = clasificacion.get("clasificaciones", [])

    partes = ["11.1 Informacion sobre los efectos toxicologicos\n"]

    # Toxicidad aguda
    partes.append("Toxicidad aguda:")
    ate_info = [c for c in clasificaciones if "Toxicidad aguda" in c.get("tipo", "")]
    if ate_info:
        for a in ate_info:
            partes.append(f"  - {a['tipo']}: Categoria {a['categoria']} "
                          f"({a['codigo_h']}) - ATE mezcla: {a.get('ate_mezcla', 'N/D')} mg/kg")
    else:
        partes.append("  No clasificado para toxicidad aguda basado en los datos disponibles.")

    # Corrosion/irritacion cutanea
    if "H314" in codigos_h:
        partes.append("\nCorrosion cutanea: Provoca quemaduras graves en la piel.")
    elif "H315" in codigos_h:
        partes.append("\nIrritacion cutanea: Provoca irritacion cutanea.")

    # Lesion ocular
    if "H318" in codigos_h:
        partes.append("Lesion ocular grave: Provoca lesiones oculares graves.")
    elif "H319" in codigos_h:
        partes.append("Irritacion ocular: Provoca irritacion ocular grave.")

    # Sensibilizacion
    if "H334" in codigos_h:
        partes.append("Sensibilizacion respiratoria: Puede provocar sintomas de alergia o asma.")
    if "H317" in codigos_h:
        partes.append("Sensibilizacion cutanea: Puede provocar una reaccion alergica en la piel.")

    # CMR
    if "H340" in codigos_h:
        partes.append("Mutagenicidad: Puede provocar defectos geneticos (mutageno categoria 1).")
    elif "H341" in codigos_h:
        partes.append("Mutagenicidad: Se sospecha que provoca defectos geneticos (mutageno categoria 2).")

    if "H350" in codigos_h:
        partes.append("Carcinogenicidad: Puede provocar cancer (cancerigeno categoria 1).")
    elif "H351" in codigos_h:
        partes.append("Carcinogenicidad: Se sospecha que provoca cancer (cancerigeno categoria 2).")

    if "H360" in codigos_h:
        partes.append("Toxicidad para la reproduccion: Puede perjudicar la fertilidad o al feto.")
    elif "H361" in codigos_h:
        partes.append("Toxicidad para la reproduccion: Se sospecha que perjudica la fertilidad o al feto.")

    # STOT
    if "H370" in codigos_h:
        partes.append("Toxicidad especifica en determinados organos (exposicion unica): "
                      "Provoca danos en los organos (organo diana especificado).")
    if "H372" in codigos_h:
        partes.append("Toxicidad especifica en determinados organos (exposicion repetida): "
                      "Provoca danos en los organos tras exposiciones prolongadas o repetidas.")

    return "\n".join(partes)


def _generar_seccion_12(codigos_h):
    """Genera Seccion 12: Informacion ecologica."""
    partes = ["12.1 Toxicidad\n"]

    if "H400" in codigos_h:
        partes.append("Toxicidad acuatica aguda: Muy toxico para los organismos acuaticos (Categoria 1).")
    if "H410" in codigos_h:
        partes.append("Toxicidad acuatica cronica: Muy toxico para los organismos acuaticos "
                      "con efectos nocivos duraderos (Categoria 1).")
    if "H411" in codigos_h:
        partes.append("Toxicidad acuatica cronica: Toxico para los organismos acuaticos "
                      "con efectos nocivos duraderos (Categoria 2).")
    if "H412" in codigos_h:
        partes.append("Nocivo para los organismos acuaticos con efectos nocivos duraderos (Categoria 3).")

    if not any(c in codigos_h for c in ["H400", "H410", "H411", "H412"]):
        partes.append("No se clasifica como peligroso para el medio acuatico basado en los datos disponibles.")

    partes.extend([
        "\n12.2 Persistencia y degradabilidad\n"
        "No se dispone de datos especificos.",
        "\n12.3 Potencial de bioacumulacion\n"
        "No se dispone de datos especificos.",
        "\n12.4 Movilidad en el suelo\n"
        "No se dispone de datos especificos.",
        "\n12.5 Resultados de la valoracion PBT y mPmB\n"
        "No se ha realizado esta valoracion.",
    ])

    if "H420" in codigos_h:
        partes.append("\n12.6 Otros efectos adversos\n"
                      "Peligroso para la capa de ozono.")
    else:
        partes.append("\n12.6 Otros efectos adversos\n"
                      "No se conocen.")

    return "\n".join(partes)
