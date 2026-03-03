from fpdf import FPDF
from supabase import create_client
import os
from dotenv import load_dotenv

# Cargar configuración desde el archivo .env
load_dotenv()
url = os.getenv("SUPABASE_URL")
key = os.getenv("SUPABASE_KEY")
supabase = create_client(url, key)

def obtener_guia_global():
    res = supabase.table("configuracion").select("valor").eq("clave", "ultimo_numero_guia").execute()
    nuevo_num = res.data[0]['valor'] + 1
    supabase.table("configuracion").update({"valor": nuevo_num}).eq("clave", "ultimo_numero_guia").execute()
    return nuevo_num

def anular_ultima_guia():
    """Decrementa el número de guía y borra su registro en guias_generadas para reutilizarlo."""
    res = supabase.table("configuracion").select("valor").eq("clave", "ultimo_numero_guia").execute()
    valor_actual = res.data[0]['valor']
    if valor_actual <= 0:
        return False
    supabase.table("configuracion").update({"valor": valor_actual - 1}).eq("clave", "ultimo_numero_guia").execute()
    try:
        supabase.table("guias_generadas").delete().eq("num_guia", valor_actual).execute()
    except Exception:
        pass
    return True

# Mapeo de columnas (índice 0) según el documento origen hasta AF = TELEFONO:
# 0 MES, 1 AÑO, 2 CANAL, 3 NO, 4 PEDIDO CASA FERRO, 5 ENVIA, 6 CANTIDAD, 7 PRODUCTO, 8 NOTA,
# 9-23 (días, factura, status, envío, paquetería, guía, recolección, fechas...),
# 24 NOMBRE COMPLETO, 25 CALLE, 26 COLONIA, 27 CODIGO POSTAL, 28 CIUDAD, 29 ESTADO,
# 30 TIPO DE PAGO, 31 TELEFONO (col AF), 32 MAIL...
# Si "ESTADO de Mexico" se pega en 2 celdas, TELEFONO puede quedar en 32.
IDX_PEDIDO, IDX_CANTIDAD, IDX_PRODUCTO = 4, 6, 7
IDX_NOMBRE, IDX_CALLE, IDX_COLONIA, IDX_CP = 24, 25, 26, 27
IDX_CIUDAD, IDX_ESTADO = 28, 29
IDX_TELEFONO_PRINCIPAL, IDX_TELEFONO_FALLBACK = 31, 32
IDX_MAIL = 33  # columna AH

def _procesar_fila(d, productos_datos, pedidos_lista, info_cliente):
    """Extrae datos de una fila (lista de columnas). Devuelve True si la fila era válida."""
    if len(d) < 30:
        return False
    def get_val(idx):
        return d[idx].strip().upper() if len(d) > idx and d[idx].strip() else ""
    if not info_cliente:
        info_cliente["nombre"] = get_val(IDX_NOMBRE)
        info_cliente["calle"] = get_val(IDX_CALLE)
        info_cliente["colonia"] = get_val(IDX_COLONIA)
        info_cliente["cp"] = get_val(IDX_CP)
        info_cliente["ciudad"] = get_val(IDX_CIUDAD)
        info_cliente["estado"] = get_val(IDX_ESTADO)
        info_cliente["telefono"] = get_val(IDX_TELEFONO_PRINCIPAL) or get_val(IDX_TELEFONO_FALLBACK)
        info_cliente["email"] = get_val(IDX_MAIL)
    pedidos_lista.append(get_val(IDX_PEDIDO))
    productos_datos.append([get_val(IDX_CANTIDAD), get_val(IDX_PRODUCTO)])
    return True

def obtener_info_cliente(raw_data):
    """Parsea raw_data y devuelve info_cliente dict para Skydropx, o None si no se puede parsear."""
    pedidos_lista, _, info_cliente = _parse_raw_data(raw_data)
    if not pedidos_lista or not info_cliente:
        return None
    return info_cliente


def obtener_pedidos_lista(raw_data):
    """
    Devuelve lista de pedidos detectados (sin duplicados, conservando orden).
    """
    pedidos_lista, _, _ = _parse_raw_data(raw_data)
    if not pedidos_lista:
        return []
    return list(dict.fromkeys([str(p or "").strip() for p in pedidos_lista if str(p or "").strip()]))


def _parse_raw_data(raw_data):
    """Parsea el texto pegado y devuelve (pedidos_lista, productos_datos, info_cliente) o (None, None, None)."""
    raw_data = raw_data.replace('\r\n', '\n').replace('\r', '\n').strip()
    productos_datos = []
    pedidos_lista = []
    info_cliente = {}
    filas = raw_data.split('\n')
    for fila in filas:
        d = [c.strip() for c in fila.split('\t')]
        _procesar_fila(d, productos_datos, pedidos_lista, info_cliente)
    if not pedidos_lista and filas:
        celdas = [c.strip() for c in raw_data.replace('\n', '\t').split('\t')]
        if len(celdas) >= 30:
            _procesar_fila(celdas, productos_datos, pedidos_lista, info_cliente)
        if not pedidos_lista and len(filas) >= 32:
            d = [f.strip() for f in filas[:32] if f.strip()]
            if len(d) >= 30:
                _procesar_fila(d, productos_datos, pedidos_lista, info_cliente)
    if not pedidos_lista:
        return None, None, None
    return pedidos_lista, productos_datos, info_cliente

def _clave_pedidos(pedidos_lista):
    """Clave única para identificar el mismo conjunto de pedidos (orden normalizado)."""
    return ",".join(sorted(pedidos_lista))


def _build_pdf_filename(pedidos_lista):
    """
    Nombre legible para PDF:
    - 1 pedido: "12345.pdf"
    - 2 pedidos: "12345 y 12346.pdf"
    - 3+ pedidos: "12345 a 12360.pdf"
    """
    pedidos_clean = [str(p or "").strip() for p in pedidos_lista if str(p or "").strip()]
    if not pedidos_clean:
        return "guia.pdf"
    pedidos_unique = list(dict.fromkeys(pedidos_clean))
    if len(pedidos_unique) == 1:
        base = pedidos_unique[0]
    elif len(pedidos_unique) == 2:
        base = f"{pedidos_unique[0]} y {pedidos_unique[1]}"
    else:
        base = f"{pedidos_unique[0]} a {pedidos_unique[-1]}"
    return f"{base}.pdf"

def guia_ya_generada(pedidos_lista):
    """Devuelve (True, num_guia) si ya existe una guía para estos pedidos, (False, None) si no."""
    try:
        clave = _clave_pedidos(pedidos_lista)
        res = supabase.table("guias_generadas").select("num_guia").eq("pedidos", clave).order("created_at", desc=True).limit(1).execute()
        if res.data and len(res.data) > 0:
            return True, res.data[0]["num_guia"]
    except Exception:
        pass
    return False, None

def _registrar_guia_generada(num_guia, pedidos_lista):
    try:
        supabase.table("guias_generadas").insert({"num_guia": num_guia, "pedidos": _clave_pedidos(pedidos_lista)}).execute()
    except Exception:
        pass

def crear_guia_backend(raw_data, notas=None, num_guia_fijo=None):
    """Genera el PDF. Si num_guia_fijo es None y la guía ya existía, devuelve (None, num_guia). Si no, devuelve (nombre_archivo, None)."""
    try:
        pedidos_lista, productos_datos, info_cliente = _parse_raw_data(raw_data)
        if not pedidos_lista:
            print("Error: Selecciona las filas completas en Sheets.")
            return None, None

        if num_guia_fijo is None:
            ya, num_ya = guia_ya_generada(pedidos_lista)
            if ya:
                return None, num_ya  # ya generada, el cliente puede descartar o regenerar

        num_guia_auto = num_guia_fijo if num_guia_fijo is not None else obtener_guia_global()
        if num_guia_fijo is None:
            _registrar_guia_generada(num_guia_auto, pedidos_lista)
        pdf = FPDF()
        pdf.add_page()
        
        # --- ENCABEZADO ---
        pdf.set_draw_color(180, 180, 180)
        pdf.set_fill_color(245, 245, 245)
        pdf.set_font("Arial", 'B', 20)
        pdf.cell(190, 15, "GUIA DE ENVIO", border=1, ln=True, align='C', fill=True)
        
        pdf.set_font("Arial", 'B', 11)
        pedidos_str = " / ".join(pedidos_lista)
        pdf.cell(95, 10, f"PEDIDOS: {pedidos_str}", border=1, ln=0, align='C')
        pdf.cell(95, 10, f"GUIA #: {num_guia_auto}", border=1, ln=1, align='C')
        
        # --- DIRECCIONES (Lógica sin COL. vacío) ---
        pdf.ln(8)
        pdf.set_font("Arial", 'B', 11)
        pdf.cell(95, 8, "REMITENTE", ln=0); pdf.cell(95, 8, "DESTINATARIO", ln=1)
        
        pdf.set_font("Arial", '', 10)
        y_dir = pdf.get_y()
        pdf.set_xy(10, y_dir)
        pdf.multi_cell(90, 5, "CASA FERRO\nPLAYA REGATAS 391\nCOL. REFORMA IZTACCIHUATL NORTE\nCP 08810, CDMX")
        
        dest_lines = [info_cliente['nombre'], info_cliente['calle']]
        if info_cliente['colonia']: dest_lines.append(f"COL. {info_cliente['colonia']}")
        dest_lines.append(f"CP {info_cliente['cp']}")
        if info_cliente['telefono']: dest_lines.append(f"TEL: {info_cliente['telefono']}")
            
        pdf.set_xy(105, y_dir)
        pdf.multi_cell(90, 5, "\n".join(dest_lines))

        # --- TABLA DE CONTENIDO UNIFICADA ---
        pdf.set_y(pdf.get_y() + 10)
        pdf.set_font("Arial", 'B', 10)
        pdf.set_fill_color(245, 245, 245)
        pdf.cell(25, 8, "CANT.", border=1, align='C', fill=True)
        pdf.cell(165, 8, "DESCRIPCION DEL ARTICULO", border=1, ln=1, align='C', fill=True)
        
        pdf.set_font("Arial", '', 10)
        pdf.set_fill_color(252, 252, 252)
        
        # Dibujo manual de bordes para mantener columnas parejas.
        ALTURA_LINEA = 6
        ALTURA_MINIMA_FILA = 12
        ANCHO_CANT = 25
        ANCHO_DESC = 165
        for item in productos_datos:
            texto_art = item[1]
            lineas_desc = pdf.multi_cell(ANCHO_DESC, ALTURA_LINEA, texto_art, split_only=True)
            num_lineas = max(1, len(lineas_desc))
            alto_fila = max(num_lineas * ALTURA_LINEA, ALTURA_MINIMA_FILA)

            curr_x, curr_y = pdf.get_x(), pdf.get_y()
            pdf.rect(curr_x, curr_y, ANCHO_CANT, alto_fila)
            pdf.rect(curr_x + ANCHO_CANT, curr_y, ANCHO_DESC, alto_fila)

            qty_y = curr_y + max(0, (alto_fila - ALTURA_LINEA) / 2)
            pdf.set_xy(curr_x, qty_y)
            pdf.cell(ANCHO_CANT, ALTURA_LINEA, item[0], border=0, align='C', fill=False)

            pdf.set_xy(curr_x + ANCHO_CANT, curr_y)
            pdf.multi_cell(ANCHO_DESC, ALTURA_LINEA, texto_art, border=0, align='L', fill=False)
            pdf.set_y(curr_y + alto_fila)

        # --- NOTAS (solo si hay texto) ---
        if notas and notas.strip():
            pdf.ln(6)
            pdf.set_font("Arial", 'B', 10)
            pdf.set_fill_color(248, 248, 248)
            pdf.cell(190, 6, "NOTAS:", border=1, ln=1, fill=True)
            pdf.set_font("Arial", '', 9)
            pdf.multi_cell(190, 6, notas.strip())
            pdf.ln(4)

        # --- SECCIÓN DE FIRMA (CON SOMBREADO) ---
        pdf.set_y(-65)
        pdf.set_fill_color(245, 245, 245)
        pdf.set_font("Arial", 'B', 11)
        pdf.cell(190, 10, "  CONFIRMACION DE ENTREGA", border=1, ln=True, fill=True)
        
        pdf.set_font("Arial", '', 10)
        pdf.ln(4)
        pdf.cell(100, 10, "CANTIDAD DE PAQUETES: ________________"); pdf.cell(90, 10, "FECHA: ____ / ____ / ____", ln=1)
        pdf.ln(2)
        pdf.cell(190, 10, "NOMBRE Y FIRMA DE QUIEN RECIBE: ___________________________________________", ln=True)

        # ... (código previo del PDF)
        nombre_archivo = _build_pdf_filename(pedidos_lista)
        pdf.output(nombre_archivo)
        print(f"¡Guía {num_guia_auto} generada!")
        return nombre_archivo, None
    except Exception as e:
        print(f"Error: {e}")
        raise  # Para que app.py pueda devolver el mensaje al cliente

if __name__ == "__main__":
    # Ejecutar vía app web; aquí solo para pruebas con datos de ejemplo
    crear_guia_backend("")