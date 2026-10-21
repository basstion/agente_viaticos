# Revisión de legalización {{legalizacion}}

- **Empleado:** {{empleado}}
- **Destino:** {{ciudad}} (Grupo {{grupo}})
- **Viaje:** {{salida}} a {{regreso}}
- **Política aplicada:** viáticos, versión {{version}}

| Id | Fecha | Categoría | Valor | Veredicto | Motivo |
|---|---|---|---|---|---|
{{filas}}

- **Gastos presentados:** {{presentados}}
- **Aprobados:** {{aprobados}}
- **Rechazados:** {{rechazados}}
- **Devueltos:** {{devueltos}}

**Total a reembolsar: {{total}}**

<!-- fin de la plantilla -->

Todo lo que está antes de la marca anterior es la plantilla que llena `scripts/validar.py`: el informe se entrega con este formato, sin texto antes ni después. Lo que sigue es la referencia del formato y no se imprime.

## Veredictos

- **Aprobado:** el gasto cumple la política. Se reconoce el valor completo.
- **Rechazado:** el gasto incumple la política. No se reconoce ningún valor. Un gasto que supera un tope se rechaza completo (política, sección 4).
- **Devuelto:** el gasto no se puede evaluar porque falta un dato o el dato no es válido. No se reconoce ningún valor hasta que el empleado lo corrija.

## Reglas del informe

- Un valor igual al tope está dentro del tope.
- Los gastos de hasta $30.000 COP no necesitan factura (política, sección 5).
- Los valores se escriben así: `$320.000 COP`.
- La columna **Motivo** cita la sección de la política. Queda vacía si el gasto se aprueba.
- El **Total a reembolsar** es la suma de los gastos aprobados.
