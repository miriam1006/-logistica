# 🚚 Logística Inteligente

Sistema automatizado de generación de guías de envío, diseñado para optimizar operaciones logísticas mediante integración con transportistas privados y APIs externas como Skydropx.

Este proyecto transforma información de envío en bruto en guías listas para impresión en segundos, reduciendo errores humanos y tiempos operativos.

---
Backend (App Web): Próximamente
Base de Datos (Supabase): Entorno privado

---

## 🛠️ Tech Stack

### Backend (Servidor)

* **Lenguaje:** Python 3.10+
* **Framework:** Flask
* **Arquitectura:** Modular (Separación de lógica de negocio y cliente API)
* **Integraciones:** API de Skydropx
* **Base de Datos:** PostgreSQL (Supabase)
* **Gestión de Entorno:** python-dotenv

### Frontend (Interfaz Operativa)

* **HTML5**
* **Tailwind CSS**
* **Diseño Responsivo**
* **Panel operativo integrado**

---

## 🚀 Características Principales

### 📦 Generación Automatizada de Guías

Procesamiento inteligente de texto copiado en bruto para:

* Identificar nombre, dirección, teléfono y referencias
* Mapear automáticamente los campos requeridos
* Generar guías sin intervención manual

---

### 🔌 Integración con API de Skydropx

Cliente personalizado para:

* Cotización de envíos
* Creación de guías
* Manejo estructurado de respuestas y errores

---

### 📊 Trazabilidad y Auditoría

* Registro en base de datos de cada guía generada
* Historial consultable desde la interfaz
* Persistencia estructurada para control operativo

---

### ⚡ Optimización Operativa

* Reducción significativa del tiempo de captura manual
* Disminución de errores humanos en campos críticos
* Flujo centralizado para múltiples tipos de envío

---

## 🏗️ Arquitectura del Proyecto

```
logistica-inteligente/
├── app.py                     # Punto de entrada y definición de rutas
├── generador_guias.py         # Lógica de negocio y procesamiento inteligente
├── skydropx_client.py         # Cliente para integración con API externa
├── supabase_guias_generadas.sql  # Esquema de base de datos PostgreSQL
├── static/                    # Archivos estáticos (CSS / JS)
└── templates/                 # Vistas HTML
```

Arquitectura orientada a separación de responsabilidades y escalabilidad futura.

---

## ⚙️ Instalación y Configuración Local

### 1️⃣ Clonar el repositorio

```bash
git clone https://github.com/miriam1006/-logistica.git
cd -logistica
```

---

### 2️⃣ Crear y activar entorno virtual

```bash
python -m venv .venv
```

Activar entorno:

Linux / Mac:

```bash
source .venv/bin/activate
```

Windows:

```bash
.venv\Scripts\activate
```

Instalar dependencias:

```bash
pip install -r requirements.txt
```

---

### 3️⃣ Configurar variables de entorno

Renombrar:

```
.env.example → .env
```

Configurar:

```
SUPABASE_URL=tu_url
SUPABASE_KEY=tu_key
SKYDROPX_API_KEY=tu_api_key
```

---

## 📂 Base de Datos

Motor: PostgreSQL (Supabase)

Incluye:

* Tabla de guías generadas
* Logs de transacciones
* Campos estructurados para auditoría
* Optimización para consultas frecuentes

---

## 🔮 Mejoras Futuras

* Autenticación con roles de usuario
* Dashboard con métricas operativas
* Integración con múltiples APIs de paquetería
* Pruebas unitarias y testing automatizado
* Dockerización para despliegue productivo
* Implementación de colas asíncronas (Celery / Redis)

---

## 👩‍💻 Sobre el Proyecto

Desarrollado por **Miriam G.** 
