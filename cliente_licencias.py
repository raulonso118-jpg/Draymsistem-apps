"""Servicios de licencia y versión para el cliente Kivy.

Este módulo evita mezclar la comunicación HTTP y el almacenamiento local
con las pantallas de la aplicación. No contiene secretos del servidor.
"""
from __future__ import annotations

import json
import os
from typing import Any, Callable, Optional

from kivy.app import App
from kivy.network.urlrequest import UrlRequest

APP_VERSION = "1.0.0"
DEV_LICENSE = "GEN-DEV-MASTER-2026"


def _license_path() -> str:
    return os.path.join(App.get_running_app().user_data_dir, "licencia.json")


def load_license() -> str:
    try:
        with open(_license_path(), "r", encoding="utf-8") as file:
            value = json.load(file).get("licencia", "")
            return value.strip() if isinstance(value, str) else ""
    except (OSError, ValueError, TypeError):
        return ""


def save_license(value: str) -> bool:
    value = value.strip()
    if not value:
        return False
    try:
        os.makedirs(os.path.dirname(_license_path()), exist_ok=True)
        with open(_license_path(), "w", encoding="utf-8") as file:
            json.dump({"licencia": value}, file, ensure_ascii=False)
        return True
    except OSError:
        return False


def clear_license() -> None:
    try:
        os.remove(_license_path())
    except FileNotFoundError:
        pass
    except OSError:
        pass


def is_developer_license(value: str) -> bool:
    return value.strip() == DEV_LICENSE


def _url(app: App, endpoint: str) -> str:
    return f"{app.url_servidor.rstrip('/')}{endpoint}"


def validate_license(
    value: str,
    on_success: Callable[[dict[str, Any]], None],
    on_error: Callable[[str], None],
) -> Optional[UrlRequest]:
    """Valida una licencia contra el servidor configurado."""
    value = value.strip()
    if not value:
        on_error("Ingresa una licencia válida.")
        return None

    app = App.get_running_app()
    payload = json.dumps({"licencia": value})
    headers = {"Content-Type": "application/json"}

    def success(_request, result):
        if isinstance(result, dict) and result.get("estatus") == "ok":
            save_license(value)
            on_success(result)
        else:
            on_error((result or {}).get("mensaje", "Licencia inválida o expirada."))

    def failure(_request, result):
        message = result if isinstance(result, str) else "No se pudo contactar con el servidor."
        on_error(message)

    return UrlRequest(
        _url(app, "/api/validar_licencia"),
        req_body=payload,
        req_headers=headers,
        on_success=success,
        on_failure=failure,
        on_error=lambda _request, error: on_error(f"Error de conexión: {error}"),
        method="POST",
        timeout=30,
    )


def check_version(
    on_success: Callable[[dict[str, Any]], None],
    on_error: Callable[[str], None],
) -> Optional[UrlRequest]:
    """Consulta la versión del servidor sin bloquear el arranque de la app."""
    app = App.get_running_app()
    payload = json.dumps({"version": APP_VERSION, "licencia": app.licencia_activa})
    headers = {"Content-Type": "application/json"}

    def success(_request, result):
        if isinstance(result, dict):
            on_success(result)
        else:
            on_error("Respuesta de versión inválida.")

    return UrlRequest(
        _url(app, "/api/validar_version"),
        req_body=payload,
        req_headers=headers,
        on_success=success,
        on_failure=lambda _request, _error: on_error("No se pudo comprobar la versión."),
        on_error=lambda _request, error: on_error(f"Error comprobando versión: {error}"),
        method="POST",
        timeout=15,
    )
