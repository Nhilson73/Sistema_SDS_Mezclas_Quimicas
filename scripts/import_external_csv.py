"""Script para importar archivos CSV externos (ECHA, GESTIS, NIOSH).

El administrador descarga estos CSV manualmente y los coloca en la carpeta
correspondiente. Este script los importa a la tabla cache_api para que el
orquestador los pueda consultar.

Uso: python scripts/import_external_csv.py <archivo.csv> <fuente>
Fuente: echa_csv, gestis_csv, niosh_csv
"""

import csv
import json
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from datetime import datetime, timezone

from app import create_app
from database import db
from models import CacheApi

app = create_app()


def importar_csv(ruta_archivo, fuente):
    """Importa un archivo CSV externo a la tabla cache_api.

    El CSV debe tener al menos una columna 'cas' o 'numero_cas'.
    Las demas columnas se guardan como JSON en datos_json.
    """
    if not os.path.exists(ruta_archivo):
        print(f"Error: Archivo no encontrado: {ruta_archivo}")
        return

    with app.app_context():
        count = 0
        with open(ruta_archivo, "r", encoding="utf-8", errors="replace") as f:
            reader = csv.DictReader(f)
            for row in reader:
                cas = row.get("cas") or row.get("numero_cas") or row.get("CAS")
                if not cas:
                    continue
                cas = cas.strip()
                datos = {k: v.strip() for k, v in row.items() if v and v.strip()}
                entrada = CacheApi(
                    numero_cas=cas,
                    fuente=fuente,
                    datos_json=json.dumps(datos, ensure_ascii=False),
                    fecha_consulta=datetime.now(timezone.utc),
                )
                db.session.add(entrada)
                count += 1

        db.session.commit()
        print(f"Importados {count} registros desde {ruta_archivo} (fuente: {fuente}).")


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Uso: python scripts/import_external_csv.py <archivo.csv> <fuente>")
        print("Fuentes validas: echa_csv, gestis_csv, niosh_csv")
        sys.exit(1)

    importar_csv(sys.argv[1], sys.argv[2])
