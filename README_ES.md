# Network Weather

Aplicación de escritorio para Windows que representa el estado de Internet como clima. **Estado actual: versión de desarrollo.** Contiene sondas, reglas meteorológicas, historial SQLite, CLI, widget, bandeja, panel expandido y ocho escenas procedurales. Todavía faltan funciones y pulido visual para la primera publicación. Las capturas de referencia son maquetas: sus cifras no son datos de esta aplicación.

## Arquitectura prevista

`probes` realiza pruebas DNS, TCP y HTTPS; `collector` reúne una ronda; `metrics` calcula estadísticas de muestras comparables. Las siguientes etapas añadirán línea base, reglas meteorológicas y evidencias, almacenamiento SQLite y finalmente interfaz PySide6. La lógica de red permanecerá independiente de la ventana.

## Instalación y uso (PowerShell, Python 3.12+)

```powershell
cd .\NetworkWeather
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev,desktop]"
network-weather --once
network-weather-desktop --demo
network-weather-desktop
python -m pytest
python -m ruff check .
```

`network-weather --once` guarda una ronda y su clasificación en `%LOCALAPPDATA%\NetworkWeather\history.db`. Sin `--once`, emite una ronda JSON por línea cada 30 segundos. `--raw --once` realiza sondas sin guardar historial. `--destination` es repetible, pero la clasificación permanece «desconocido» si solo hay un destino. `Ctrl+C` termina. El intervalo permitido es de 5 a 3600 segundos y el timeout TCP/HTTPS de 0,2 a 30 segundos.

`network-weather-desktop` abre el widget y empieza a medir en un hilo separado. El botón central abre el panel, el botón de minimizar lo oculta en la bandeja y **Salir** en el menú de bandeja detiene el hilo. El cierre del widget también lo oculta. `--demo` recorre los ocho climas sin hacer sondas ni escribir muestras; todas las tarjetas muestran «demo». La posición, fijación, imágenes y preferencias se guardan en `%LOCALAPPDATA%\NetworkWeather\settings.ini`.

Vista actual del widget en modo demostración: ![Widget de tormenta, versión de desarrollo](docs/widget-demo-v2.png)

## Qué se mide

Cada ronda consulta por defecto `example.com` y `www.wikipedia.org`. Para cada destino hace una resolución DNS del sistema, una conexión TCP al puerto 443 y una solicitud HTTPS `HEAD /` con TLS verificado. Es una solicitud pequeña; no descarga el cuerpo. Una respuesta HTTP válida, incluso 4xx/5xx, confirma conectividad HTTP y conserva el código recibido. El usuario puede cambiar los destinos con `--destination` (repetible). No se modifica la configuración de red.

Las duraciones de sondas fallidas son `null`. La latencia TCP excluye la resolución DNS; la duración HTTPS abarca TCP, TLS y respuesta HTTP. `metrics.summarize` calcula mediana, porcentaje de pruebas fallidas y variación de RTT como el promedio de diferencias absolutas entre éxitos consecutivos del mismo destino y protocolo. No representa jitter unidireccional. Las estadísticas de tráfico del adaptador son contadores locales; su `speed_mbps` es velocidad negociada del enlace, no velocidad de Internet.

## Límites actuales

- La resolución DNS usa el resolvedor de Windows, que puede responder desde caché y controla su propio timeout. Por ello su tiempo no mide siempre una consulta remota y un bloqueo largo del resolvedor puede prolongar una ronda.
- Los sockets registran su dirección IP local y se compara con los adaptadores. `route_adapter` queda `null` si no hay correspondencia única, por ejemplo con IPv6, VPN o varias interfaces. Falta registrar puerta de enlace y cambios de ruta con mayor detalle.
- No se hacen pruebas ICMP ni se infiere pérdida de paquetes IP de fallos TCP/HTTPS. El porcentaje de fallos siempre pertenece a un protocolo y destino concretos.
- Si DNS falla, no se crean resultados ficticios de TCP o HTTPS. Tampoco se infiere conexión estable cuando faltan muestras.
- La clasificación exige tres rondas, dos destinos y dos clasificaciones candidatas consecutivas para cambiar de clima. Los incidentes quedan abiertos durante resultados desconocidos y cierran tras dos rondas soleadas. La causa permanece sin atribuir.
- El motor de clima aún usa umbrales iniciales conservadores. Falta validar su comportamiento con conjuntos de datos reales de varios tipos de conexión antes de considerarlo diagnóstico definitivo.
- El panel muestra las últimas rondas e incidentes, pero aún faltan filtros de tiempo, gráficas históricas completas, puerta de enlace, Wi-Fi detallado, idioma inglés en la interfaz y una evaluación de confianza específica para causas. No se atribuye ninguna causa a un proveedor.
- Los ocho fondos predeterminados son ilustraciones propias creadas para este proyecto. Qt dibuja encima los efectos de lluvia, viento, niebla y relámpagos, que pueden apagarse sin perder la imagen. Cada clima acepta una imagen PNG, JPG o WebP de hasta 10 MB y 4096 px, copiada al área de datos sin modificar el original.
- Existe un ZIP de vista previa para Windows generado con PyInstaller. Abre `NetworkWeather.exe --demo` para revisar las escenas o `NetworkWeather.exe` para sondear la red. El paquete aún necesita validación en un Windows limpio antes de considerarse instalador público.

## Secuencia

1. **A:** modelos, sondas, métricas básicas, CLI y pruebas.
2. **B:** línea base, reglas de clima, diagnóstico explicable, incidentes e historial SQLite.
3. **C:** widget, bandeja y panel PySide6 con monitoreo fuera del hilo gráfico (base funcional).
4. **D:** ocho escenas, animaciones y personalización segura de imágenes (base funcional; pulido pendiente).
5. **E:** integración, pruebas en Windows, documentación completa, CI y ejecutable.

La publicación en GitHub se hará cuando el proyecto esté listo y el usuario indique el repositorio de destino.
