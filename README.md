🚚 Logística Inteligente – Generador Automatizado de Guías

Sistema web desarrollado para automatizar la generación de guías de envío, integrando transportistas privados y servicios de paquetería externos como Skydropx.

El objetivo principal es reducir la carga operativa manual en procesos logísticos mediante automatización, validación de datos y trazabilidad centralizada.

🎯 Problema que Resuelve

En operaciones logísticas tradicionales, la generación de guías implica:

Copiar y pegar información manualmente

Validar campos de envío uno por uno

Generar guías en múltiples plataformas

Falta de trazabilidad estructurada

Este sistema transforma información en bruto en guías listas para impresión en cuestión de segundos, minimizando errores humanos y tiempos de operación.

🚀 Impacto del Proyecto

⚡ Reducción de tiempo operativo en generación de guías

🤖 Automatización del mapeo de datos sin intervención manual

📦 Gestión omnicanal (transportistas privados + Skydropx)

📊 Trazabilidad en tiempo real para auditoría y control

🛠️ Stack Tecnológico

Lenguaje: Python 3.10+

Framework Backend: Flask

Base de Datos: PostgreSQL (Supabase)

Integraciones externas: API de Skydropx

Frontend: HTML5 + Tailwind CSS

Arquitectura: Modular orientada a separación de responsabilidades

🧠 Funcionalidades Clave
🔎 Procesamiento Inteligente de Datos

Algoritmo que identifica automáticamente campos relevantes desde texto copiado en bruto (nombre, dirección, teléfono, referencias, etc.), reduciendo errores humanos y mejorando la eficiencia operativa.

🔌 Integración con API de Skydropx

Cliente personalizado para:

Cotización de envíos

Generación de guías

Manejo estructurado de respuestas y errores

📜 Historial Operativo

Panel interno que permite:

Consultar guías generadas

Revisar estatus

Auditar transacciones

📈 Escalabilidad

Diseño de esquema SQL optimizado para:

Altos volúmenes de registros

Consultas rápidas

Registro estructurado de logs

🏗️ Arquitectura del Proyecto
├── app.py                    # Punto de entrada y gestión de rutas
├── generador_guias.py        # Lógica de negocio y procesamiento inteligente
├── skydropx_client.py        # Cliente para integración con API externa
├── supabase_guias_generadas.sql  # Esquema de base de datos
├── static/                   # Interfaz de usuario
└── templates/                # Vistas HTML

El diseño modular facilita mantenimiento, pruebas y escalabilidad futura.

⚙️ Instalación y Configuración
1️⃣ Clonar el repositorio
git clone https://github.com/miriam1006/-logistica.git
cd -logistica
2️⃣ Crear entorno virtual
python -m venv .venv

Activar entorno:

Linux / Mac:

source .venv/bin/activate

Windows:

.venv\Scripts\activate

Instalar dependencias:

pip install -r requirements.txt
3️⃣ Variables de Entorno

Renombrar:

.env.example → .env

Configurar:

Credenciales de Supabase

API Key de Skydropx

Variables de entorno necesarias para ejecución

🔮 Posibles Mejoras Futuras

Autenticación y roles de usuario

Dashboard con métricas operativas

Manejo de múltiples APIs de paquetería

Implementación de pruebas unitarias

Dockerización para despliegue

👩‍💻 Sobre el Proyecto

Este proyecto refleja mi enfoque hacia:

Automatización de procesos

Integración de APIs externas

Diseño backend modular

Persistencia y trazabilidad de datos

Optimización operativa mediante software

Desarrollado como parte de mi transición hacia ingeniería de software con enfoque en backend y soluciones de automatización.
