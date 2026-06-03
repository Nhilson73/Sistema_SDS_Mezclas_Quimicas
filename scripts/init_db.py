"""Script de inicializacion de la base de datos.

Crea las tablas, carga los CSV de GHS y crea usuarios por defecto.
Ejecutar: python scripts/init_db.py
"""

import csv
import os
import sys

# Agregar directorio padre al path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app import create_app
from database import db
from models import (
    CategoriaUmbral,
    ClasePeligro,
    CorrelacionSeccionFds,
    FactorAte,
    FraseH,
    FraseP,
    Pictograma,
    Usuario,
)

app = create_app()


def cargar_csv(ruta, modelo, mapa_columnas):
    """Carga un archivo CSV en una tabla del modelo."""
    if not os.path.exists(ruta):
        print(f"  AVISO: Archivo no encontrado: {ruta}")
        return 0

    count = 0
    with open(ruta, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            kwargs = {}
            for col_csv, col_modelo in mapa_columnas.items():
                valor = row.get(col_csv, "").strip()
                if valor:
                    kwargs[col_modelo] = valor
                else:
                    kwargs[col_modelo] = None
            obj = modelo(**kwargs)
            db.session.add(obj)
            count += 1
    db.session.commit()
    return count


def init_db():
    """Inicializa la base de datos completa."""
    with app.app_context():
        print("Creando tablas...")
        db.create_all()
        print("Tablas creadas.\n")

        ghs_dir = os.path.join(
            os.path.abspath(os.path.join(os.path.dirname(__file__), "..")),
            "data", "ghs_tables"
        )

        # Cargar clases de peligro
        print("Cargando clases de peligro...")
        if ClasePeligro.query.count() == 0:
            n = cargar_csv(
                os.path.join(ghs_dir, "clases_peligro.csv"),
                ClasePeligro,
                {"nombre_clase": "nombre_clase", "metodo_calculo": "metodo_calculo"},
            )
            print(f"  {n} clases de peligro cargadas.")
        else:
            print("  Ya existen datos. Saltando.")

        # Cargar categorias y umbrales
        print("Cargando categorias y umbrales...")
        if CategoriaUmbral.query.count() == 0:
            ruta = os.path.join(ghs_dir, "categorias_umbrales.csv")
            if os.path.exists(ruta):
                count = 0
                with open(ruta, "r", encoding="utf-8") as f:
                    reader = csv.DictReader(f)
                    for row in reader:
                        clase_nombre = row.get("clase_peligro", "").strip()
                        clase = ClasePeligro.query.filter_by(nombre_clase=clase_nombre).first()
                        if not clase:
                            continue
                        obj = CategoriaUmbral(
                            clase_peligro_id=clase.id,
                            categoria=row.get("categoria", "").strip(),
                            umbral_generico=float(row["umbral_generico"]) if row.get("umbral_generico") else None,
                            unidad=row.get("unidad", "").strip() or None,
                        )
                        db.session.add(obj)
                        count += 1
                db.session.commit()
                print(f"  {count} categorias cargadas.")
            else:
                print("  Archivo no encontrado.")
        else:
            print("  Ya existen datos. Saltando.")

        # Cargar frases H
        print("Cargando frases H...")
        if FraseH.query.count() == 0:
            n = cargar_csv(
                os.path.join(ghs_dir, "frases_h.csv"),
                FraseH,
                {
                    "codigo_h": "codigo_h",
                    "texto_es": "texto_es",
                    "clase_peligro": "clase_peligro",
                    "categoria": "categoria",
                    "pictograma": "pictograma_codigo",
                },
            )
            print(f"  {n} frases H cargadas.")
        else:
            print("  Ya existen datos. Saltando.")

        # Cargar frases P
        print("Cargando frases P...")
        if FraseP.query.count() == 0:
            n = cargar_csv(
                os.path.join(ghs_dir, "frases_p.csv"),
                FraseP,
                {
                    "codigo_p": "codigo_p",
                    "texto_es": "texto_es",
                    "codigos_h_aplicables": "codigos_h_aplicables",
                },
            )
            print(f"  {n} frases P cargadas.")
        else:
            print("  Ya existen datos. Saltando.")

        # Cargar pictogramas
        print("Cargando pictogramas...")
        if Pictograma.query.count() == 0:
            n = cargar_csv(
                os.path.join(ghs_dir, "pictogramas.csv"),
                Pictograma,
                {
                    "codigo_ghs": "codigo_ghs",
                    "nombre": "nombre",
                    "archivo_svg": "archivo_svg",
                },
            )
            print(f"  {n} pictogramas cargados.")
        else:
            print("  Ya existen datos. Saltando.")

        # Cargar factores ATE
        print("Cargando factores ATE...")
        if FactorAte.query.count() == 0:
            ruta = os.path.join(ghs_dir, "factores_ate.csv")
            if os.path.exists(ruta):
                count = 0
                with open(ruta, "r", encoding="utf-8") as f:
                    reader = csv.DictReader(f)
                    for row in reader:
                        obj = FactorAte(
                            via_origen=row["via_origen"].strip(),
                            via_destino=row["via_destino"].strip(),
                            factor_conversion=float(row["factor_conversion"]),
                        )
                        db.session.add(obj)
                        count += 1
                db.session.commit()
                print(f"  {count} factores ATE cargados.")
        else:
            print("  Ya existen datos. Saltando.")

        # Cargar correlacion secciones FDS
        print("Cargando tabla de correlacion...")
        if CorrelacionSeccionFds.query.count() == 0:
            n = cargar_csv(
                os.path.join(ghs_dir, "correlacion_secciones_fds.csv"),
                CorrelacionSeccionFds,
                {
                    "codigo_h": "codigo_h",
                    "seccion_fds": "seccion_fds",
                    "regla_coherencia": "regla_coherencia",
                    "mensaje_error": "mensaje_error",
                    "nivel": "nivel",
                },
            )
            print(f"  {n} reglas de correlacion cargadas.")
        else:
            print("  Ya existen datos. Saltando.")

        # Crear usuarios por defecto
        print("\nCreando usuarios por defecto...")
        if Usuario.query.count() == 0:
            director = Usuario(
                nombre="Director de Calidad",
                email="dcalidad@lab.com",
                rol="director",
            )
            director.set_password("director123")

            asistente = Usuario(
                nombre="Asistente de Calidad",
                email="asistente@lab.com",
                rol="asistente",
            )
            asistente.set_password("asistente123")

            db.session.add(director)
            db.session.add(asistente)
            db.session.commit()
            print("  Usuarios creados:")
            print("    - Director: dcalidad@lab.com / director123")
            print("    - Asistente: asistente@lab.com / asistente123")
        else:
            print("  Ya existen usuarios. Saltando.")

        print("\nBase de datos inicializada correctamente.")


if __name__ == "__main__":
    init_db()
