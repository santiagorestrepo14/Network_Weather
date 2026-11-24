# Guía de uso · Network Weather

Network Weather es una aplicación local para Windows 10/11. El ZIP de vista previa es portátil: extrae la carpeta completa y ejecuta `NetworkWeather.exe`. Para instalarlo desde el código fuente, sigue [README_ES.md](../README_ES.md). La aplicación no necesita una cuenta ni un servidor propio.

## Primer inicio

La aplicación mide por defecto `example.com` y `www.wikipedia.org` cada 30 segundos. En cada ronda intenta DNS, TCP/443 y una solicitud HTTPS `HEAD /` con TLS verificado. Una prueba directa a una IP pública es opcional y viene desactivada.

Al principio puedes ver **Desconocido** aunque las tarjetas ya muestren cifras. El motor necesita al menos tres rondas, dos destinos y una segunda clasificación candidata consecutiva antes de cambiar de clima. El texto bajo el clima muestra el avance o la confirmación pendiente. Si persiste «Desconocido», abre **Panel → Diagnóstico** para ver las pruebas y evidencias.

`NetworkWeather.exe --demo` recorre los ocho climas sin hacer sondas ni guardar mediciones. Las tarjetas indican que son datos de demostración.

## Widget y panel

- Arrastra la barra superior para mover el widget; arrastra la esquina inferior izquierda para cambiar su tamaño. Ambos valores se recuerdan.
- El botón de fijación mantiene el widget encima de otras ventanas hasta que lo desactives.
- El botón de panel abre **Resumen, Diagnóstico, Historial, Incidentes y Configuración**.
- Minimizar o cerrar el widget lo oculta en la bandeja y el monitoreo continúa. Usa el icono de bandeja para restaurarlo; elige **Salir** para detener las mediciones y cerrar la aplicación.
- En el widget puedes elegir **Latencia** o **Variación** para la gráfica compacta. Muestra muestras reales y sus horas; no rellena huecos sin mediciones.

**Resumen** muestra el clima principal, señales adicionales confirmadas, tarjetas observadas, la última hora, el incidente activo y la explicación técnica. **Diagnóstico** separa destinos y protocolos, con intentos, éxitos, mediana, P95, variación y fallos. **Historial** ofrece una hora, 24 horas, siete días, 30 días y un rango personalizado. **Incidentes** conserva el inicio, fin, duración, severidad y evidencias disponibles.

## Configuración

| Control | Valor inicial y efecto |
|---|---|
| Idioma | Español; también English. Reinicia la aplicación para aplicarlo. |
| Intervalo | 30 segundos; admite de 5 a 3600 segundos. Reinicia para aplicar. |
| Destinos | `example.com, www.wikipedia.org`; admite de 1 a 8 dominios separados por comas. Se necesitan al menos dos para clasificar el clima. Reinicia para aplicar. |
| Prueba TCP directa sin DNS | Vacía/desactivada. Admite una IP pública que responda en TCP/443; no se usa como destino DNS. Reinicia para aplicar. |
| Retención del historial | 30 días; admite de 1 a 3650 días. Se limpia al iniciar y después cada hora. Reinicia para aplicar el nuevo plazo. |
| Iniciar con Windows | Desactivado. Si lo activas, registra solo una entrada para tu usuario de Windows. |
| Movimiento reducido y efectos meteorológicos | Se pueden cambiar independientemente y se aplican de inmediato. |
| Ajuste de imagen | `cover` llena el área, `contain` muestra toda la imagen y `center` la centra sin deformarla. |

En **Apariencia → Climas** hay una fila para cada uno de los ocho fenómenos. Pulsa **Seleccionar imagen…**, revisa la vista previa y confirma. **Original** restaura el fondo incluido. Se admiten PNG, JPG y WebP de hasta 10 MB y 4096 píxeles por dimensión; la aplicación valida y copia el archivo a `%LOCALAPPDATA%\NetworkWeather\images` sin modificar el original. Los efectos animados siguen siendo independientes del fondo elegido. La configuración y el historial se guardan en `%LOCALAPPDATA%\NetworkWeather`.

## Significado de los climas

| Clima | Lectura técnica |
|---|---|
| Soleado | Las pruebas DNS, TCP y HTTPS respondieron en varios destinos sin degradación suficiente para otro estado. |
| Nublado | Tiempo de conexión TCP elevado en al menos dos destinos. |
| Ventoso | Variación elevada entre tiempos TCP comparables; no es una medición de jitter unidireccional. |
| Lluvioso | Fallos de respuesta TCP/HTTPS intermitentes en rondas repetidas; no representa pérdida de paquetes IP medida. |
| Neblina | Fallos de resolución DNS, con comprobaciones adicionales cuando hay conectividad por otra ruta. |
| Tormenta | Combinación de dos o más degradaciones observadas; el resumen muestra señales adicionales. |
| Sin conexión | Dos rondas completas sin respuesta TCP ni HTTPS de todos los destinos configurados, sujetas a la confirmación general del motor. |
| Desconocido | Muestras insuficientes, incompletas o contradictorias. No equivale a conexión estable. |

La confianza del clima mide el respaldo de la clasificación; la severidad mide la magnitud observada. La confianza en una causa se muestra por separado y queda «no establecida» cuando las sondas no permiten identificarla. La aplicación no asigna automáticamente una causa al proveedor. Una puerta de enlace que no contesta ICMP puede filtrar ecos aunque Internet funcione. Consulta [la arquitectura](ARCHITECTURE.md) para el flujo interno y [la guía de empaquetado](PACKAGING.md) para reproducir el ejecutable.
