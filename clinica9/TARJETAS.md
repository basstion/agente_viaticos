# Tarjetas de síntomas

Cada tarjeta cuenta lo que ve un usuario. La causa la encuentras tú.

## Avería 1 · No arranca
Ejecuto `python clinica9/servidor.py` y el servidor no arranca: sale un error
en rojo y se cierra.

## Avería 2 · Se queda pensando
El servidor ya arranca. Abro la página, escribo la clave `altiplano-demo-2026`,
hago clic en **Ver reporte** y la página se queda en "Cargando…" para siempre.

## Avería 3 · La clave no sirve
Ahora la página responde, pero dice **"Clave incorrecta"**. Estoy seguro de que
la clave es `altiplano-demo-2026`: la copié de esta tarjeta.

## Avería 4 · Error del servidor
Con la clave correcta, la página dice "Error del servidor. Revisa la terminal
donde corre el servidor."

## Avería 5 · Las cuentas no cuadran
El reporte ya sale completo. Pero Natalia Guzmán viajó a Medellín del 3 al 5 de
noviembre y el reporte le reconoce $160.000 de alimentación. Tesorería dice que
deberían ser $240.000.

## Bonus · El log de producción
Lee `log_produccion.txt`. Tiene tres errores. Para cada uno: ¿es culpa del
código, de la configuración o de un servicio externo? ¿Cuál arreglarías tú
cambiando código?
