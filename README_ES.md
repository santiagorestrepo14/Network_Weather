# Network Weather

Aplicación de escritorio para Windows que representa el estado de Internet como clima. **Estado actual: versión de desarrollo.** Contiene sondas, reglas meteorológicas, historial SQLite, CLI, widget, bandeja, panel expandido y ocho escenas procedurales. Todavía faltan funciones y pulido visual para la primera publicación. Las capturas de referencia son maquetas: sus cifras no son datos de esta aplicación.

## Arquitectura

`probes` realiza pruebas DNS, TCP y HTTPS; `collector` reúne una ronda; `metrics` calcula estadísticas de muestras comparables. `weather` clasifica con reglas y evidencias, `history` guarda rondas e incidentes en SQLite y `desktop` presenta los datos con PySide6. Las sondas y las consultas del historial se ejecutan en hilos separados del gráfico.

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

`network-weather-desktop` abre el widget y empieza a medir en un hilo separado. El botón central abre el panel, el botón de minimizar lo oculta en la bandeja y **Salir** en el menú de bandeja detiene el hilo. El cierre del widget también lo oculta. El historial permite elegir una hora, 24 horas, 7 días, 30 días o un rango personalizado y filtrar la latencia TCP por destino. La franja de clima muestra estados categóricos observados; el gráfico inferior promedia solo latencias TCP válidas por intervalo y deja visibles los periodos sin observación. La consulta SQLite se realiza fuera del hilo gráfico. `--demo` recorre los ocho climas sin hacer sondas ni escribir muestras; todas las tarjetas muestran «demo». La posición, fijación, imágenes y preferencias se guardan en `%LOCALAPPDATA%\NetworkWeather\settings.ini`.

La gráfica del widget compacto permite elegir **Latencia** o **Variación** y recuerda la elección. Su eje horizontal usa las horas reales de las últimas 30 rondas, incluidas las guardadas antes de abrir la aplicación. Cada punto de latencia promedia los éxitos TCP de la ronda. La variación compara cada destino con su valor en la ronda inmediatamente anterior y promedia esas diferencias absolutas; los fallos y las pausas largas cortan la comparación. Las muestras ausentes quedan sin punto y no se unen por una línea.

Si la posición guardada del widget queda fuera de las pantallas disponibles (por ejemplo, al desconectar un monitor), la aplicación lo devuelve al área visible al abrirlo.

En **Configuración → Idioma**, elige Español o English. La preferencia se aplica al reiniciar la aplicación y se conserva para las siguientes sesiones. Los mensajes técnicos devueltos por Windows o por un servidor externo pueden aparecer en el idioma original de ese sistema.

Vista actual del widget en modo demostración: ![Widget de tormenta, versión de desarrollo](docs/widget-demo-v2.png)

## Qué se mide

Cada ronda consulta por defecto `example.com` y `www.wikipedia.org`. Para cada destino hace una resolución DNS del sistema, una conexión TCP al puerto 443 y una solicitud HTTPS `HEAD /` con TLS verificado. Es una solicitud pequeña; no descarga el cuerpo. Una respuesta HTTP válida, incluso 4xx/5xx, confirma conectividad HTTP y conserva el código recibido. El usuario puede cambiar los destinos con `--destination` (repetible). No se modifica la configuración de red.

Las duraciones de sondas fallidas son `null`. La latencia TCP excluye la resolución DNS; la duración HTTPS abarca TCP, TLS y respuesta HTTP. `metrics.summarize` calcula mediana, porcentaje de pruebas fallidas y variación de RTT como el promedio de diferencias absolutas entre éxitos consecutivos del mismo destino y protocolo. No representa jitter unidireccional. Las estadísticas de tráfico del adaptador son contadores locales; su `speed_mbps` es velocidad negociada del enlace, no velocidad de Internet.

En Windows, el diagnóstico puede mostrar calidad de señal Wi‑Fi (%), RSSI (dBm) y canal de interfaces inalámbricas conectadas cuando Native Wi‑Fi los proporciona. La consulta se guarda en caché durante 60 segundos y no realiza escaneos ni solicita SSID/BSSID. La interfaz Wi‑Fi mostrada no se identifica automáticamente como la ruta de las sondas; los campos no disponibles quedan ausentes. La consulta de calidad en tiempo real puede no estar disponible en algunas versiones de Windows y entonces se intentan únicamente RSSI y canal. Esta información local no se usa para afirmar una causa de los problemas de Internet. [API de calidad de Microsoft](https://learn.microsoft.com/en-us/windows/win32/api/wlanapi/ne-wlanapi-wlan_intf_opcode), [privacidad y ubicación](https://learn.microsoft.com/en-us/windows/win32/nativewifi/wi-fi-access-location-changes).

## Límites actuales

- La resolución DNS usa el resolvedor de Windows, que puede responder desde caché y controla su propio timeout. Por ello su tiempo no mide siempre una consulta remota y un bloqueo largo del resolvedor puede prolongar una ronda.
- Los sockets registran su dirección IP local IPv4 o IPv6 y se compara con los adaptadores. `route_adapter` queda `null` si no hay correspondencia única, por ejemplo con algunas VPN o varias interfaces. Al cambiar la interfaz identificada, el motor reinicia su ventana de clasificación.
- Windows informa la puerta de enlace IPv4 del adaptador mediante una consulta de solo lectura, almacenada durante cinco minutos. Si se identifica, la aplicación envía un eco ICMP por ronda. Registra únicamente si recibió respuesta: no inventa un tiempo RTT. La ausencia de eco puede deberse a filtrado y por sí sola no demuestra una falla local.
- No se infiere pérdida de paquetes IP de fallos TCP/HTTPS. El porcentaje de fallos siempre pertenece a un protocolo y destino concretos.
- Si DNS falla, no se crean resultados ficticios de TCP o HTTPS. Tampoco se infiere conexión estable cuando faltan muestras.
- La clasificación exige tres rondas, dos destinos y dos clasificaciones candidatas consecutivas para cambiar de clima. Los incidentes quedan abiertos durante resultados desconocidos y cierran tras dos rondas soleadas. La causa permanece sin atribuir.
- «Sin conexión» requiere dos rondas completas sin respuesta TCP ni HTTPS de todos los destinos configurados. Una respuesta DNS, que puede venir de caché, no descarta ese estado; un fallo aislado, una prueba ausente o un error TLS tampoco lo confirman. La latencia se compara con una línea base propia de cada destino y la latencia alta de un único destino no se presenta como degradación general.
- El motor de clima aún usa umbrales iniciales conservadores. Falta validar su comportamiento con conjuntos de datos reales de varios tipos de conexión antes de considerarlo diagnóstico definitivo.
- El panel muestra historial por rango, latencia TCP por destino, puerta de enlace, datos Wi‑Fi disponibles e incidentes con inicio, fin, duración, severidad y evidencias. Todavía falta una evaluación de confianza específica para causas. No se atribuye ninguna causa a un proveedor.
- Los ocho fondos predeterminados son ilustraciones propias creadas para este proyecto. Qt dibuja encima los efectos de lluvia, viento, niebla y relámpagos, que pueden apagarse sin perder la imagen. Cada clima acepta una imagen PNG, JPG o WebP de hasta 10 MB y 4096 px, copiada al área de datos sin modificar el original.
- Existe un ZIP de vista previa para Windows generado con PyInstaller. Abre `NetworkWeather.exe --demo` para revisar las escenas o `NetworkWeather.exe` para sondear la red. El paquete aún necesita validación en un Windows limpio antes de considerarse instalador público.

## Secuencia

1. **A:** modelos, sondas, métricas básicas, CLI y pruebas.
2. **B:** línea base, reglas de clima, diagnóstico explicable, incidentes e historial SQLite.
3. **C:** widget, bandeja y panel PySide6 con monitoreo fuera del hilo gráfico (base funcional).
4. **D:** ocho escenas, animaciones y personalización segura de imágenes (base funcional; pulido pendiente).
5. **E:** integración, pruebas en Windows, documentación completa, CI y ejecutable.

La publicación en GitHub se hará cuando el proyecto esté listo y el usuario indique el repositorio de destino.
