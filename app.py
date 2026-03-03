from datetime import datetime, timedelta, timezone
import time
import requests
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse, HTMLResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
import os
from generador_guias import (
    crear_guia_backend,
    anular_ultima_guia,
    obtener_info_cliente,
    obtener_pedidos_lista,
    supabase,
)
from skydropx_client import (
    cotizar_nacional,
    crear_envio,
    build_address_to_precheck,
    obtener_envio,
    obtener_labels_orden,
    obtener_labels_envio,
    diagnosticar_autenticacion,
    cancelar_envio,
)

app = FastAPI()
ESTADOS_VALIDOS = {
    "Generada",
    "Enviada a almacen",
    "Reimpresa",
    "Archivada",
    "Cancelacion solicitada",
    "Cancelada",
    "Cancelacion negada",
}
HISTORIAL_VENTANA_DIAS = 62

# Montamos la carpeta static para que puedas ver el index.html
app.mount("/static", StaticFiles(directory="static"), name="static")

class PedidoData(BaseModel):
    raw_text: str
    notas: str | None = None
    regenerar_num_guia: int | None = None  # si se envía, se regenera el PDF con ese número (sin incrementar)
    pedido: str | None = None
    parte: int | None = None
    total_partes: int | None = None
    confirmar_duplicado: bool = False

class CotizarData(BaseModel):
    raw_text: str
    weight_kg: float = 1.0
    length_cm: float = 20.0
    width_cm: float = 15.0
    height_cm: float = 10.0

class CrearEnvioSkydropxData(BaseModel):
    raw_text: str
    rate_id: str
    pedido: str | None = None
    parte: int | None = None
    total_partes: int | None = None
    confirmar_duplicado: bool = False
    address_override: dict | None = None


class PrevalidarSkydropxData(BaseModel):
    raw_text: str
    address_override: dict | None = None


class HistorialEstadoData(BaseModel):
    id: int
    estado: str


class HistorialDeleteData(BaseModel):
    id: int


class CancelarGuiaData(BaseModel):
    id: int
    razon: str = "Paquetería o servicio no deseado"


def _sanitize_pedido(pedido: str | None):
    val = (pedido or "").strip()
    return val


def _sanitize_parte(parte: int | None):
    return int(parte or 1)


def _pedido_historial_from_raw(raw_text: str, pedido_input: str | None):
    pedido_manual = _sanitize_pedido(pedido_input)
    if pedido_manual:
        return pedido_manual
    pedidos = obtener_pedidos_lista(raw_text or "")
    if not pedidos:
        return None
    if len(pedidos) == 1:
        return pedidos[0]
    if len(pedidos) == 2:
        return f"{pedidos[0]} y {pedidos[1]}"
    return f"{pedidos[0]} a {pedidos[-1]}"


def _filename_from_pedido_parte(pedido: str | None, parte: int | None, total_partes: int | None = None):
    pedido_val = _sanitize_pedido(pedido)
    parte_val = _sanitize_parte(parte)
    total_val = max(1, int(total_partes or 1))
    if not pedido_val:
        return None
    # Si el pedido tiene 2+ partes, siempre incluir "PARTE N", incluso para la parte 1.
    if total_val <= 1 and parte_val <= 1:
        return f"{pedido_val}.pdf"
    return f"{pedido_val} PARTE {parte_val}.pdf"


def _historial_desde_iso():
    dt = datetime.now(timezone.utc) - timedelta(days=HISTORIAL_VENTANA_DIAS)
    return dt.isoformat()


def _buscar_duplicado(pedido: str | None, parte: int | None, canal: str):
    pedido_val = _sanitize_pedido(pedido)
    parte_val = _sanitize_parte(parte)
    if not pedido_val:
        return None
    try:
        res = (
            supabase
            .table("guias_historial")
            .select("id,pedido,parte,canal,estado,created_at")
            .eq("pedido", pedido_val)
            .eq("parte", parte_val)
            .eq("canal", canal)
            .gte("created_at", _historial_desde_iso())
            .order("created_at", desc=True)
            .limit(1)
            .execute()
        )
        # Compatibilidad histórica: antes se guardaba como "pdf_privado".
        if (not res.data) and canal == "cflogistica":
            res = (
                supabase
                .table("guias_historial")
                .select("id,pedido,parte,canal,estado,created_at")
                .eq("pedido", pedido_val)
                .eq("parte", parte_val)
                .eq("canal", "pdf_privado")
                .gte("created_at", _historial_desde_iso())
                .order("created_at", desc=True)
                .limit(1)
                .execute()
            )
        if res.data and len(res.data) > 0:
            return res.data[0]
    except Exception:
        return None
    return None


def _registrar_historial(payload: dict):
    try:
        supabase.table("guias_historial").insert(payload).execute()
    except Exception:
        pass


def _first_non_empty(*values):
    for val in values:
        if val is None:
            continue
        txt = str(val).strip()
        if txt:
            return txt
    return None


def _as_float_or_none(value):
    try:
        if value is None:
            return None
        return float(str(value).replace(",", "").strip())
    except Exception:
        return None


def _extract_skydropx_fields(result: dict):
    result = result or {}
    data = result.get("data") if isinstance(result, dict) else {}
    attrs = data.get("attributes") if isinstance(data, dict) else {}
    included = result.get("included") if isinstance(result, dict) else []
    relationships = data.get("relationships") if isinstance(data, dict) else {}

    pkg_attrs = {}
    if isinstance(included, list):
        for item in included:
            if isinstance(item, dict) and item.get("type") == "package":
                pkg_attrs = item.get("attributes") or {}
                break

    label_url = _first_non_empty(
        result.get("label_url"),
        (result.get("label") or {}).get("url") if isinstance(result.get("label"), dict) else None,
        ((result.get("labels") or [{}])[0]).get("url") if isinstance(result.get("labels"), list) else None,
        pkg_attrs.get("label_url"),
        attrs.get("label_url"),
    )
    tracking_number = _first_non_empty(
        result.get("master_tracking_number"),
        attrs.get("master_tracking_number"),
        pkg_attrs.get("tracking_number"),
    )
    tracking_url = _first_non_empty(
        result.get("tracking_url_provider"),
        pkg_attrs.get("tracking_url_provider"),
        attrs.get("tracking_url_provider"),
    )
    costo_total = _as_float_or_none(
        _first_non_empty(
            result.get("total"),
            (result.get("rate") or {}).get("total") if isinstance(result.get("rate"), dict) else None,
            attrs.get("total"),
        )
    )
    shipment_id = _first_non_empty(result.get("id"), data.get("id") if isinstance(data, dict) else None)
    order_id = _first_non_empty(
        result.get("order_id"),
        attrs.get("order_id"),
        (relationships.get("order") or {}).get("data", {}).get("id") if isinstance(relationships, dict) else None,
        (result.get("data") or {}).get("order_id") if isinstance(result.get("data"), dict) else None,
    )
    label_urls = []
    label_urls_raw = (result.get("data") or {}).get("label_urls") if isinstance(result.get("data"), dict) else None
    if label_urls_raw is None and isinstance(attrs, dict):
        label_urls_raw = attrs.get("label_urls")
    if label_urls_raw is None:
        label_urls_raw = result.get("label_urls") if isinstance(result, dict) else None
    if isinstance(label_urls_raw, list):
        label_urls = [str(x).strip() for x in label_urls_raw if str(x or "").strip()]
        if not label_url and label_urls:
            label_url = label_urls[0]
    return {
        "shipment_id": shipment_id,
        "order_id": order_id,
        "label_urls": label_urls,
        "label_url": label_url,
        "tracking_number": tracking_number,
        "tracking_url": tracking_url,
        "costo_total": costo_total,
    }


def _resolve_skydropx_links(extracted: dict, max_attempts: int = 6, sleep_sec: float = 1.2):
    current = dict(extracted or {})
    for _ in range(max_attempts):
        if current.get("label_url") or current.get("tracking_url"):
            return current
        updated = dict(current)
        shipment_id = current.get("shipment_id")
        order_id = current.get("order_id")
        if shipment_id:
            try:
                latest = obtener_envio(shipment_id)
                latest_extracted = _extract_skydropx_fields(latest)
                updated["order_id"] = latest_extracted.get("order_id") or updated.get("order_id")
                updated["label_url"] = latest_extracted.get("label_url") or updated.get("label_url")
                updated["tracking_number"] = latest_extracted.get("tracking_number") or updated.get("tracking_number")
                updated["tracking_url"] = latest_extracted.get("tracking_url") or updated.get("tracking_url")
                if latest_extracted.get("costo_total") is not None:
                    updated["costo_total"] = latest_extracted.get("costo_total")
            except Exception:
                pass
            if not updated.get("label_url"):
                try:
                    labels_by_shipment = obtener_labels_envio(shipment_id)
                    labels_ship_extracted = _extract_skydropx_fields(labels_by_shipment)
                    if labels_ship_extracted.get("label_url"):
                        updated["label_url"] = labels_ship_extracted.get("label_url")
                except Exception:
                    pass
        order_id = updated.get("order_id") or order_id
        if order_id and not updated.get("label_url"):
            try:
                labels_result = obtener_labels_orden(order_id)
                labels_extracted = _extract_skydropx_fields(labels_result)
                if labels_extracted.get("label_url"):
                    updated["label_url"] = labels_extracted.get("label_url")
            except Exception:
                pass
        current = updated
        if current.get("label_url") or current.get("tracking_url"):
            break
        time.sleep(sleep_sec)
    return current

@app.get("/", response_class=HTMLResponse)
async def read_index():
    with open("static/index.html", "r", encoding="utf-8") as f:
        return f.read()


@app.get("/diagnostico-skydropx")
async def diagnostico_skydropx():
    try:
        return diagnosticar_autenticacion()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/generar-pdf")
async def generar_pdf(data: PedidoData):
    try:
        pedido_historial = _pedido_historial_from_raw(data.raw_text, data.pedido)
        dup = _buscar_duplicado(pedido_historial, data.parte, "cflogistica")
        if dup and not data.confirmar_duplicado:
            raise HTTPException(
                status_code=409,
                detail=f"duplicado|Pedido {dup.get('pedido')} parte {dup.get('parte')} ya existe en historial",
            )

        result = crear_guia_backend(
            data.raw_text,
            notas=data.notas,
            num_guia_fijo=data.regenerar_num_guia,
        )
        nombre_archivo, num_ya_generada = result
        if num_ya_generada is not None:
            raise HTTPException(status_code=409, detail=f"ya_generada|{num_ya_generada}")
        if nombre_archivo and os.path.exists(nombre_archivo):
            filename_sugerido = _filename_from_pedido_parte(pedido_historial, data.parte, data.total_partes) or nombre_archivo
            _registrar_historial(
                {
                    "pedido": pedido_historial,
                    "parte": _sanitize_parte(data.parte),
                    "canal": "cflogistica",
                    "estado": "Reimpresa" if data.regenerar_num_guia is not None else "Generada",
                    "archivo_nombre": filename_sugerido,
                    "archivo_ruta": nombre_archivo,
                    "label_url": None,
                    "override_duplicado": bool(dup and data.confirmar_duplicado),
                }
            )
            return FileResponse(
                nombre_archivo,
                media_type='application/pdf',
                filename=filename_sugerido,
                headers={"X-Filename": filename_sugerido},
            )
        raise HTTPException(status_code=500, detail="No se pudieron leer los datos. Asegúrate de pegar la fila completa desde Sheets.")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/anular-ultima-guia")
async def anular_ultima():
    try:
        if anular_ultima_guia():
            return {"ok": True, "mensaje": "Número de guía anulado. El próximo PDF usará el mismo número."}
        return {"ok": False, "mensaje": "No se puede anular (el contador ya está en 0)."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/cotizar-envio")
async def cotizar_envio(data: CotizarData):
    """Cotiza envío nacional con Skydropx. Parsea raw_text para obtener dirección destino."""
    try:
        info = obtener_info_cliente(data.raw_text)
        if not info:
            raise HTTPException(status_code=400, detail="No se pudo parsear la dirección. Pega la fila completa de Sheets.")
        address_to = {
            "postal_code": info.get("cp", ""),
            "area_level1": info.get("estado", ""),
            "area_level2": info.get("ciudad", ""),
            "area_level3": info.get("colonia", ""),
        }
        opciones = cotizar_nacional(
            address_to,
            data.weight_kg,
            data.length_cm,
            data.width_cm,
            data.height_cm,
        )
        return {"opciones": opciones}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/prevalidar-skydropx")
async def prevalidar_skydropx(data: PrevalidarSkydropxData):
    try:
        info = obtener_info_cliente(data.raw_text)
        if not info:
            raise HTTPException(status_code=400, detail="No se pudo parsear la dirección desde Sheets.")
        precheck = build_address_to_precheck(info, data.address_override or {})
        return precheck
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/crear-envio-skydropx")
async def crear_envio_skydropx(data: CrearEnvioSkydropxData):
    """Crea envío en Skydropx con el rate_id elegido. Parsea raw_text para dirección destino."""
    try:
        dup = _buscar_duplicado(data.pedido, data.parte, "skydropx")
        if dup and not data.confirmar_duplicado:
            raise HTTPException(
                status_code=409,
                detail=f"duplicado|Pedido {dup.get('pedido')} parte {dup.get('parte')} ya existe en historial",
            )

        info = obtener_info_cliente(data.raw_text)
        if not info:
            raise HTTPException(status_code=400, detail="No se pudo parsear la dirección. Pega la fila completa de Sheets.")

        precheck = build_address_to_precheck(info, data.address_override or {})
        if not precheck.get("valid"):
            raise HTTPException(status_code=422, detail={"mensaje": "Prevalidación fallida", "precheck": precheck})

        address_from = {
            "name": "Casa Ferro",
            "company": "Casa Ferro",
            "street1": "Playa Regatas 391",
            "city": "Ciudad de México",
            "state": "CDMX",
            "zip": "08810",
            "phone": "5578805661",
            "email": "logistica@casaferro.com",
            "reference": "Bodega Casa Ferro",
        }
        address_to = {
            "name": precheck.get("name", ""),
            "street1": precheck.get("street1", ""),
            "city": precheck.get("city", ""),
            "state": precheck.get("state", ""),
            "zip": precheck.get("postal_code", ""),
            "phone": precheck.get("phone", ""),
            "email": precheck.get("email", "") or "",
            "reference": precheck.get("reference", ""),
            "company": precheck.get("name", "") or "Cliente",
        }
        result = crear_envio(data.rate_id, address_from, address_to)
        filename_sugerido = _filename_from_pedido_parte(data.pedido, data.parte, data.total_partes)
        extracted = _extract_skydropx_fields(result)
        extracted = _resolve_skydropx_links(extracted)
        _registrar_historial(
            {
                "pedido": _sanitize_pedido(data.pedido) or None,
                "parte": _sanitize_parte(data.parte),
                "canal": "skydropx",
                "estado": "Generada",
                "archivo_nombre": filename_sugerido,
                "archivo_ruta": None,
                "shipment_id": extracted.get("shipment_id"),
                "label_url": extracted.get("label_url"),
                "tracking_number": extracted.get("tracking_number"),
                "tracking_url": extracted.get("tracking_url"),
                "costo_total": extracted.get("costo_total"),
                "override_duplicado": bool(dup and data.confirmar_duplicado),
            }
        )
        if filename_sugerido:
            result["filename_sugerido"] = filename_sugerido
        if extracted.get("label_url"):
            result["label_url"] = extracted.get("label_url")
        if extracted.get("tracking_number"):
            result["tracking_number"] = extracted.get("tracking_number")
        if extracted.get("tracking_url"):
            result["tracking_url"] = extracted.get("tracking_url")
        if extracted.get("costo_total") is not None:
            result["costo_total"] = extracted.get("costo_total")
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/historial-guias")
async def historial_guias(
    pedido: str | None = Query(default=None),
    estado: str | None = Query(default=None),
    limit: int = Query(default=300),
):
    try:
        q = (
            supabase.table("guias_historial")
            .select("*")
            .gte("created_at", _historial_desde_iso())
            .order("created_at", desc=True)
            .limit(max(1, min(limit, 1000)))
        )
        if pedido:
            q = q.ilike("pedido", f"%{pedido.strip()}%")
        if estado:
            q = q.eq("estado", estado.strip())
        res = q.execute()
        return {"rows": res.data or []}
    except Exception:
        return {"rows": []}


@app.post("/actualizar-estado-guia")
async def actualizar_estado_guia(data: HistorialEstadoData):
    try:
        estado = data.estado.strip()
        if estado not in ESTADOS_VALIDOS:
            raise HTTPException(status_code=400, detail=f"Estado inválido. Usa: {', '.join(sorted(ESTADOS_VALIDOS))}")
        supabase.table("guias_historial").update({"estado": estado}).eq("id", data.id).execute()
        return {"ok": True}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/eliminar-guia-historial")
async def eliminar_guia_historial(data: HistorialDeleteData):
    try:
        supabase.table("guias_historial").delete().eq("id", data.id).execute()
        return {"ok": True}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


def _extract_cancel_status(cancel_result: dict):
    payload = cancel_result or {}
    data = payload.get("data") if isinstance(payload, dict) else {}
    attrs = data.get("attributes") if isinstance(data, dict) else {}
    status = str(
        payload.get("status")
        or attrs.get("status")
        or data.get("status")
        or ""
    ).strip().lower()
    success_raw = payload.get("success")
    if success_raw is None:
        success_raw = attrs.get("success")
    if success_raw is None:
        success_raw = data.get("success")
    success = bool(success_raw) if success_raw is not None else False

    if success and status in {"approved", "cancelled", "canceled", "done"}:
        return "Cancelada"
    if status in {"rejected", "denied", "failed"}:
        return "Cancelacion negada"
    return "Cancelacion solicitada"


@app.post("/cancelar-guia-skydropx")
async def cancelar_guia_skydropx(data: CancelarGuiaData):
    try:
        res = (
            supabase
            .table("guias_historial")
            .select("*")
            .eq("id", data.id)
            .limit(1)
            .execute()
        )
        if not res.data:
            raise HTTPException(status_code=404, detail="Registro no encontrado.")
        row = res.data[0]
        if row.get("canal") != "skydropx":
            raise HTTPException(status_code=400, detail="Solo aplica para guías Skydropx.")

        shipment_ref = str(row.get("shipment_id") or row.get("tracking_number") or "").strip()
        if not shipment_ref:
            raise HTTPException(status_code=422, detail="No hay shipment_id/rastreo para cancelar esta guía.")

        cancel_result = cancelar_envio(shipment_ref, data.razon)
        estado_local = _extract_cancel_status(cancel_result)
        supabase.table("guias_historial").update({"estado": estado_local}).eq("id", data.id).execute()
        return {"ok": True, "estado": estado_local, "resultado": cancel_result}
    except HTTPException:
        raise
    except Exception as e:
        msg = str(e)
        if "Skydropx 422" in msg:
            raise HTTPException(status_code=422, detail="Cancelación negada por Skydropx (422).")
        if "Skydropx 404" in msg:
            raise HTTPException(status_code=404, detail="Envío no encontrado en Skydropx (404).")
        raise HTTPException(status_code=500, detail=msg)


@app.get("/descargar-pdf-local")
async def descargar_pdf_local(filename: str):
    try:
        name = os.path.basename(filename or "")
        if not name:
            raise HTTPException(status_code=400, detail="Filename inválido.")
        if not os.path.exists(name):
            raise HTTPException(status_code=404, detail="Archivo no encontrado en servidor.")
        return FileResponse(
            name,
            media_type="application/pdf",
            filename=name,
            headers={"X-Filename": name},
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/descargar-label-skydropx")
async def descargar_label_skydropx(url: str, filename: str | None = None):
    try:
        target = (url or "").strip()
        if not target:
            raise HTTPException(status_code=400, detail="URL requerida.")
        allowed = (
            target.startswith("https://pro.skydropx.com/")
            or target.startswith("https://sb-pro.skydropx.com/")
        )
        if not allowed:
            raise HTTPException(status_code=400, detail="URL de label no permitida.")

        r = requests.get(target, timeout=35)
        if r.status_code >= 400:
            raise HTTPException(status_code=502, detail=f"No se pudo descargar label ({r.status_code}).")

        safe_name = os.path.basename((filename or "").strip()) or "guia-skydropx.pdf"
        if not safe_name.lower().endswith(".pdf"):
            safe_name += ".pdf"
        media_type = r.headers.get("Content-Type", "application/pdf")
        return Response(
            content=r.content,
            media_type=media_type,
            headers={
                "Content-Disposition": f'attachment; filename="{safe_name}"',
                "X-Filename": safe_name,
            },
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/resolver-label-historial")
async def resolver_label_historial(id: int):
    try:
        res = (
            supabase
            .table("guias_historial")
            .select("*")
            .eq("id", id)
            .limit(1)
            .execute()
        )
        if not res.data:
            raise HTTPException(status_code=404, detail="Registro no encontrado.")
        row = res.data[0]
        if row.get("canal") != "skydropx":
            raise HTTPException(status_code=400, detail="Solo aplica para guías Skydropx.")

        extracted = {
            "shipment_id": row.get("shipment_id"),
            "order_id": None,
            "label_url": row.get("label_url"),
            "tracking_number": row.get("tracking_number"),
            "tracking_url": row.get("tracking_url"),
            "costo_total": row.get("costo_total"),
        }
        resolved = _resolve_skydropx_links(extracted, max_attempts=4, sleep_sec=1.0)

        update_payload = {
            "label_url": resolved.get("label_url"),
            "tracking_number": resolved.get("tracking_number"),
            "tracking_url": resolved.get("tracking_url"),
            "costo_total": resolved.get("costo_total"),
        }
        supabase.table("guias_historial").update(update_payload).eq("id", id).execute()
        return {"ok": True, "row": {**row, **update_payload}}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))