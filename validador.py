"""Validador de coherencia interna de la FDS.

Dos tipos de reglas:
1. Reglas desde tabla correlacion_secciones_fds (genericas)
2. Reglas especificas para cosmeticos y productos de aseo
"""

import re

from models import CorrelacionSeccionFds


def validar_fds(fds_secciones, clasificacion, ensayos=None, componentes=None):
    """Valida la coherencia de una FDS generada.

    Args:
        fds_secciones: dict con secciones 1-16 (cada una tiene 'contenido')
        clasificacion: dict con codigos_h, pictogramas, etc.
        ensayos: lista de dicts con nombre_parametro, valor (opcional)
        componentes: lista de componentes con nombre_inci, porcentaje (opcional)

    Returns:
        dict con 'errores' y 'advertencias', cada uno lista de dicts
        {codigo_h, seccion, mensaje, nivel}
    """
    if ensayos is None:
        ensayos = []
    if componentes is None:
        componentes = []

    errores = []
    advertencias = []

    codigos_h = clasificacion.get("codigos_h", [])

    # 1. Reglas desde tabla de correlacion
    reglas = CorrelacionSeccionFds.query.all()
    for regla in reglas:
        if regla.codigo_h not in codigos_h:
            continue

        seccion_num = re.search(r"(\d+)", regla.seccion_fds)
        if not seccion_num:
            continue
        sec_key = seccion_num.group(1)

        contenido_seccion = fds_secciones.get(sec_key, {})
        if isinstance(contenido_seccion, dict):
            texto = contenido_seccion.get("contenido", "")
        else:
            texto = str(contenido_seccion)

        # Verificar si la regla de coherencia se cumple
        patron = regla.regla_coherencia.lower()
        if patron not in texto.lower():
            item = {
                "codigo_h": regla.codigo_h,
                "seccion": regla.seccion_fds,
                "mensaje": regla.mensaje_error,
                "nivel": regla.nivel,
                "regla": regla.regla_coherencia,
            }
            if regla.nivel == "error":
                errores.append(item)
            else:
                advertencias.append(item)

    # 2. Reglas especificas para cosmeticos
    reglas_cosmeticas = _validar_reglas_cosmeticas(
        codigos_h, ensayos, componentes
    )
    for r in reglas_cosmeticas:
        if r["nivel"] == "error":
            errores.append(r)
        else:
            advertencias.append(r)

    return {
        "errores": errores,
        "advertencias": advertencias,
        "total_errores": len(errores),
        "total_advertencias": len(advertencias),
        "puede_aprobar": len(errores) == 0,
    }


def _obtener_valor_ensayo(ensayos, parametro):
    """Busca valor numerico de un ensayo."""
    for e in ensayos:
        if e["nombre_parametro"].lower() == parametro.lower():
            try:
                val = e["valor"].replace(",", ".")
                return float(re.search(r"[\d.]+", val).group())
            except (ValueError, AttributeError):
                return None
    return None


def _componente_contiene_inci(componentes, nombres_inci):
    """Verifica si algun componente contiene alguno de los nombres INCI dados."""
    for c in componentes:
        nombre = c.get("nombre_inci", "").lower()
        for n in nombres_inci:
            if n.lower() in nombre:
                return True, c
    return False, None


def _validar_reglas_cosmeticas(codigos_h, ensayos, componentes):
    """Reglas especificas para cosmeticos y productos de aseo/hogar."""
    resultados = []

    # Regla 1: pH > 11.5 → debe tener H314 o H315
    ph = _obtener_valor_ensayo(ensayos, "pH")
    if ph is not None and ph > 11.5:
        if "H314" not in codigos_h and "H315" not in codigos_h:
            resultados.append({
                "codigo_h": "N/A",
                "seccion": "Regla cosmetica",
                "mensaje": (
                    f"pH de la mezcla es {ph} (> 11.5). "
                    "Debe tener codigo H314 (corrosivo) o al menos H315 (irritante)."
                ),
                "nivel": "error",
                "regla": "pH > 11.5 requiere H314/H315",
            })

    # Regla 2: pH < 4.0 o pH > 8.5 para cremas/lociones → advertencia
    if ph is not None and (ph < 4.0 or ph > 8.5):
        resultados.append({
            "codigo_h": "N/A",
            "seccion": "Regla cosmetica",
            "mensaje": (
                f"pH de la mezcla es {ph} (fuera del rango 4.0-8.5). "
                "Posible irritacion no declarada para productos de uso cutaneo."
            ),
            "nivel": "warning",
            "regla": "pH fuera de rango fisiologico",
        })

    # Regla 3: Filtros UV → debe tener H410 o H411
    filtros_uv = ["avobenzona", "octocrileno", "benzofenona", "oxibenzona",
                  "homosalato", "octinoxato", "octocrylene", "avobenzone"]
    tiene_filtro, comp_filtro = _componente_contiene_inci(componentes, filtros_uv)
    if tiene_filtro:
        if "H410" not in codigos_h and "H411" not in codigos_h:
            resultados.append({
                "codigo_h": "N/A",
                "seccion": "Regla cosmetica",
                "mensaje": (
                    f"El producto contiene filtro UV ({comp_filtro.get('nombre_inci', '')}). "
                    "Deberia tener H410 o H411 (toxicidad acuatica). Verificar clasificacion."
                ),
                "nivel": "warning",
                "regla": "Filtros UV requieren clasificacion acuatica",
            })

    # Regla 4: Aerosoles (propelentes) → deben tener GHS04 y H280/H281
    propelentes = ["butano", "propano", "isobutano", "dimethyl ether", "dimetilete"]
    tiene_propelente, comp_prop = _componente_contiene_inci(componentes, propelentes)
    if tiene_propelente:
        if "H280" not in codigos_h and "H281" not in codigos_h:
            resultados.append({
                "codigo_h": "N/A",
                "seccion": "Regla cosmetica",
                "mensaje": (
                    f"El producto contiene propelente ({comp_prop.get('nombre_inci', '')}). "
                    "Debe tener GHS04 (gas a presion) y H280/H281."
                ),
                "nivel": "error",
                "regla": "Aerosoles requieren H280/H281",
            })

    # Regla 5: Alcohol > 20% → inflamable H225/H226
    alcoholes = ["etanol", "ethanol", "isopropanol", "alcohol isopropilico",
                 "isopropyl alcohol", "alcohol etilico"]
    for c in componentes:
        nombre = c.get("nombre_inci", "").lower()
        pct = c.get("porcentaje", 0)
        if any(a in nombre for a in alcoholes) and pct and pct > 20:
            if "H225" not in codigos_h and "H226" not in codigos_h:
                resultados.append({
                    "codigo_h": "N/A",
                    "seccion": "Regla cosmetica",
                    "mensaje": (
                        f"El producto contiene {c.get('nombre_inci', '')} al {pct}% (> 20%). "
                        "Debe tener clasificacion de inflamable (H225/H226)."
                    ),
                    "nivel": "warning",
                    "regla": "Alcohol > 20% requiere clasificacion inflamable",
                })

    # Regla 6: Productos en polvo (talco) → advertencia polvo
    polvos = ["talco", "talc", "almidón", "starch", "silica"]
    tiene_polvo, comp_polvo = _componente_contiene_inci(componentes, polvos)
    if tiene_polvo:
        resultados.append({
            "codigo_h": "N/A",
            "seccion": "Regla cosmetica",
            "mensaje": (
                f"El producto contiene {comp_polvo.get('nombre_inci', '')} (polvo fino). "
                "La Seccion 7 debe advertir sobre evitar la formacion de polvo."
            ),
            "nivel": "warning",
            "regla": "Productos en polvo requieren advertencia",
        })

    return resultados
