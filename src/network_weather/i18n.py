"""Small, explicit Spanish/English presentation catalog."""

from __future__ import annotations

from network_weather.models import ProbeStatus
from network_weather.weather import Weather

WEATHER_NAMES = {
    "es": {
        Weather.SUNNY: "Soleado", Weather.CLOUDY: "Nublado",
        Weather.WINDY: "Ventoso", Weather.RAINY: "Lluvioso",
        Weather.FOGGY: "Neblina", Weather.STORMY: "Tormenta",
        Weather.OFFLINE: "Sin conexión", Weather.UNKNOWN: "Desconocido",
    },
    "en": {
        Weather.SUNNY: "Clear", Weather.CLOUDY: "Cloudy",
        Weather.WINDY: "Windy", Weather.RAINY: "Rain",
        Weather.FOGGY: "Fog", Weather.STORMY: "Storm",
        Weather.OFFLINE: "Offline", Weather.UNKNOWN: "Unknown",
    },
}

WEATHER_DESCRIPTIONS = {
    "es": {
        Weather.SUNNY: "Conexión estable observada",
        Weather.CLOUDY: "Latencia elevada sostenida",
        Weather.WINDY: "Variación de latencia elevada",
        Weather.RAINY: "Fallos de respuesta intermitentes",
        Weather.FOGGY: "Problemas de resolución DNS",
        Weather.STORMY: "Degradación combinada",
        Weather.OFFLINE: "Sin respuesta de varios destinos",
        Weather.UNKNOWN: "Esperando evidencia suficiente",
    },
    "en": {
        Weather.SUNNY: "Stable connection observed",
        Weather.CLOUDY: "Sustained high latency",
        Weather.WINDY: "High latency variation",
        Weather.RAINY: "Intermittent response failures",
        Weather.FOGGY: "DNS resolution problems",
        Weather.STORMY: "Combined degradation",
        Weather.OFFLINE: "Multiple destinations not responding",
        Weather.UNKNOWN: "Waiting for enough evidence",
    },
}

EVIDENCE_NAMES = {
    "es": {
        "gateway_echo_replied": "La puerta de enlace respondió al eco ICMP",
        "gateway_echo_unanswered": "La puerta de enlace no respondió al eco ICMP; podría filtrar estas pruebas",
        "multi_target_outage": "Varios destinos no respondieron a las pruebas TCP/HTTPS",
        "dns_failures": "Fallos de resolución DNS",
        "response_failures": "Fallos de respuesta TCP/HTTPS",
        "high_latency": "Latencia TCP elevada",
        "single_target_latency": "Latencia TCP elevada en un solo destino",
        "rtt_variation": "Variación elevada entre tiempos TCP comparables",
        "tls_errors": "Errores de verificación o negociación TLS",
        "conflicting_results": "Resultados contradictorios entre pruebas",
        "route_changed": "Cambió la ruta; la recuperación no quedó confirmada",
        "observation_gap": "Se interrumpió el monitoreo; la recuperación no quedó confirmada",
        "direct_ip_tcp_replied": "Respondió una conexión TCP directa a la IP configurada",
        "insufficient_rounds": "Se necesitan al menos tres rondas",
        "missing_protocol": "Faltan pruebas DNS, TCP o HTTPS",
        "single_destination": "Se necesitan al menos dos destinos",
        "sparse_samples": "Cobertura insuficiente de las pruebas",
        "all_probes_ok": "DNS, TCP y HTTPS respondieron en varios destinos",
    },
    "en": {
        "gateway_echo_replied": "Local gateway answered ICMP echo",
        "gateway_echo_unanswered": "Gateway did not answer ICMP; it may filter echo requests",
        "multi_target_outage": "Multiple targets did not respond to TCP/HTTPS probes",
        "dns_failures": "DNS resolution failures",
        "response_failures": "TCP/HTTPS response failures",
        "high_latency": "High TCP latency",
        "single_target_latency": "High TCP latency toward one target only",
        "rtt_variation": "High variation between comparable TCP times",
        "tls_errors": "TLS verification or handshake errors",
        "conflicting_results": "Conflicting probe results",
        "route_changed": "Route changed; recovery was not confirmed",
        "observation_gap": "Monitoring was interrupted; recovery was not confirmed",
        "direct_ip_tcp_replied": "Direct TCP connection to the configured IP succeeded",
        "insufficient_rounds": "At least three rounds are required",
        "missing_protocol": "DNS, TCP and HTTPS evidence is required",
        "single_destination": "At least two targets are required",
        "sparse_samples": "Insufficient probe coverage",
        "all_probes_ok": "DNS, TCP and HTTPS responded across multiple targets",
    },
}

PROBE_STATUS_NAMES = {
    "es": {
        ProbeStatus.SUCCESS: "correcto", ProbeStatus.DNS_ERROR: "error DNS",
        ProbeStatus.TCP_ERROR: "error TCP", ProbeStatus.TLS_ERROR: "error TLS",
        ProbeStatus.HTTP_ERROR: "error HTTP", ProbeStatus.ICMP_ERROR: "error ICMP",
        ProbeStatus.TIMEOUT: "tiempo agotado",
    },
    "en": {
        ProbeStatus.SUCCESS: "success", ProbeStatus.DNS_ERROR: "DNS error",
        ProbeStatus.TCP_ERROR: "TCP error", ProbeStatus.TLS_ERROR: "TLS error",
        ProbeStatus.HTTP_ERROR: "HTTP error", ProbeStatus.ICMP_ERROR: "ICMP error",
        ProbeStatus.TIMEOUT: "timeout",
    },
}

EN = {
    "Fijar encima de otras ventanas": "Keep above other windows",
    "Abrir panel": "Open dashboard",
    "Ocultar en la bandeja": "Hide to tray",
    "●  Monitoreo activo": "●  Monitoring live",
    "●  Monitoreo activo · datos reales": "●  Monitoring live · real measurements",
    "Latencia": "Latency",
    "Variación": "Variation",
    "Fallos TCP": "TCP failures",
    "Historial TCP · muestras por ronda": "TCP history · samples by round",
    "Puerta de enlace": "Gateway",
    "Conectividad externa": "External connectivity",
    "Historial de red · última hora": "Network history · last hour",
    "Incidente activo": "Active incident",
    "Explicación técnica": "Technical explanation",
    "Sin datos observados todavía.": "No observations yet.",
    "Sin evidencias concluyentes todavía.": "No conclusive evidence yet.",
    "Sin incidentes activos.": "No active incidents.",
    "Severidad": "Severity",
    "Correcto": "Healthy",
    "Con fallos": "Failures",
    "Responde": "Responding",
    "Sin respuesta": "No reply",
    "Confirmada": "Confirmed",
    "Sin confirmar": "Unconfirmed",
    "Resumen": "Overview",
    "Diagnóstico": "Diagnostics",
    "Historial": "History",
    "Incidentes": "Incidents",
    "Configuración": "Settings",
    "Resumen de la conexión": "Connection overview",
    "Esperando las primeras mediciones…": "Waiting for the first measurements…",
    "Confianza: —   Severidad: —": "Confidence: —   Severity: —",
    "Las evidencias aparecerán tras tres rondas.": "Evidence will appear after three rounds.",
    "Diagnóstico técnico": "Technical diagnostics",
    "Esperando muestras comparables…": "Waiting for comparable samples…",
    "Destino": "Destination",
    "Protocolo": "Protocol",
    "Intentos": "Attempts",
    "Éxitos": "Successes",
    "Mediana": "Median",
    "Fallos": "Failures",
    "Última ronda y contexto de red": "Latest round and network context",
    "P95: rango más cercano entre éxitos. Variación: diferencias entre tiempos consecutivos del mismo destino y protocolo; no es jitter unidireccional.":
        "P95: nearest rank among successes. Variation: differences between consecutive times for the same target and protocol; not one-way jitter.",
    "Esperando pruebas DNS, TCP y HTTPS…": "Waiting for DNS, TCP and HTTPS probes…",
    "Historial observado": "Observed history",
    "Última hora": "Last hour",
    "24 horas": "24 hours",
    "7 días": "7 days",
    "30 días": "30 days",
    "Personalizado": "Custom",
    "Todos los destinos": "All targets",
    "Actualizar": "Refresh",
    "Abre el historial para consultar los datos guardados.": "Open History to view saved data.",
    " · gris: sin observación": " · gray: unobserved",
    " · límite de rondas alcanzado": " · round limit reached",
    "No hay incidentes registrados.": "No incidents recorded.",
    "Abre Incidentes para consultar los episodios guardados.": "Open Incidents to view saved episodes.",
    "Movimiento reducido": "Reduced motion",
    "Efectos meteorológicos": "Weather effects",
    "Ajuste de imagen": "Image fit",
    "Mediciones · los cambios se aplican al reiniciar": "Probes · changes apply after restart",
    " días": " days",
    "Intervalo": "Interval",
    "Retención del historial": "History retention",
    "Destinos HTTPS (separados por comas)": "HTTPS targets (comma-separated)",
    "Prueba TCP directa sin DNS": "Direct TCP probe without DNS",
    "Opcional: IP pública con TCP/443": "Optional: public IP with TCP/443",
    "Guardar mediciones": "Save probe settings",
    "Iniciar con Windows": "Start with Windows",
    "La ruta actual es demasiado larga para el inicio de Windows.":
        "The current path is too long for Windows startup.",
    "La ruta registrada corresponde a otra instalación. Desactiva y activa para actualizarla.":
        "The registered path points to another installation. Turn this off and on to update it.",
    "Apariencia → Climas": "Appearance → Weather",
    "Seleccionar imagen…": "Choose image…",
    "Original": "Reset",
    "Destinos no válidos": "Invalid targets",
    "Guardado": "Saved",
    "Las nuevas sondas se usarán al reiniciar Network Weather.":
        "New probe settings will apply after restarting Network Weather.",
    "No disponible": "Unavailable",
    "Esta opción requiere Windows.": "This option requires Windows.",
    "No se pudo configurar": "Could not configure",
    "Imágenes (*.png *.jpg *.jpeg *.webp)": "Images (*.png *.jpg *.jpeg *.webp)",
    "Imagen no válida": "Invalid image",
    "No se pudo leer el archivo seleccionado.": "Could not read the selected file.",
    "Usa PNG, JPG o WebP de 64–4096 px y hasta 10 MB.":
        "Use PNG, JPG or WebP, 64–4096 px and up to 10 MB.",
    "¿Aplicar esta imagen al clima seleccionado?": "Apply this image to the selected weather state?",
    "Error": "Error",
    "No se pudo guardar la imagen importada.": "Could not save the imported image.",
    "No identificado": "Not identified",
    "No identificada": "Not identified",
    "sin latencia válida": "no valid latency",
    "Activo": "Active",
    "Finalizado": "Finished",
    "Network Weather · iniciando": "Network Weather · starting",
    "Mostrar widget": "Show widget",
    "Salir": "Exit",
    "●  MODO DEMOSTRACIÓN · sin mediciones reales":
        "●  DEMO MODE · no real measurements",
    "El inicio debe ser anterior al fin.": "Start must be before end.",
    "Consultando historial…": "Loading history…",
    "Network Weather · error de medición": "Network Weather · probe error",
    "Escena visual sintética. No hay pruebas de red ni historial.":
        "Synthetic visual scene. No network probes or history.",
    "Cierre pendiente": "Waiting to exit",
    "La consulta del historial aún no termina.": "The history query is still running.",
    "Una prueba de red aún no termina. Intenta salir de nuevo.":
        "A network probe is still running. Try exiting again.",
    "No se pudo crear la instancia única.": "Could not create the single application instance.",
    "Clima observado": "Observed weather",
    "Latencia TCP promedio por intervalo (ms)": "Average TCP latency per interval (ms)",
    "Selecciona un periodo para consultar el historial": "Select a period to view history",
    "Sin observaciones en este periodo": "No observations in this period",
    "Idioma": "Language",
    "Reinicia Network Weather para aplicar el idioma.":
        "Restart Network Weather to apply the language.",
}


def normalize_language(value: object) -> str:
    return value if value in ("es", "en") else "es"


def translate(message: str, language: str) -> str:
    return EN.get(message, message) if language == "en" else message


def weather_name(weather: Weather, language: str) -> str:
    return WEATHER_NAMES[normalize_language(language)][weather]


def weather_description(weather: Weather, language: str) -> str:
    return WEATHER_DESCRIPTIONS[normalize_language(language)][weather]


def evidence_name(code: str, fallback: str, language: str) -> str:
    label = EVIDENCE_NAMES[normalize_language(language)].get(code, fallback)
    if code in {"high_latency", "single_target_latency"} and " toward " in fallback:
        label += f" ({fallback.rsplit(' toward ', 1)[1]})"
    return label


def probe_status_name(status: ProbeStatus, language: str) -> str:
    return PROBE_STATUS_NAMES[normalize_language(language)][status]
