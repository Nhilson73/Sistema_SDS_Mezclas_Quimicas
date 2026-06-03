# Sistema FSD 2026

**Sistema de Generacion de Fichas de Datos de Seguridad (FDS/MSDS) para Mezclas Quimicas**

Aplicacion web local para laboratorios de control de calidad que genera Fichas de Datos de Seguridad (FDS) completas de 16 secciones para productos terminados que son mezclas quimicas: jabones, cremas, shampoos, desincrustantes, filtros solares, etc.

## Caracteristicas

- **Gestion de usuarios** con roles (Director de Calidad / Asistente de Calidad)
- **Mezclas con hasta 20 componentes** — calculo automatico de c.s.p. (cantidad suficiente para)
- **Subida de SDS en formato .md** con parseo automatico (extraccion de CAS, frases H/P, propiedades fisicas, toxicologia)
- **Orquestador de datos** — busqueda en: cache local → PubChem API → Wikipedia API → CSV importados (ECHA, GESTIS, NIOSH)
- **Motor GHS completo** — metodo de aditividad (ATE), suma de fracciones acuatica, clasificacion por umbral
- **Generador de FDS de 16 secciones** con plantillas adaptadas a los peligros detectados
- **Validador de coherencia** con reglas genericas (tabla de correlacion) y reglas especificas para cosmeticos
- **Exportacion a PDF** (WeasyPrint), JSON y CSV
- **Flujo de aprobacion** — borrador → revision → edicion → aprobacion con historial de versiones
- **Ensayos de laboratorio** con prioridad absoluta sobre datos calculados

## Requisitos

- Ubuntu 24.04 LTS (o superior)
- Python 3.10+
- Librerias del sistema para WeasyPrint:
  ```bash
  sudo apt install -y libpango-1.0-0 libcairo2 libgdk-pixbuf2.0-0 libffi-dev shared-mime-info
  ```

## Instalacion

```bash
# 1. Clonar el repositorio
git clone https://github.com/Nhilson73/Sistema_SDS_Mezclas_Quimicas.git
cd Sistema_SDS_Mezclas_Quimicas

# 2. Crear y activar entorno virtual
python3 -m venv venv
source venv/bin/activate

# 3. Instalar dependencias de Python
pip install -r requirements.txt

# 4. Instalar librerias del sistema para PDF
sudo apt install -y libpango-1.0-0 libcairo2 libgdk-pixbuf2.0-0 libffi-dev shared-mime-info

# 5. Inicializar la base de datos (crea tablas, carga CSV GHS, crea usuarios)
python scripts/init_db.py

# 6. Ejecutar la aplicacion
python app.py
```

La aplicacion estara disponible en **http://127.0.0.1:5000**

## Usuarios por defecto

| Rol | Email | Contrasena |
|-----|-------|------------|
| Director de Calidad | dcalidad@lab.com | director123 |
| Asistente de Calidad | asistente@lab.com | asistente123 |

## Estructura del proyecto

```
Sistema_SDS_Mezclas_Quimicas/
├── app.py                    # Aplicacion principal Flask (rutas, controladores)
├── config.py                 # Configuracion
├── database.py               # Conexion SQLAlchemy
├── models.py                 # Modelos de la BD (usuario, mezcla, componente, etc.)
├── orquestador.py            # Busqueda de datos: SDS.md → cache → PubChem → Wikipedia → CSV
├── clasificacion_ghs.py      # Motor GHS: aditividad, bridging, pictogramas
├── generador_fds.py          # Generador de FDS (16 secciones con plantillas)
├── validador.py              # Validador de coherencia + reglas cosmeticas
├── exportador.py             # Exportacion a PDF (WeasyPrint), JSON, CSV
├── requirements.txt          # Dependencias Python
├── data/ghs_tables/          # Tablas GHS en CSV (frases H/P, umbrales, correlacion)
├── scripts/
│   ├── init_db.py            # Inicializacion de BD y carga de CSV
│   └── import_external_csv.py # Importacion de CSV externos (ECHA/GESTIS/NIOSH)
├── templates/                # Plantillas HTML (Jinja2)
├── static/
│   ├── style.css
│   └── pictogramas/          # GHS01.svg ... GHS09.svg
├── uploads/                  # Archivos .md de SDS subidos
├── fds_generadas/            # PDFs exportados
└── instance/proyecto.db      # Base de datos SQLite
```

## Flujo de trabajo

1. **Asistente** crea una mezcla con nombre, lote y componentes
2. **Asistente** sube archivos SDS (.md) para cada componente — el sistema los parsea automaticamente
3. **Asistente** ingresa ensayos de laboratorio (pH, color, viscosidad, densidad, etc.)
4. **Asistente** genera la FDS — el sistema clasifica la mezcla segun GHS y genera las 16 secciones
5. **Director** revisa, puede editar cualquier campo, y aprueba la FDS
6. FDS exportable a PDF, JSON o CSV

## Importar CSV externos

```bash
python scripts/import_external_csv.py archivo_echa.csv echa_csv
python scripts/import_external_csv.py archivo_gestis.csv gestis_csv
python scripts/import_external_csv.py archivo_niosh.csv niosh_csv
```

## Tecnologias

- **Python 3** + **Flask** (microframework web)
- **SQLite** + **SQLAlchemy** (base de datos ORM)
- **Flask-Login** (autenticacion)
- **WeasyPrint** (generacion PDF)
- **PubChem API** + **Wikipedia API** (fuentes externas)
- **Jinja2** (plantillas HTML)

## Licencia

Proyecto gratuito de uso interno para laboratorios de control de calidad.
