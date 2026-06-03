"""Configuracion central del proyecto FSD 2026."""

import os

class Config:
    BASE_DIR = os.path.abspath(os.path.dirname(__file__))
    SECRET_KEY = os.environ.get("SECRET_KEY", "clave-secreta-fsd-2026-cambiar-en-produccion")
    SQLALCHEMY_DATABASE_URI = "sqlite:///" + os.path.join(BASE_DIR, "instance", "proyecto.db")
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    UPLOAD_FOLDER = os.path.join(BASE_DIR, "uploads")
    FDS_OUTPUT_FOLDER = os.path.join(BASE_DIR, "fds_generadas")
    GHS_TABLES_FOLDER = os.path.join(BASE_DIR, "data", "ghs_tables")
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024  # 16 MB max upload
