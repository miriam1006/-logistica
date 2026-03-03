import os
import time
import requests
from dotenv import load_dotenv
import re

load_dotenv()

# Configuración de URLs y Tokens
SKYDROPX_BASE = os.getenv("SKYDROPX_BASE_URL", "https://pro.skydropx.com").rstrip("/")
SKYDROPX_BEARER_TOKEN = os.getenv("SKYDROPX_BEARER_TOKEN", "").strip()
SKYDROPX_CLIENT_ID = os.getenv("SKYDROPX_CLIENT_ID", "").strip()
SKYDROPX_CLIENT_SECRET = os.getenv("SKYDROPX_CLIENT_SECRET", "").strip()
SKYDROPX_CONSIGNMENT_NOTE = os.getenv("SKYDROPX_CONSIGNMENT_NOTE", "53102400").strip()
SKYDROPX_PACKAGE_TYPE = os.getenv("SKYDROPX_PACKAGE_TYPE", "4G").strip()
MAX_STREET1_LEN = 45
MAX_REFERENCE_LEN = 40
TOKEN_REFRESH_MARGIN_SEC = 60

_oauth_cache = {
    "access_token": None,
    "expires_at": 0,
}

# Origen fijo para cotización
ADDRESS_FROM_QUOTATION = {
    "country_code": "MX",
    "postal_code": "08810",
    "area_level1": "Ciudad de México",
    "area_level2": "Iztacalco",
    "area_level3": "Reforma Iztaccihuatl Norte",
}


def _clean(value, fallback):
    text = str(value or "").strip()
    return text if text else fallback


def _only_digits(value):
    return "".join(ch for ch in str(value or "") if ch.isdigit())


def _truncate(text, limit):
    val = str(text or "").strip()
    return val[:limit] if len(val) > limit else val


def _compact_spaces(text):
    return re.sub(r"\s+", " ", str(text or "")).strip()


def _abbreviate_street(text):
    val = _compact_spaces(text)
    replacements = {
        "CALLE ": "C. ",
        "AVENIDA ": "AV. ",
        "DEPARTAMENTO ": "DEP. ",
        "INTERIOR ": "INT. ",
    }
    upper_val = val.upper()
    for src, dst in replacements.items():
        if upper_val.startswith(src):
            return dst + val[len(src):]
    return val


def _parse_street_and_reference(street_raw):
    """
    Separa calle/base y referencia con prioridad a 'Entre:' cuando exista.
    Ejemplo:
      'Calle Topacio... Referencia: ... Entre: Turquesa y Calle 7'
      -> street1: 'C. Topacio ...'
      -> reference: 'Entre Turquesa y Calle 7'
    """
    raw = _compact_spaces(street_raw)
    lower = raw.lower()
    idx_ref = lower.find("referencia:")
    idx_ent = lower.find("entre:")

    split_indexes = [idx for idx in [idx_ref, idx_ent] if idx >= 0]
    first_marker = min(split_indexes) if split_indexes else -1
    base = raw[:first_marker].strip(" -,:") if first_marker >= 0 else raw

    referencia_txt = ""
    entre_txt = ""
    if idx_ref >= 0:
        after_ref = raw[idx_ref + len("referencia:"):].strip(" -,:")
        # Si aparece "Entre:" después de referencia, corta ahí.
        idx_ent_in_ref = after_ref.lower().find("entre:")
        if idx_ent_in_ref >= 0:
            referencia_txt = after_ref[:idx_ent_in_ref].strip(" -,:")
        else:
            referencia_txt = after_ref
    if idx_ent >= 0:
        entre_txt = raw[idx_ent + len("entre:"):].strip(" -,:")

    reference = ""
    if entre_txt:
        reference = f"Entre {entre_txt}"
    elif referencia_txt:
        reference = referencia_txt

    street1 = _truncate(_abbreviate_street(base), MAX_STREET1_LEN)
    reference = _truncate(_compact_spaces(reference), MAX_REFERENCE_LEN)
    return street1, reference


def build_address_to_precheck(info_cliente, overrides=None):
    overrides = overrides or {}
    street_raw = overrides.get("street_raw", info_cliente.get("calle", ""))
    street1_suggested, ref_suggested = _parse_street_and_reference(street_raw)

    street1 = _truncate(
        _compact_spaces(overrides.get("street1", street1_suggested)),
        MAX_STREET1_LEN,
    )
    reference = _truncate(
        _compact_spaces(overrides.get("reference", ref_suggested)),
        MAX_REFERENCE_LEN,
    )
    postal_code = _only_digits(overrides.get("postal_code", info_cliente.get("cp", "")))[:5]
    phone = _only_digits(overrides.get("phone", info_cliente.get("telefono", "")))
    state = _compact_spaces(overrides.get("state", info_cliente.get("estado", "")))
    city = _compact_spaces(overrides.get("city", info_cliente.get("ciudad", "")))
    colony = _compact_spaces(overrides.get("colony", info_cliente.get("colonia", "")))
    name = _compact_spaces(overrides.get("name", info_cliente.get("nombre", "")))
    email = _compact_spaces(overrides.get("email", info_cliente.get("email", "")))

    errors = {}
    if not street1:
        errors["street1"] = "Requerido"
    if len(street1) > MAX_STREET1_LEN:
        errors["street1"] = f"Máximo {MAX_STREET1_LEN} caracteres"
    if not postal_code or len(postal_code) != 5:
        errors["postal_code"] = "Debe tener 5 dígitos"
    if not phone or len(phone) < 10:
        errors["phone"] = "Mínimo 10 dígitos"
    if not state:
        errors["state"] = "Requerido"
    if not city:
        errors["city"] = "Requerido"
    if not colony:
        errors["colony"] = "Requerido"

    precheck = {
        "street_raw": street_raw,
        "street1": street1,
        "reference": reference,
        "postal_code": postal_code,
        "phone": phone,
        "state": state,
        "city": city,
        "colony": colony,
        "name": name or "CLIENTE",
        "email": email or "cliente@example.com",
        "valid": len(errors) == 0,
        "errors": errors,
        "limits": {"street1": MAX_STREET1_LEN, "reference": MAX_REFERENCE_LEN},
    }
    return precheck


def _get_token(force_oauth=False):
    """
    Prioridad:
      1) OAuth client_credentials automático con SKYDROPX_CLIENT_ID/SECRET.
      2) SKYDROPX_BEARER_TOKEN fijo (manual) como respaldo.
    """
    has_oauth = bool(SKYDROPX_CLIENT_ID and SKYDROPX_CLIENT_SECRET)
    if not force_oauth and not has_oauth and SKYDROPX_BEARER_TOKEN:
        return SKYDROPX_BEARER_TOKEN

    if not has_oauth:
        if SKYDROPX_BEARER_TOKEN:
            return SKYDROPX_BEARER_TOKEN
        raise ValueError(
            "Configura SKYDROPX_BEARER_TOKEN o bien SKYDROPX_CLIENT_ID + SKYDROPX_CLIENT_SECRET en .env"
        )

    now = int(time.time())
    cached_token = _oauth_cache.get("access_token")
    expires_at = int(_oauth_cache.get("expires_at") or 0)
    if cached_token and now < (expires_at - TOKEN_REFRESH_MARGIN_SEC):
        return cached_token

    token_url = f"{SKYDROPX_BASE}/api/v1/oauth/token"
    resp = requests.post(
        token_url,
        data={
            "grant_type": "client_credentials",
            "client_id": SKYDROPX_CLIENT_ID,
            "client_secret": SKYDROPX_CLIENT_SECRET,
        },
        headers={"Content-Type": "application/x-www-form-urlencoded", "Accept": "application/json"},
        timeout=20,
    )
    if resp.status_code >= 400:
        detail = resp.text.strip() or resp.reason
        # Fallback operativo: si OAuth falla (invalid_client, etc.) y existe bearer manual, usarlo.
        if SKYDROPX_BEARER_TOKEN:
            return SKYDROPX_BEARER_TOKEN
        raise ValueError(f"Skydropx {resp.status_code} al obtener token OAuth: {detail}")
    data = resp.json() if resp.content else {}
    token = data.get("access_token")
    if not token:
        if SKYDROPX_BEARER_TOKEN:
            return SKYDROPX_BEARER_TOKEN
        raise ValueError(f"Skydropx OAuth sin access_token: {data}")
    expires_in = int(data.get("expires_in") or 7200)
    _oauth_cache["access_token"] = token
    _oauth_cache["expires_at"] = now + expires_in
    return token


def _request(method, path, token, json=None, _retry_on_401=True):
    url = f"{SKYDROPX_BASE}/api/v1/{path}"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    response = requests.request(method, url, headers=headers, json=json, timeout=30)
    # Si usamos OAuth automático y expira entre llamadas, forzar una renovación y reintentar una vez.
    if (
        response.status_code == 401
        and _retry_on_401
        and token != SKYDROPX_BEARER_TOKEN
        and SKYDROPX_CLIENT_ID
        and SKYDROPX_CLIENT_SECRET
    ):
        _oauth_cache["access_token"] = None
        _oauth_cache["expires_at"] = 0
        fresh_token = _get_token(force_oauth=True)
        return _request(method, path, fresh_token, json=json, _retry_on_401=False)

    if response.status_code >= 400:
        detail = response.text.strip() or response.reason or "Error desconocido"
        raise ValueError(f"Skydropx {response.status_code}: {detail}")
    return response.json() if response.content else {}


def _short_error_text(response):
    txt = (response.text or "").strip()
    if not txt:
        return response.reason
    return txt[:300]


def cotizar_nacional(address_to, weight_kg, length_cm, width_cm, height_cm):
    cp = _only_digits(address_to.get("postal_code", ""))[:5]
    if len(cp) != 5:
        raise ValueError("El código postal destino debe tener 5 dígitos.")

    token = _get_token()
    body = {
        "quotation": {
            "address_from": ADDRESS_FROM_QUOTATION,
            "address_to": {
                "country_code": "MX",
                "postal_code": cp,
                "area_level1": _clean(address_to.get("area_level1"), "Estado de México"),
                "area_level2": _clean(address_to.get("area_level2"), "Toluca"),
                "area_level3": _clean(address_to.get("area_level3"), "Centro"),
            },
            "parcels": [
                {
                    "length": max(1, int(float(length_cm))),
                    "width": max(1, int(float(width_cm))),
                    "height": max(1, int(float(height_cm))),
                    "weight": max(0.1, float(weight_kg)),
                }
            ],
        }
    }

    quotation = _request("POST", "quotations", token, body)
    quotation_id = quotation.get("id")
    if not quotation_id:
        raise ValueError(f"Skydropx no devolvió id de cotización: {quotation}")

    result = quotation
    for _ in range(12):
        if result.get("is_completed"):
            break
        time.sleep(1.5)
        result = _request("GET", f"quotations/{quotation_id}", token)

    rates = result.get("rates") or []
    opciones = []
    for rate in rates:
        if not rate.get("success"):
            continue
        opciones.append(
            {
                "id": rate.get("id"),
                "carrier": rate.get("provider_display_name") or rate.get("provider_name") or "Paquetería",
                "service": rate.get("provider_service_name") or "",
                "total": rate.get("total") or rate.get("amount") or "0",
                "currency": rate.get("currency_code") or "MXN",
                "days": rate.get("days"),
            }
        )
    return opciones


def crear_envio(rate_id, address_from_full, address_to_full):
    token = _get_token()
    body = {
        "shipment": {
            "rate_id": rate_id,
            "address_from": {
                "street1": _clean(address_from_full.get("street1"), "Playa Regatas 391"),
                "name": _clean(address_from_full.get("name"), "Casa Ferro"),
                "company": _clean(address_from_full.get("company"), "Casa Ferro"),
                "phone": _clean(address_from_full.get("phone"), "5500000000"),
                "email": _clean(address_from_full.get("email"), "logistica@casaferro.com"),
                "reference": _clean(address_from_full.get("reference"), "Bodega Casa Ferro"),
            },
            "address_to": {
                "street1": _clean(address_to_full.get("street1"), "SIN CALLE"),
                "name": _clean(address_to_full.get("name"), "CLIENTE"),
                "company": _clean(address_to_full.get("company"), "CLIENTE"),
                "phone": _clean(address_to_full.get("phone"), "5500000000"),
                "email": _clean(address_to_full.get("email"), "cliente@example.com"),
                "reference": _clean(address_to_full.get("reference"), "SIN REFERENCIA"),
            },
            "packages": [
                {
                    "package_number": "1",
                    "consignment_note": _clean(SKYDROPX_CONSIGNMENT_NOTE, "53102400"),
                    "package_type": _clean(SKYDROPX_PACKAGE_TYPE, "4G"),
                }
            ],
        }
    }
    return _request("POST", "shipments", token, body)


def obtener_envio(shipment_id):
    shipment_id = str(shipment_id or "").strip()
    if not shipment_id:
        raise ValueError("shipment_id requerido")
    token = _get_token()
    return _request("GET", f"shipments/{shipment_id}", token)


def obtener_labels_orden(order_id):
    order_id = str(order_id or "").strip()
    if not order_id:
        raise ValueError("order_id requerido")
    token = _get_token()
    return _request("GET", f"orders/{order_id}/labels", token)


def obtener_labels_envio(shipment_id):
    shipment_id = str(shipment_id or "").strip()
    if not shipment_id:
        raise ValueError("shipment_id requerido")
    token = _get_token()
    return _request("GET", f"shipments/{shipment_id}/labels", token)


def cancelar_envio(shipment_id, reason="Paquetería o servicio no deseado"):
    shipment_id = str(shipment_id or "").strip()
    if not shipment_id:
        raise ValueError("shipment_id requerido")
    token = _get_token()
    body = {"reason": str(reason or "Paquetería o servicio no deseado").strip()}
    return _request("POST", f"shipments/{shipment_id}/cancellations", token, body)


def diagnosticar_autenticacion():
    """
    Diagnóstico no destructivo de autenticación:
    - Verifica OAuth client_credentials.
    - Verifica bearer manual por introspect (si hay client credentials).
    """
    out = {
        "base_url": SKYDROPX_BASE,
        "oauth_client_credentials": {"ok": False, "status": "not_configured"},
        "bearer_token": {"configured": bool(SKYDROPX_BEARER_TOKEN), "active": None, "status": "not_configured"},
        "modo_sugerido": "none",
    }

    has_oauth = bool(SKYDROPX_CLIENT_ID and SKYDROPX_CLIENT_SECRET)
    if has_oauth:
        token_url = f"{SKYDROPX_BASE}/api/v1/oauth/token"
        resp = requests.post(
            token_url,
            data={
                "grant_type": "client_credentials",
                "client_id": SKYDROPX_CLIENT_ID,
                "client_secret": SKYDROPX_CLIENT_SECRET,
            },
            headers={"Content-Type": "application/x-www-form-urlencoded", "Accept": "application/json"},
            timeout=20,
        )
        if resp.status_code < 400:
            data = resp.json() if resp.content else {}
            access_token = data.get("access_token")
            out["oauth_client_credentials"] = {
                "ok": bool(access_token),
                "status": "ok" if access_token else "missing_access_token",
                "http_status": resp.status_code,
            }
        else:
            out["oauth_client_credentials"] = {
                "ok": False,
                "status": "error",
                "http_status": resp.status_code,
                "detail": _short_error_text(resp),
            }

    if SKYDROPX_BEARER_TOKEN and has_oauth:
        introspect_url = f"{SKYDROPX_BASE}/api/v1/oauth/introspect"
        resp = requests.post(
            introspect_url,
            data={
                "client_id": SKYDROPX_CLIENT_ID,
                "client_secret": SKYDROPX_CLIENT_SECRET,
                "token": SKYDROPX_BEARER_TOKEN,
                "token_type_hint": "access_token",
            },
            headers={"Content-Type": "application/x-www-form-urlencoded", "Accept": "application/json"},
            timeout=20,
        )
        if resp.status_code < 400:
            data = resp.json() if resp.content else {}
            out["bearer_token"] = {
                "configured": True,
                "active": bool(data.get("active")),
                "status": "ok" if data.get("active") else "inactive",
                "http_status": resp.status_code,
            }
        else:
            out["bearer_token"] = {
                "configured": True,
                "active": None,
                "status": "error",
                "http_status": resp.status_code,
                "detail": _short_error_text(resp),
            }
    elif SKYDROPX_BEARER_TOKEN and not has_oauth:
        out["bearer_token"] = {
            "configured": True,
            "active": None,
            "status": "unknown_without_client_credentials",
        }

    if out["oauth_client_credentials"].get("ok"):
        out["modo_sugerido"] = "oauth_client_credentials"
    elif out["bearer_token"].get("configured"):
        out["modo_sugerido"] = "bearer_token"

    return out