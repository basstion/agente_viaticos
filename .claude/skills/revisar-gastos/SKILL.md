---
name: revisar-gastos
description: "Revisa una legalización de gastos de viaje (un CSV como datos/legalizacion_L-2031.csv) contra la política de viáticos y entrega un informe con un veredicto por gasto (Aprobado, Rechazado o Devuelto) y el total a reembolsar. Úsala cuando pidan revisar, auditar o validar una legalización de viáticos o gastos de viaje."
---

# Revisar una legalización de gastos de viaje

## Cuándo usarla

Cuando el usuario pida revisar, auditar o validar una legalización de gastos de viaje y entregue (o indique) el CSV. Si no indica cuál, pídele la ruta.

## Pasos

1. Ejecuta el script con la ruta del CSV:

   ```
   python .claude/skills/revisar-gastos/scripts/validar.py <ruta del CSV>
   ```

   El script aplica la política (`referencia/politica_viaticos.md`), decide el veredicto de cada gasto, calcula el total y llena `plantilla_informe.md`.

2. Muestra el informe que imprime el script **tal cual**. No cambies cifras, veredictos ni motivos. Si el script falla, muestra el error y no improvises una revisión.

3. Después del informe, agrega una sección **Notas del revisor** con lo que el script no puede juzgar. Incluye solo las que apliquen a esta legalización:

   - **Tiquetes aéreos:** que se compraron en clase económica, por la agencia de la empresa y con mínimo 7 días de anticipación (el CSV no trae esos datos).
   - **Hospedaje:** que el hotel sea de máximo 4 estrellas.
   - **Facturas:** que estén a nombre de Altiplano S.A.S. (el script solo verifica que exista el número).
   - **Plazo:** que se legalizó dentro de los 5 días hábiles siguientes al regreso (el CSV no trae la fecha de legalización).
   - **Aprobaciones:** aprobación previa del jefe inmediato y, si hubo excesos, autorización escrita del director emitida antes del viaje.
   - **Otros gastos:** que parqueaderos, peajes o papelería tengan relación con el motivo del viaje.
   - **Descripciones:** el script detecta los gastos no reembolsables (sección 6) por palabras clave; lee las descripciones de los gastos aprobados por si alguno se le escapó.

   Si no aplica ninguna nota, escribe "Sin notas".
