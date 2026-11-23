# Windows release acceptance / Validación para publicar en Windows

This checklist is for an interactive test on a clean Windows 10/11 user profile. The GitHub Actions build and automated smoke check do not exercise the tray, native window placement or image picker. No administrator rights or server setup should be needed. Record the tested commit, Windows version, display scaling, and any failure before calling a build a release.

Esta lista es para una prueba interactiva en un perfil limpio de Windows 10/11. La compilación y prueba automática de GitHub Actions no ejercitan la bandeja, la posición de ventanas ni el selector de imágenes. No deberían hacer falta permisos de administrador ni un servidor. Anota el commit, la versión de Windows, el escalado de pantalla y cualquier fallo antes de llamar «versión final» a un paquete.

## English

1. Download the Windows artifact from a successful [`main` CI run](https://github.com/santiagorestrepo14/Network_Weather/actions/workflows/ci.yml). Extract the entire archive; keep `NetworkWeather.exe` with its `_internal` directory. Exit any older Network Weather instance before opening this build.
2. Launch `NetworkWeather.exe --demo`. Confirm that all eight weather scenes cycle, every metric says `demo`, no real probe history is created in the clean profile, and custom image, image fit, effects and reduced motion controls respond. Verify that imported images survive exit and relaunch, and restoring an original image works.
3. Drag the compact widget, resize it from the lower-left corner, toggle always-on-top, hide it to the tray, restore it from the tray, and use **Exit**. Confirm the process ends. Reopen and confirm saved position, size, pin state and language. Repeat on a second display and at 125% or 150% display scaling if available.
4. Launch `NetworkWeather.exe` without `--demo`. Wait for at least four complete rounds at the configured interval. Check that DNS, TCP and HTTPS results identify actual destinations, units and failures. An initial **Unknown** state is expected until enough evidence has accumulated; a probe error must not appear as a measured latency.
5. Hide the widget to the tray for several intervals. Restore it and confirm that new real rounds were saved. Open History, inspect the last hour and a custom range, then exit and relaunch; the saved rounds and incidents must remain. Periods without observations must stay visually distinct.
6. Check startup with Windows: off by default; when enabled, it should register for the current user only, and disabling it should remove that registration. Verify that selecting **Exit** ends monitoring cleanly. If possible, test loss and restoration of network connectivity and sleep/resume without attributing an unsupported cause.

## Español

1. Descarga el artefacto Windows de una [ejecución correcta de la CI en `main`](https://github.com/santiagorestrepo14/Network_Weather/actions/workflows/ci.yml). Descomprime todo el archivo; conserva `NetworkWeather.exe` junto a `_internal`. Sal de cualquier copia anterior antes de abrir esta versión.
2. Abre `NetworkWeather.exe --demo`. Comprueba que se recorren los ocho climas, todas las métricas dicen `demo`, no se crea historial de sondas reales en el perfil limpio y responden los controles de imagen, ajuste, efectos y movimiento reducido. Verifica que las imágenes importadas sobreviven al cierre y reapertura, y que restaurar el fondo original funciona.
3. Arrastra el widget, cambia su tamaño desde la esquina inferior izquierda, activa y desactiva «siempre encima», ocúltalo en la bandeja, restáuralo y usa **Salir**. Confirma que termina el proceso. Vuelve a abrirlo y comprueba posición, tamaño, fijación e idioma guardados. Repite en un segundo monitor y con escalado de 125 % o 150 % si están disponibles.
4. Abre `NetworkWeather.exe` sin `--demo`. Espera al menos cuatro rondas completas según el intervalo configurado. Comprueba que los resultados DNS, TCP y HTTPS muestran destinos, unidades y fallos reales. Al principio puede aparecer **Desconocido** hasta reunir evidencia; un fallo de sonda no debe presentarse como latencia medida.
5. Oculta el widget en la bandeja durante varios intervalos. Restáuralo y comprueba que se guardaron rondas nuevas. Abre Historial, revisa la última hora y un rango personalizado, sal y vuelve a abrir: las rondas y los incidentes deben permanecer. Los periodos sin observaciones deben distinguirse visualmente.
6. Comprueba el inicio con Windows: desactivado por defecto; al activarlo debe registrarse solo para el usuario actual y al desactivarlo debe desaparecer ese registro. Verifica que **Salir** detiene el monitoreo. Si es posible, prueba pérdida y recuperación de red y suspensión/reanudación sin atribuir causas no demostradas.

This checklist is a gate, not evidence that these manual steps passed. Record actual outcomes before publishing a final release.

Esta lista es un criterio de aceptación, no evidencia de que las pruebas manuales hayan pasado. Registra los resultados reales antes de publicar una versión final.
