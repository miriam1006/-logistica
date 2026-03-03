import pyperclip
from fpdf import FPDF
import os

def obtener_siguiente_guia():
    archivo_conteo = "ultimo_numero.txt"
    if not os.path.exists(archivo_conteo):
        numero_actual = 1073
    else:
        with open(archivo_conteo, "r") as f:
            try:
                line = f.read().strip()
                numero_actual = int(line) + 1 if line else 1073
            except:
                numero_actual = 1073
    with open(archivo_conteo, "w") as f:
        f.write(str(numero_actual))
    return numero_actual

def crear_guia():
    try:
        raw_data = pyperclip.paste().strip()
        filas = raw_data.split('\n')
        
        productos_datos = []
        pedidos_lista = []
        info_cliente = {}
        
        for fila in filas:
            d = fila.split('\t')
            if len(d) < 30: continue
            
            def get_val(idx):
                return d[idx].strip().upper() if len(d) > idx and d[idx].strip() else ""
            
            if not info_cliente:
                info_cliente = {
                    "nombre": get_val(24), "calle": get_val(25), 
                    "colonia": get_val(26), "cp": get_val(27), "telefono": get_val(31)
                }
            
            pedidos_lista.append(get_val(4))
            productos_datos.append([get_val(6), get_val(7)]) # [Cantidad, Producto]

        if not pedidos_lista:
            print("Error: Selecciona la fila completa.")
            return

        num_guia_auto = obtener_siguiente_guia()
        pdf = FPDF()
        pdf.add_page()
        
        # --- ENCABEZADO ---
        pdf.set_draw_color(180, 180, 180)
        pdf.set_fill_color(245, 245, 245)
        pdf.set_font("Arial", 'B', 20)
        pdf.cell(190, 15, "GUIA DE ENVIO", border=1, ln=True, align='C', fill=True)
        
        pdf.set_font("Arial", 'B', 11)
        pedidos_str = " / ".join(pedidos_lista)
        pdf.cell(95, 10, f"PEDIDO: {pedidos_str}", border=1, ln=0, align='C')
        pdf.cell(95, 10, f"GUIA #: {num_guia_auto}", border=1, ln=1, align='C')
        
        # --- BLOQUE DE DIRECCIONES ---
        pdf.ln(8)
        pdf.set_text_color(0, 0, 0)
        pdf.set_font("Arial", 'B', 11)
        pdf.cell(95, 8, "REMITENTE", ln=0)
        pdf.cell(95, 8, "DESTINATARIO", ln=1)
        
        pdf.set_font("Arial", '', 10)
        y_dir = pdf.get_y()
        # Remitente Fijo
        pdf.set_xy(10, y_dir)
        pdf.multi_cell(90, 5, "CASA FERRO\nPLAYA REGATAS 391\nCOL. REFORMA IZTACCIHUATL NORTE\nCP 08810, CDMX")
        
        # Destinatario Dinámico (Sin "COL." si está vacío)
        dir_lines = [info_cliente['nombre'], info_cliente['calle']]
        if info_cliente['colonia']: 
            dir_lines.append(f"COL. {info_cliente['colonia']}")
        dir_lines.append(f"CP {info_cliente['cp']}")
        if info_cliente['telefono']: 
            dir_lines.append(f"TEL: {info_cliente['telefono']}")
            
        pdf.set_xy(105, y_dir)
        pdf.multi_cell(90, 5, "\n".join(dir_lines))

        # --- TABLA DE CONTENIDO (DINÁMICA) ---
        pdf.set_y(max(pdf.get_y(), y_dir + 35) + 5)
        pdf.set_font("Arial", 'B', 10)
        pdf.set_fill_color(245, 245, 245)
        pdf.cell(190, 8, "CONTENIDO DEL ENVIO", border=1, ln=1, align='L', fill=True)
        
        pdf.set_font("Arial", '', 10)
        pdf.set_fill_color(252, 252, 252)
        
        for item in productos_datos:
            texto_producto = item[1]
            # Calculamos altura necesaria
            num_lineas = len(pdf.multi_cell(165, 8, texto_producto, split_only=True))
            alto_fila = max(num_lineas * 8, 10)

            curr_x = pdf.get_x()
            curr_y = pdf.get_y()

            # Celda de Cantidad
            pdf.cell(25, alto_fila, item[0], border=1, align='C', fill=True)
            
            # Celda de Producto (sin la X)
            pdf.set_xy(curr_x + 25, curr_y)
            pdf.multi_cell(165, 8, texto_producto, border=1, align='L', fill=True)
            
            pdf.set_y(curr_y + alto_fila)
            pdf.ln(1)

        # --- SECCIÓN DE FIRMA ---
        pdf.set_y(-65)
        pdf.set_fill_color(245, 245, 245)
        pdf.set_font("Arial", 'B', 11)
        pdf.cell(190, 10, "  CONFIRMACION DE ENTREGA", border=1, ln=True, fill=True)
        
        pdf.set_font("Arial", '', 10)
        pdf.ln(4)
        pdf.cell(100, 10, "CANTIDAD DE PAQUETES: ________________", ln=0)
        pdf.cell(90, 10, "FECHA: ____ / ____ / ____", ln=1)
        pdf.ln(2)
        pdf.cell(190, 10, "NOMBRE Y FIRMA DE QUIEN RECIBE: ___________________________________________", ln=True)

        # Nombre de archivo solicitado: Pedido Guia Numero
        ped_name = "-".join(pedidos_lista).replace('$', '')
        nombre_archivo = f"{ped_name} Guia {num_guia_auto}.pdf"
        
        pdf.output(nombre_archivo)
        print(f"¡Guía {num_guia_auto} generada exitosamente!")

    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    crear_guia()