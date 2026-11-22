"""Human-readable incident details from persisted measurements, without cause claims."""

from __future__ import annotations

from datetime import UTC, datetime

from network_weather.weather import Weather

WEATHER_NAMES = {
    Weather.SUNNY: "Soleado", Weather.CLOUDY: "Nublado",
    Weather.WINDY: "Ventoso", Weather.RAINY: "Lluvioso",
    Weather.FOGGY: "Neblina", Weather.STORMY: "Tormenta",
    Weather.OFFLINE: "Sin conexión", Weather.UNKNOWN: "Desconocido",
}

EVIDENCE_NAMES = {
    "gateway_echo_replied": "La puerta de enlace respondió al eco ICMP",
    "gateway_echo_unanswered": "La puerta de enlace no respondió al eco ICMP; podría filtrar estas pruebas",
    "multi_target_outage": "Varios destinos no respondieron a las pruebas TCP/HTTPS",
    "dns_failures": "Fallos de resolución DNS",
    "response_failures": "Fallos de respuesta TCP/HTTPS",
    "high_latency": "Latencia TCP elevada",
    "rtt_variation": "Variación elevada entre tiempos TCP comparables",
    "tls_errors": "Errores de verificación o negociación TLS",
    "conflicting_results": "Resultados contradictorios entre pruebas",
    "route_changed": "Cambió la ruta; la recuperación no quedó confirmada",
}


def format_incident(incident: dict, now: datetime | None = None) -> str:
    """Show observed episode facts; keep cause unidentified unless diagnosed."""
    start = datetime.fromisoformat(incident["started_at"])
    finished = incident["ended_at"]
    end = datetime.fromisoformat(finished) if finished else (now or datetime.now(UTC))
    elapsed = max(0, int((end - start).total_seconds()))
    hours, remainder = divmod(elapsed, 3600)
    minutes, seconds = divmod(remainder, 60)
    weather = Weather(incident["weather"])
    lines = [
        f"Fenómeno: {WEATHER_NAMES[weather]}",
        f"Estado: {'Finalizado' if finished else 'Activo'}",
        f"Inicio: {start.astimezone():%d/%m/%Y %H:%M:%S}",
        f"Fin: {end.astimezone():%d/%m/%Y %H:%M:%S}" if finished else "Fin: aún activo",
        f"Duración: {hours} h {minutes} min {seconds} s",
        f"Severidad máxima observada: {incident['severity']:.0%}",
        "Causa: no determinada",
        "",
        "Evidencias más recientes:",
    ]
    evidence = incident.get("evidence") or []
    if not evidence:
        lines.append("• No hay evidencias detalladas guardadas")
    for item in evidence:
        label = EVIDENCE_NAMES.get(item.get("code"), item.get("detail", "Evidencia sin descripción"))
        code = item.get("code")
        observed = item.get("observed")
        threshold = item.get("threshold")
        if observed is not None:
            if code in {"dns_failures", "response_failures", "multi_target_outage"}:
                value = f"{observed:.0%} de pruebas"
                bound = f"; umbral {threshold:.0%}" if threshold is not None else ""
            elif code in {"high_latency", "rtt_variation"}:
                value = f"{observed:.1f} ms"
                bound = f"; umbral {threshold:.1f} ms" if threshold is not None else ""
            else:
                value = str(observed)
                bound = f"; umbral {threshold}" if threshold is not None else ""
            label += f" ({value}{bound})"
        lines.append(f"• {label}")
    return "\n".join(lines)
