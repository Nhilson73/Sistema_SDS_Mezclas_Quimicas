"""Modelos de la base de datos (SQLAlchemy) - Sistema FSD 2026."""

from datetime import datetime, timezone

from flask_login import UserMixin
from werkzeug.security import check_password_hash, generate_password_hash

from database import db


def _utcnow():
    return datetime.now(timezone.utc)


class Usuario(UserMixin, db.Model):
    __tablename__ = "usuario"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    nombre = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(100), unique=True, nullable=False)
    password_hash = db.Column(db.String(200), nullable=False)
    rol = db.Column(db.String(20), nullable=False)  # 'director' o 'asistente'
    fecha_registro = db.Column(db.DateTime, default=_utcnow)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)


class Mezcla(db.Model):
    __tablename__ = "mezcla"

    id = db.Column(db.Integer, primary_key=True)
    nombre_producto = db.Column(db.String(200), nullable=False)
    lote = db.Column(db.String(50))
    fecha_creacion = db.Column(db.DateTime, default=_utcnow)
    estado = db.Column(db.String(20), nullable=False, default="borrador")
    fecha_aprobacion = db.Column(db.DateTime)
    aprobado_por_id = db.Column(db.Integer, db.ForeignKey("usuario.id"))
    version_actual = db.Column(db.Integer, default=1)
    creado_por_id = db.Column(db.Integer, db.ForeignKey("usuario.id"))

    componentes = db.relationship("Componente", backref="mezcla", cascade="all, delete-orphan", lazy=True)
    ensayos = db.relationship("Ensayo", backref="mezcla", cascade="all, delete-orphan", lazy=True)
    versiones_fds = db.relationship("FdsVersion", backref="mezcla", cascade="all, delete-orphan", lazy=True)
    aprobado_por = db.relationship("Usuario", foreign_keys=[aprobado_por_id])
    creado_por = db.relationship("Usuario", foreign_keys=[creado_por_id])


class Componente(db.Model):
    __tablename__ = "componente"

    id = db.Column(db.Integer, primary_key=True)
    mezcla_id = db.Column(db.Integer, db.ForeignKey("mezcla.id"), nullable=False)
    nombre_inci = db.Column(db.String(200), nullable=False)
    numero_cas = db.Column(db.String(20))
    porcentaje = db.Column(db.Float)
    es_csp = db.Column(db.Boolean, default=False)

    sds_subidas = db.relationship("SdsSubida", backref="componente", cascade="all, delete-orphan", lazy=True)


class Ensayo(db.Model):
    __tablename__ = "ensayo"

    id = db.Column(db.Integer, primary_key=True)
    mezcla_id = db.Column(db.Integer, db.ForeignKey("mezcla.id"), nullable=False)
    nombre_parametro = db.Column(db.String(50), nullable=False)
    valor = db.Column(db.String(100), nullable=False)
    unidad = db.Column(db.String(20))
    fecha_ingreso = db.Column(db.DateTime, default=_utcnow)


class SdsSubida(db.Model):
    __tablename__ = "sds_subida"

    id = db.Column(db.Integer, primary_key=True)
    componente_id = db.Column(db.Integer, db.ForeignKey("componente.id"), nullable=False)
    archivo_md_path = db.Column(db.String(300), nullable=False)
    fecha_subida = db.Column(db.DateTime, default=_utcnow)
    contenido_extraido = db.Column(db.Text)  # JSON con datos parseados


class CacheApi(db.Model):
    __tablename__ = "cache_api"

    id = db.Column(db.Integer, primary_key=True)
    numero_cas = db.Column(db.String(20), nullable=False)
    fuente = db.Column(db.String(50), nullable=False)
    datos_json = db.Column(db.Text, nullable=False)
    fecha_consulta = db.Column(db.DateTime, default=_utcnow)


class FdsVersion(db.Model):
    __tablename__ = "fds_version"

    id = db.Column(db.Integer, primary_key=True)
    mezcla_id = db.Column(db.Integer, db.ForeignKey("mezcla.id"), nullable=False)
    version_numero = db.Column(db.Integer, nullable=False)
    fds_json = db.Column(db.Text, nullable=False)
    clasificacion_ghs_json = db.Column(db.Text)
    fecha_generacion = db.Column(db.DateTime, default=_utcnow)
    generada_por_id = db.Column(db.Integer, db.ForeignKey("usuario.id"), nullable=False)
    es_borrador = db.Column(db.Boolean, default=True)
    es_aprobada = db.Column(db.Boolean, default=False)

    generada_por = db.relationship("Usuario", foreign_keys=[generada_por_id])


# ---------------------------------------------------------------------------
# Tablas GHS (cargadas desde CSV, solo lectura)
# ---------------------------------------------------------------------------

class ClasePeligro(db.Model):
    __tablename__ = "clase_peligro"

    id = db.Column(db.Integer, primary_key=True)
    nombre_clase = db.Column(db.String(200), nullable=False)
    metodo_calculo = db.Column(db.String(50))


class CategoriaUmbral(db.Model):
    __tablename__ = "categoria_umbral"

    id = db.Column(db.Integer, primary_key=True)
    clase_peligro_id = db.Column(db.Integer, db.ForeignKey("clase_peligro.id"), nullable=False)
    categoria = db.Column(db.String(20), nullable=False)
    umbral_generico = db.Column(db.Float)
    unidad = db.Column(db.String(20))


class FraseH(db.Model):
    __tablename__ = "frase_h"

    id = db.Column(db.Integer, primary_key=True)
    codigo_h = db.Column(db.String(10), nullable=False)
    texto_es = db.Column(db.String(500), nullable=False)
    clase_peligro = db.Column(db.String(200))
    categoria = db.Column(db.String(20))
    pictograma_codigo = db.Column(db.String(10))


class FraseP(db.Model):
    __tablename__ = "frase_p"

    id = db.Column(db.Integer, primary_key=True)
    codigo_p = db.Column(db.String(10), nullable=False)
    texto_es = db.Column(db.String(500), nullable=False)
    codigos_h_aplicables = db.Column(db.String(200))


class Pictograma(db.Model):
    __tablename__ = "pictograma"

    id = db.Column(db.Integer, primary_key=True)
    codigo_ghs = db.Column(db.String(10), nullable=False)
    nombre = db.Column(db.String(100), nullable=False)
    archivo_svg = db.Column(db.String(100), nullable=False)


class FactorAte(db.Model):
    __tablename__ = "factor_ate"

    id = db.Column(db.Integer, primary_key=True)
    via_origen = db.Column(db.String(50), nullable=False)
    via_destino = db.Column(db.String(50), nullable=False)
    factor_conversion = db.Column(db.Float, nullable=False)


class CorrelacionSeccionFds(db.Model):
    __tablename__ = "correlacion_seccion_fds"

    id = db.Column(db.Integer, primary_key=True)
    codigo_h = db.Column(db.String(10), nullable=False)
    seccion_fds = db.Column(db.String(50), nullable=False)
    regla_coherencia = db.Column(db.String(500), nullable=False)
    mensaje_error = db.Column(db.String(500), nullable=False)
    nivel = db.Column(db.String(10), nullable=False)  # 'error' o 'warning'
