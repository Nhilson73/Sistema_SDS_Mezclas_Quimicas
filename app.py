"""Aplicacion principal Flask - Sistema FSD 2026.

Generador de Fichas de Datos de Seguridad (FDS/MSDS) para Mezclas Quimicas.
"""

import json
import os
from datetime import datetime, timezone
from io import BytesIO

from flask import (
    Flask,
    flash,
    redirect,
    render_template,
    request,
    send_file,
    url_for,
)
from flask_login import (
    LoginManager,
    current_user,
    login_required,
    login_user,
    logout_user,
)

from clasificacion_ghs import clasificar_mezcla
from config import Config
from database import db
from exportador import exportar_csv, exportar_json, exportar_pdf
from generador_fds import generar_fds
from models import (
    Componente,
    Ensayo,
    FdsVersion,
    Mezcla,
    SdsSubida,
    Usuario,
)
from orquestador import obtener_datos_componente, parsear_sds_md
from validador import validar_fds

login_manager = LoginManager()


def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)

    os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)
    os.makedirs(app.config["FDS_OUTPUT_FOLDER"], exist_ok=True)
    os.makedirs(os.path.join(Config.BASE_DIR, "instance"), exist_ok=True)

    db.init_app(app)
    login_manager.init_app(app)
    login_manager.login_view = "login"
    login_manager.login_message = "Debe iniciar sesion para acceder."

    @login_manager.user_loader
    def load_user(user_id):
        return Usuario.query.get(int(user_id))

    # ------------------------------------------------------------------
    # Autenticacion
    # ------------------------------------------------------------------

    @app.route("/login", methods=["GET", "POST"])
    def login():
        if current_user.is_authenticated:
            return redirect(url_for("dashboard"))
        if request.method == "POST":
            email = request.form.get("email", "").strip()
            password = request.form.get("password", "")
            user = Usuario.query.filter_by(email=email).first()
            if user and user.check_password(password):
                login_user(user)
                flash("Sesion iniciada correctamente.", "success")
                return redirect(url_for("dashboard"))
            flash("Email o contrasena incorrectos.", "danger")
        return render_template("login.html")

    @app.route("/logout")
    @login_required
    def logout():
        logout_user()
        flash("Sesion cerrada.", "info")
        return redirect(url_for("login"))

    # ------------------------------------------------------------------
    # Dashboard
    # ------------------------------------------------------------------

    @app.route("/")
    @app.route("/dashboard")
    @login_required
    def dashboard():
        total_mezclas = Mezcla.query.count()
        borradores = Mezcla.query.filter_by(estado="borrador").count()
        aprobadas = Mezcla.query.filter_by(estado="aprobada").count()
        total_fds = FdsVersion.query.count()
        mezclas_recientes = Mezcla.query.order_by(Mezcla.fecha_creacion.desc()).limit(10).all()
        return render_template(
            "dashboard.html",
            total_mezclas=total_mezclas,
            borradores=borradores,
            aprobadas=aprobadas,
            total_fds=total_fds,
            mezclas_recientes=mezclas_recientes,
        )

    # ------------------------------------------------------------------
    # Mezclas
    # ------------------------------------------------------------------

    @app.route("/mezclas")
    @login_required
    def lista_mezclas():
        mezclas = Mezcla.query.order_by(Mezcla.fecha_creacion.desc()).all()
        return render_template("lista_mezclas.html", mezclas=mezclas)

    @app.route("/mezclas/nueva", methods=["GET", "POST"])
    @login_required
    def nueva_mezcla():
        if request.method == "POST":
            return _guardar_mezcla(mezcla_existente=None)
        return render_template("nueva_mezcla.html", mezcla=None, componentes_existentes=None)

    @app.route("/mezclas/<int:mezcla_id>")
    @login_required
    def ver_mezcla(mezcla_id):
        mezcla = Mezcla.query.get_or_404(mezcla_id)
        return render_template("ver_mezcla.html", mezcla=mezcla)

    @app.route("/mezclas/<int:mezcla_id>/editar", methods=["GET", "POST"])
    @login_required
    def editar_mezcla(mezcla_id):
        mezcla = Mezcla.query.get_or_404(mezcla_id)
        if request.method == "POST":
            return _guardar_mezcla(mezcla_existente=mezcla)
        return render_template(
            "nueva_mezcla.html",
            mezcla=mezcla,
            componentes_existentes=mezcla.componentes,
        )

    def _guardar_mezcla(mezcla_existente=None):
        """Logica comun para crear/actualizar una mezcla con sus componentes."""
        nombre = request.form.get("nombre_producto", "").strip()
        lote = request.form.get("lote", "").strip() or None
        num_comp = int(request.form.get("num_componentes", 1))

        if not nombre:
            flash("El nombre del producto es obligatorio.", "danger")
            return redirect(request.url)

        if mezcla_existente:
            mezcla = mezcla_existente
            mezcla.nombre_producto = nombre
            mezcla.lote = lote
            # Eliminar componentes antiguos
            for c in mezcla.componentes:
                db.session.delete(c)
        else:
            mezcla = Mezcla(
                nombre_producto=nombre,
                lote=lote,
                creado_por_id=current_user.id,
            )
            db.session.add(mezcla)

        db.session.flush()

        # Recoger componentes
        suma_pct = 0.0
        tiene_csp = False
        componentes = []

        for i in range(num_comp):
            comp_nombre = request.form.get(f"comp_nombre_{i}", "").strip()
            if not comp_nombre:
                continue
            comp_cas = request.form.get(f"comp_cas_{i}", "").strip() or None
            comp_pct_str = request.form.get(f"comp_pct_{i}", "")
            comp_csp = request.form.get(f"comp_csp_{i}") is not None

            comp_pct = None
            if not comp_csp and comp_pct_str:
                try:
                    comp_pct = float(comp_pct_str)
                    suma_pct += comp_pct
                except ValueError:
                    pass

            if comp_csp:
                tiene_csp = True

            comp = Componente(
                mezcla_id=mezcla.id,
                nombre_inci=comp_nombre,
                numero_cas=comp_cas,
                porcentaje=comp_pct,
                es_csp=comp_csp,
            )
            db.session.add(comp)
            db.session.flush()
            componentes.append((comp, i))

        # Calcular c.s.p.
        if tiene_csp and suma_pct < 100:
            csp_pct = 100.0 - suma_pct
            for comp, idx in componentes:
                if comp.es_csp:
                    comp.porcentaje = round(csp_pct, 2)

        # Validar suma
        if suma_pct > 100 and not tiene_csp:
            flash(f"La suma de porcentajes ({suma_pct:.1f}%) excede 100%.", "warning")

        # Procesar archivos SDS subidos
        for comp, idx in componentes:
            archivo = request.files.get(f"comp_sds_{idx}")
            if archivo and archivo.filename:
                filename = f"sds_comp_{comp.id}_{int(datetime.now(timezone.utc).timestamp())}.md"
                filepath = os.path.join(app.config["UPLOAD_FOLDER"], filename)
                archivo.save(filepath)

                sds = SdsSubida(
                    componente_id=comp.id,
                    archivo_md_path=filename,
                )
                db.session.add(sds)
                db.session.flush()

                # Parsear automaticamente
                datos = parsear_sds_md(filepath)
                if datos:
                    sds.contenido_extraido = json.dumps(datos, ensure_ascii=False)
                    # Actualizar CAS si se encontro
                    if datos.get("cas") and not comp.numero_cas:
                        comp.numero_cas = datos["cas"][0]

        db.session.commit()
        flash("Mezcla guardada correctamente.", "success")
        return redirect(url_for("ver_mezcla", mezcla_id=mezcla.id))

    # ------------------------------------------------------------------
    # Ensayos
    # ------------------------------------------------------------------

    @app.route("/mezclas/<int:mezcla_id>/ensayos", methods=["GET", "POST"])
    @login_required
    def ensayos_mezcla(mezcla_id):
        mezcla = Mezcla.query.get_or_404(mezcla_id)
        params_comunes = ["pH", "Color", "Viscosidad", "Densidad"]

        if request.method == "POST":
            # Eliminar ensayos previos
            Ensayo.query.filter_by(mezcla_id=mezcla.id).delete()

            # Guardar parametros comunes
            for i, param in enumerate(params_comunes):
                valor = request.form.get(f"param_valor_{i}", "").strip()
                unidad = request.form.get(f"param_unidad_{i}", "").strip() or None
                if valor:
                    ensayo = Ensayo(
                        mezcla_id=mezcla.id,
                        nombre_parametro=param,
                        valor=valor,
                        unidad=unidad,
                    )
                    db.session.add(ensayo)

            # Guardar parametros adicionales
            num_extras = int(request.form.get("num_extras", 0))
            for i in range(num_extras):
                nombre = request.form.get(f"extra_nombre_{i}", "").strip()
                valor = request.form.get(f"extra_valor_{i}", "").strip()
                unidad = request.form.get(f"extra_unidad_{i}", "").strip() or None
                if nombre and valor:
                    ensayo = Ensayo(
                        mezcla_id=mezcla.id,
                        nombre_parametro=nombre,
                        valor=valor,
                        unidad=unidad,
                    )
                    db.session.add(ensayo)

            db.session.commit()
            flash("Ensayos guardados correctamente.", "success")
            return redirect(url_for("ver_mezcla", mezcla_id=mezcla.id))

        # GET - cargar ensayos existentes
        ensayos = Ensayo.query.filter_by(mezcla_id=mezcla.id).all()
        ensayos_dict = {}
        unidades_dict = {}
        ensayos_adicionales = []
        for e in ensayos:
            if e.nombre_parametro in params_comunes:
                ensayos_dict[e.nombre_parametro] = e.valor
                unidades_dict[e.nombre_parametro] = e.unidad or ""
            else:
                ensayos_adicionales.append(e)

        return render_template(
            "ensayos_mezcla.html",
            mezcla=mezcla,
            ensayos_dict=ensayos_dict,
            unidades_dict=unidades_dict,
            ensayos_adicionales=ensayos_adicionales,
        )

    # ------------------------------------------------------------------
    # Generacion de FDS
    # ------------------------------------------------------------------

    @app.route("/mezclas/<int:mezcla_id>/generar-fds")
    @login_required
    def generar_fds(mezcla_id):
        mezcla = Mezcla.query.get_or_404(mezcla_id)

        # Preparar datos de componentes para clasificacion
        componentes_clasif = []
        for comp in mezcla.componentes:
            datos_comp = {
                "nombre_inci": comp.nombre_inci,
                "numero_cas": comp.numero_cas,
                "porcentaje": comp.porcentaje or 0,
                "es_csp": comp.es_csp,
                "codigos_h": [],
                "ate_oral": None,
                "ate_cutanea": None,
                "ate_inhalacion": None,
            }

            # Obtener datos de la SDS parseada
            sds = SdsSubida.query.filter_by(componente_id=comp.id).first()
            if sds and sds.contenido_extraido:
                try:
                    extraido = json.loads(sds.contenido_extraido)
                    datos_comp["codigos_h"] = extraido.get("frases_h", [])
                    tox = extraido.get("toxicologia", {})
                    if tox.get("DL50_oral"):
                        try:
                            import re
                            val = re.search(r"[\d.]+", tox["DL50_oral"])
                            if val:
                                datos_comp["ate_oral"] = float(val.group())
                        except (ValueError, AttributeError):
                            pass
                except (json.JSONDecodeError, TypeError):
                    pass

            # Buscar datos faltantes via orquestador
            if comp.numero_cas and not datos_comp["codigos_h"]:
                datos_ext = obtener_datos_componente(comp.numero_cas)
                if datos_ext:
                    # Los datos externos normalmente no traen codigos H directamente
                    pass

            componentes_clasif.append(datos_comp)

        # Clasificar mezcla
        clasificacion = clasificar_mezcla(componentes_clasif)

        # Preparar datos de ensayos
        ensayos_data = [
            {
                "nombre_parametro": e.nombre_parametro,
                "valor": e.valor,
                "unidad": e.unidad,
            }
            for e in mezcla.ensayos
        ]

        # Preparar datos de componentes para el generador
        componentes_data = [
            {
                "nombre_inci": c.nombre_inci,
                "numero_cas": c.numero_cas,
                "porcentaje": c.porcentaje,
                "es_csp": c.es_csp,
            }
            for c in mezcla.componentes
        ]

        # Generar FDS
        mezcla_data = {
            "nombre_producto": mezcla.nombre_producto,
            "lote": mezcla.lote,
            "fecha_creacion": mezcla.fecha_creacion,
            "version_actual": mezcla.version_actual,
        }

        from generador_fds import generar_fds as gen_fds
        secciones = gen_fds(mezcla_data, componentes_data, ensayos_data, clasificacion)

        # Validar
        componentes_val = [
            {
                "nombre_inci": c.nombre_inci,
                "porcentaje": c.porcentaje or 0,
                "codigos_h": componentes_clasif[i].get("codigos_h", []) if i < len(componentes_clasif) else [],
            }
            for i, c in enumerate(mezcla.componentes)
        ]
        validacion = validar_fds(secciones, clasificacion, ensayos_data, componentes_val)

        # Guardar como nueva version
        nueva_version = mezcla.version_actual
        version = FdsVersion(
            mezcla_id=mezcla.id,
            version_numero=nueva_version,
            fds_json=json.dumps(secciones, ensure_ascii=False),
            clasificacion_ghs_json=json.dumps(clasificacion, ensure_ascii=False),
            generada_por_id=current_user.id,
            es_borrador=True,
            es_aprobada=False,
        )
        db.session.add(version)
        mezcla.version_actual = nueva_version + 1
        db.session.commit()

        flash(f"FDS v{nueva_version} generada correctamente.", "success")
        return redirect(url_for("ver_fds", version_id=version.id))

    # ------------------------------------------------------------------
    # Ver / Editar / Aprobar FDS
    # ------------------------------------------------------------------

    @app.route("/fds/<int:version_id>")
    @login_required
    def ver_fds(version_id):
        version = FdsVersion.query.get_or_404(version_id)
        mezcla = version.mezcla

        secciones = json.loads(version.fds_json) if version.fds_json else {}
        clasificacion = json.loads(version.clasificacion_ghs_json) if version.clasificacion_ghs_json else {}

        # Validar para mostrar resultados
        ensayos_data = [
            {"nombre_parametro": e.nombre_parametro, "valor": e.valor, "unidad": e.unidad}
            for e in mezcla.ensayos
        ]
        componentes_val = [
            {"nombre_inci": c.nombre_inci, "porcentaje": c.porcentaje or 0}
            for c in mezcla.componentes
        ]
        validacion = validar_fds(secciones, clasificacion, ensayos_data, componentes_val)

        return render_template(
            "ver_fds.html",
            version=version,
            mezcla=mezcla,
            secciones=secciones,
            clasificacion=clasificacion,
            validacion=validacion,
        )

    @app.route("/fds/<int:version_id>/editar", methods=["GET", "POST"])
    @login_required
    def editar_fds(version_id):
        version = FdsVersion.query.get_or_404(version_id)
        mezcla = version.mezcla

        if current_user.rol != "director":
            flash("Solo el Director puede editar la FDS.", "danger")
            return redirect(url_for("ver_fds", version_id=version.id))

        secciones = json.loads(version.fds_json) if version.fds_json else {}

        if request.method == "POST":
            # Guardar cambios como nueva version
            nuevas_secciones = {}
            for num in range(1, 17):
                contenido = request.form.get(f"seccion_{num}", "")
                if str(num) in secciones:
                    nuevas_secciones[str(num)] = {
                        "titulo": secciones[str(num)].get("titulo", f"Seccion {num}"),
                        "contenido": contenido,
                    }

            nueva_version = FdsVersion(
                mezcla_id=mezcla.id,
                version_numero=mezcla.version_actual,
                fds_json=json.dumps(nuevas_secciones, ensure_ascii=False),
                clasificacion_ghs_json=version.clasificacion_ghs_json,
                generada_por_id=current_user.id,
                es_borrador=True,
                es_aprobada=False,
            )
            db.session.add(nueva_version)
            mezcla.version_actual += 1
            db.session.commit()

            flash(f"FDS v{nueva_version.version_numero} guardada con los cambios.", "success")
            return redirect(url_for("ver_fds", version_id=nueva_version.id))

        return render_template(
            "editar_fds.html",
            version=version,
            mezcla=mezcla,
            secciones=secciones,
        )

    @app.route("/fds/<int:version_id>/aprobar", methods=["POST"])
    @login_required
    def aprobar_fds(version_id):
        version = FdsVersion.query.get_or_404(version_id)
        mezcla = version.mezcla

        if current_user.rol != "director":
            flash("Solo el Director puede aprobar FDS.", "danger")
            return redirect(url_for("ver_fds", version_id=version.id))

        # Validar antes de aprobar
        secciones = json.loads(version.fds_json) if version.fds_json else {}
        clasificacion = json.loads(version.clasificacion_ghs_json) if version.clasificacion_ghs_json else {}
        ensayos_data = [
            {"nombre_parametro": e.nombre_parametro, "valor": e.valor, "unidad": e.unidad}
            for e in mezcla.ensayos
        ]
        componentes_val = [
            {"nombre_inci": c.nombre_inci, "porcentaje": c.porcentaje or 0}
            for c in mezcla.componentes
        ]
        validacion = validar_fds(secciones, clasificacion, ensayos_data, componentes_val)

        if not validacion["puede_aprobar"]:
            flash(f"No se puede aprobar: {validacion['total_errores']} error(es) de validacion.", "danger")
            return redirect(url_for("ver_fds", version_id=version.id))

        # Crear copia aprobada
        version_aprobada = FdsVersion(
            mezcla_id=mezcla.id,
            version_numero=mezcla.version_actual,
            fds_json=version.fds_json,
            clasificacion_ghs_json=version.clasificacion_ghs_json,
            generada_por_id=current_user.id,
            es_borrador=False,
            es_aprobada=True,
        )
        db.session.add(version_aprobada)
        mezcla.estado = "aprobada"
        mezcla.fecha_aprobacion = datetime.now(timezone.utc)
        mezcla.aprobado_por_id = current_user.id
        mezcla.version_actual += 1
        db.session.commit()

        flash("FDS aprobada correctamente.", "success")
        return redirect(url_for("ver_fds", version_id=version_aprobada.id))

    # ------------------------------------------------------------------
    # Exportacion
    # ------------------------------------------------------------------

    @app.route("/fds/<int:version_id>/exportar/pdf")
    @login_required
    def exportar_fds_pdf(version_id):
        version = FdsVersion.query.get_or_404(version_id)
        mezcla = version.mezcla
        secciones = json.loads(version.fds_json) if version.fds_json else {}
        clasificacion = json.loads(version.clasificacion_ghs_json) if version.clasificacion_ghs_json else {}
        mezcla_data = {
            "nombre_producto": mezcla.nombre_producto,
            "lote": mezcla.lote,
            "fecha_creacion": mezcla.fecha_creacion,
            "version_actual": version.version_numero,
        }
        pdf_bytes = exportar_pdf(secciones, clasificacion, mezcla_data)
        filename = f"FDS_{mezcla.nombre_producto.replace(' ', '_')}_v{version.version_numero}.pdf"
        return send_file(
            BytesIO(pdf_bytes),
            mimetype="application/pdf",
            as_attachment=True,
            download_name=filename,
        )

    @app.route("/fds/<int:version_id>/exportar/json")
    @login_required
    def exportar_fds_json(version_id):
        version = FdsVersion.query.get_or_404(version_id)
        mezcla = version.mezcla
        secciones = json.loads(version.fds_json) if version.fds_json else {}
        clasificacion = json.loads(version.clasificacion_ghs_json) if version.clasificacion_ghs_json else {}
        mezcla_data = {
            "nombre_producto": mezcla.nombre_producto,
            "lote": mezcla.lote,
            "version": version.version_numero,
        }
        json_str = exportar_json(secciones, clasificacion, mezcla_data)
        filename = f"FDS_{mezcla.nombre_producto.replace(' ', '_')}_v{version.version_numero}.json"
        return send_file(
            BytesIO(json_str.encode("utf-8")),
            mimetype="application/json",
            as_attachment=True,
            download_name=filename,
        )

    @app.route("/fds/<int:version_id>/exportar/csv")
    @login_required
    def exportar_fds_csv(version_id):
        version = FdsVersion.query.get_or_404(version_id)
        mezcla = version.mezcla
        secciones = json.loads(version.fds_json) if version.fds_json else {}
        clasificacion = json.loads(version.clasificacion_ghs_json) if version.clasificacion_ghs_json else {}
        mezcla_data = {
            "nombre_producto": mezcla.nombre_producto,
            "lote": mezcla.lote,
            "version": version.version_numero,
        }
        csv_str = exportar_csv(secciones, clasificacion, mezcla_data)
        filename = f"FDS_{mezcla.nombre_producto.replace(' ', '_')}_v{version.version_numero}.csv"
        return send_file(
            BytesIO(csv_str.encode("utf-8")),
            mimetype="text/csv",
            as_attachment=True,
            download_name=filename,
        )

    return app


# Crear la aplicacion
app = create_app()

# Crear tablas al iniciar si no existen
with app.app_context():
    db.create_all()

if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000)
