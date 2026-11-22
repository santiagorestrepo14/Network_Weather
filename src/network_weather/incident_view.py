"""Human-readable incident details from persisted measurements, without cause claims."""

from __future__ import annotations

from datetime import UTC, datetime

from network_weather.i18n import evidence_name, normalize_language, weather_name
from network_weather.weather import Weather


def format_incident(
    incident: dict, now: datetime | None = None, language: str = "es",
) -> str:
    """Show observed episode facts; keep cause unidentified unless diagnosed."""
    start = datetime.fromisoformat(incident["started_at"])
    finished = incident["ended_at"]
    end = datetime.fromisoformat(finished) if finished else (now or datetime.now(UTC))
    elapsed = max(0, int((end - start).total_seconds()))
    hours, remainder = divmod(elapsed, 3600)
    minutes, seconds = divmod(remainder, 60)
    weather = Weather(incident["weather"])
    language = normalize_language(language)
    if language == "en":
        lines = [
            f"Weather: {weather_name(weather, language)}",
            f"Status: {'Finished' if finished else 'Active'}",
            f"Start: {start.astimezone():%Y-%m-%d %H:%M:%S}",
            f"End: {end.astimezone():%Y-%m-%d %H:%M:%S}" if finished else "End: still active",
            f"Duration: {hours} h {minutes} min {seconds} s",
            f"Peak observed severity: {incident['severity']:.0%}",
            "Cause: undetermined", "", "Most recent evidence:",
        ]
    else:
        lines = [
            f"Fenómeno: {weather_name(weather, language)}",
            f"Estado: {'Finalizado' if finished else 'Activo'}",
            f"Inicio: {start.astimezone():%d/%m/%Y %H:%M:%S}",
            f"Fin: {end.astimezone():%d/%m/%Y %H:%M:%S}" if finished else "Fin: aún activo",
            f"Duración: {hours} h {minutes} min {seconds} s",
            f"Severidad máxima observada: {incident['severity']:.0%}",
            "Causa: no determinada", "", "Evidencias más recientes:",
        ]
    evidence = incident.get("evidence") or []
    if not evidence:
        lines.append("• No detailed evidence saved" if language == "en"
                     else "• No hay evidencias detalladas guardadas")
    for item in evidence:
        code = item.get("code")
        label = evidence_name(code, item.get("detail", "Evidence without description"), language)
        observed = item.get("observed")
        threshold = item.get("threshold")
        if observed is not None:
            if code in {"dns_failures", "response_failures", "multi_target_outage"}:
                value = f"{observed:.0%} {'of probes' if language == 'en' else 'de pruebas'}"
                bound = (f"; {'threshold' if language == 'en' else 'umbral'} {threshold:.0%}"
                         if threshold is not None else "")
            elif code in {"high_latency", "single_target_latency", "rtt_variation"}:
                value = f"{observed:.1f} ms"
                bound = (f"; {'threshold' if language == 'en' else 'umbral'} {threshold:.1f} ms"
                         if threshold is not None else "")
            else:
                value = str(observed)
                bound = (f"; {'threshold' if language == 'en' else 'umbral'} {threshold}"
                         if threshold is not None else "")
            label += f" ({value}{bound})"
        lines.append(f"• {label}")
    return "\n".join(lines)
