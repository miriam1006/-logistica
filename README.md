🚚 Logística Inteligente - Generador de Guías
Sistema automatizado de gestión logística diseñado para agilizar el despacho de mercancías mediante la integración de transportistas privados y servicios de paquetería externos (Skydropx).

🚀 Impacto del Proyecto
Este sistema elimina la carga operativa manual al procesar datos de envío en bruto y transformarlos automáticamente en guías listas para impresión.

Automatización: Identificación inteligente de campos y mapeo de datos para generación de guías sin intervención manual.

Omnicanalidad: Gestión centralizada de guías internas (transportistas privados) y guías de mercado (Skydropx).

Trazabilidad: Registro en tiempo real de cada transacción para auditoría y control de entregas.

🛠️ Stack Tecnológico
Lenguaje: Python 3.10+

Backend Framework: Flask (vía app.py)

Base de Datos: Supabase / PostgreSQL (Persistencia y logs)

Integraciones: Skydropx API

Frontend: HTML5 / Tailwind CSS (Interfaz responsiva)

📦 Funcionalidades Clave
Procesamiento Inteligente: Algoritmo que identifica automáticamente campos relevantes desde información copiada, reduciendo errores humanos.

Cliente de API Robusto: Integración personalizada con Skydropx para cotización y generación de guías.

Historial Operativo: Panel integrado para consulta de resultados y estatus de guías generadas directamente en la interfaz.

Escalabilidad: Esquema SQL diseñado para soportar altos volúmenes de registros y consultas rápidas.

📂 Estructura del Proyecto
app.py: Punto de entrada de la aplicación web y gestión de rutas.

generador_guias.py: Núcleo de la lógica de negocio y procesamiento de datos.

skydropx_client.py: Módulo especializado para la comunicación con la API de envíos.

supabase_guias_generadas.sql: Definición del esquema de datos para PostgreSQL.

static/: Interfaz de usuario (UI) para el operador logístico.

🔧 Configuración
Clonar repositorio:

Bash
git clone https://github.com/miriam1006/-logistica.git
cd -logistica
Entorno Virtual:

Bash
python -m venv .venv
source .venv/bin/activate  # Linux/Mac
.venv\Scripts\activate     # Windows
pip install -r requirements.txt
Variables de Entorno:
Renombrar .env.example a .env y configurar tus credenciales de Supabase y Skydropx.
