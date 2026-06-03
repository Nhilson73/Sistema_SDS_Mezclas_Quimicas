"""Exportador de FDS a PDF (WeasyPrint), JSON y CSV."""

import csv
import io
import json
import os
from datetime import datetime, timezone

from config import Config


def exportar_json(fds_secciones, clasificacion, mezcla_data):
    """Exporta la FDS completa a formato JSON."""
    return json.dumps({
        "mezcla": mezcla_data,
        "clasificacion": clasificacion,
        "secciones": fds_secciones,
        "fecha_exportacion": datetime.now(timezone.utc).isoformat(),
    }, ensure_ascii=False, indent=2)


def exportar_csv(fds_secciones, clasificacion, mezcla_data):
    """Exporta la FDS a formato CSV (tabla plana para auditorias)."""
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Seccion", "Titulo", "Contenido"])

    for num in sorted(fds_secciones.keys(), key=lambda x: int(x)):
        sec = fds_secciones[num]
        titulo = sec.get("titulo", f"Seccion {num}")
        contenido = sec.get("contenido", "")
        # Limpiar saltos de linea para CSV
        contenido_limpio = contenido.replace("\n", " | ")
        writer.writerow([num, titulo, contenido_limpio])

    # Agregar fila de clasificacion
    writer.writerow([])
    writer.writerow(["Clasificacion GHS"])
    writer.writerow(["Codigos H", ", ".join(clasificacion.get("codigos_h", []))])
    writer.writerow(["Pictogramas", ", ".join(clasificacion.get("pictogramas", []))])
    writer.writerow(["Palabra de advertencia", clasificacion.get("palabra_advertencia", "")])

    return output.getvalue()


def _generar_html_fds(fds_secciones, clasificacion, mezcla_data):
    """Genera HTML completo de la FDS para renderizar a PDF."""
    nombre = mezcla_data.get("nombre_producto", "Sin nombre")
    pictogramas = clasificacion.get("pictogramas", [])
    pictos_dir = os.path.join(Config.BASE_DIR, "static", "pictogramas")

    pictos_html = ""
    for p in pictogramas:
        svg_path = os.path.join(pictos_dir, f"{p}.svg")
        if os.path.exists(svg_path):
            with open(svg_path, "r") as f:
                pictos_html += f'<div class="pictograma">{f.read()}</div>'

    secciones_html = ""
    for num in sorted(fds_secciones.keys(), key=lambda x: int(x)):
        sec = fds_secciones[num]
        titulo = sec.get("titulo", f"Seccion {num}")
        contenido = sec.get("contenido", "").replace("\n", "<br>")
        secciones_html += f"""
        <div class="seccion">
            <h2>{titulo}</h2>
            <div class="contenido">{contenido}</div>
        </div>
        """

    html = f"""<!DOCTYPE html>
<html lang="es">
<head>
    <meta charset="UTF-8">
    <title>FDS - {nombre}</title>
    <style>
        @page {{
            size: A4;
            margin: 2cm;
            @top-center {{
                content: "FICHA DE DATOS DE SEGURIDAD - {nombre}";
                font-size: 8pt;
                color: #666;
            }}
            @bottom-center {{
                content: "Pagina " counter(page) " de " counter(pages);
                font-size: 8pt;
                color: #666;
            }}
        }}
        body {{
            font-family: Arial, Helvetica, sans-serif;
            font-size: 10pt;
            line-height: 1.4;
            color: #333;
        }}
        .header {{
            text-align: center;
            border-bottom: 2px solid #c00;
            padding-bottom: 10px;
            margin-bottom: 20px;
        }}
        .header h1 {{
            color: #c00;
            font-size: 16pt;
            margin: 0;
        }}
        .pictogramas {{
            display: flex;
            justify-content: center;
            gap: 10px;
            margin: 10px 0;
        }}
        .pictograma {{
            width: 60px;
            height: 60px;
        }}
        .pictograma svg {{
            width: 100%;
            height: 100%;
        }}
        .seccion {{
            margin-bottom: 15px;
            page-break-inside: avoid;
        }}
        .seccion h2 {{
            color: #c00;
            font-size: 11pt;
            border-bottom: 1px solid #ddd;
            padding-bottom: 3px;
            margin-top: 15px;
            margin-bottom: 5px;
        }}
        .contenido {{
            margin-left: 10px;
        }}
    </style>
</head>
<body>
    <div class="header">
        <h1>FICHA DE DATOS DE SEGURIDAD</h1>
        <h2>{nombre}</h2>
        <div class="pictogramas">{pictos_html}</div>
    </div>
    {secciones_html}
</body>
</html>"""
    return html


def exportar_pdf(fds_secciones, clasificacion, mezcla_data, ruta_salida=None):
    """Exporta la FDS a PDF usando WeasyPrint.

    Args:
        fds_secciones: dict con secciones
        clasificacion: dict con clasificacion GHS
        mezcla_data: dict con datos de la mezcla
        ruta_salida: ruta del archivo PDF de salida (opcional)

    Returns:
        bytes del PDF si no se especifica ruta, o la ruta del archivo creado
    """
    try:
        from weasyprint import HTML
    except ImportError:
        raise RuntimeError(
            "WeasyPrint no esta instalado. Ejecute: "
            "sudo apt install -y libpango-1.0-0 libcairo2 libgdk-pixbuf2.0-0 libffi-dev shared-mime-info && "
            "pip install weasyprint"
        )

    html = _generar_html_fds(fds_secciones, clasificacion, mezcla_data)

    if ruta_salida:
        os.makedirs(os.path.dirname(ruta_salida), exist_ok=True)
        HTML(string=html).write_pdf(ruta_salida)
        return ruta_salida
    else:
        return HTML(string=html).write_pdf()
