# Reglas para procesar el lote de legalizaciones

**Altiplano S.A.S.** (empresa ficticia para uso académico) · Área de Contabilidad

Cada viernes Contabilidad recibe un archivo con las legalizaciones de gastos de viaje que los empleados enviaron por el formulario. Hoy alguien las revisa una por una. Queremos un script que haga ese trabajo y entregue un reporte listo para actuar.

Lote de esta semana: `legalizaciones_octubre.csv`, con gastos del **28 de septiembre al 9 de octubre de 2026**.

## 1. Qué hace el código y qué hace la IA

| Tarea | Quién la hace | Por qué |
|---|---|---|
| Limpiar fechas, valores y ciudades | Código | Es exacto y siempre da el mismo resultado |
| Encontrar duplicados | Código | Igual |
| Clasificar la descripción en una categoría | Gemini | Es texto libre: cada empleado escribe distinto |
| Decidir si se aprueba, se rechaza o se revisa | Código | Es comparar números contra topes |
| Redactar el mensaje para el empleado | Gemini | Es redacción |

## 2. Limpieza

- **Fechas.** El formulario acepta tres formatos: `2026-10-05`, `05/10/2026` y `5 oct 2026`. Las fechas con barras siempre son día/mes/año. En el reporte van como `AAAA-MM-DD`.
- **Valores.** Son pesos colombianos enteros, sin centavos. Los puntos, las comas, los espacios, el signo `$` y la palabra `COP` son solo formato: `$ 320.000 COP` es 320000.
- **Ciudades.** Lleva cada ciudad al nombre exacto que aparece en `topes_por_ciudad.csv`. Corrige mayúsculas, tildes, espacios sobrantes, nombres largos (por ejemplo, "Bogotá, D.C.") y errores evidentes de escritura. El archivo trae las siete ciudades a las que viaja Altiplano; una ciudad que no esté ahí va a revisión.
- **Duplicados.** Dos filas son la misma legalización si, **después de limpiar**, coinciden el empleado, la fecha, la ciudad, la descripción y el valor. El radicado no cuenta. Se conserva la primera fila y las demás van a la lista de duplicadas: no se aprueban ni se rechazan.

## 3. Categorías

Cada fila es el total de un concepto en un día, o una noche de hotel.

| Categoría | Qué incluye |
|---|---|
| `alimentacion` | Desayunos, almuerzos, cenas, refrigerios |
| `hospedaje` | Noches de hotel o alojamiento |
| `transporte_terrestre` | Taxis, aplicaciones de transporte, bus, metro, traslados urbanos |
| `tiquetes_aereos` | Tiquetes de avión |
| `no_reembolsable` | Bebidas alcohólicas, propinas, minibar, multas de tránsito, entretenimiento personal, gastos de acompañantes |
| `otro` | Todo lo demás: parqueaderos, peajes, papelería, lavandería. También cualquier descripción que mezcle dos conceptos |

La lavandería va en `otro` porque solo se reembolsa en viajes de 5 noches o más, y el lote no trae la duración del viaje.

## 4. Decisión

Aplica las reglas en este orden. La primera que se cumpla decide.

| # | Si... | Decisión |
|---|---|---|
| 1 | Falta el valor, la fecha no existe, la fecha está fuera del periodo del lote o la ciudad no está en `topes_por_ciudad.csv` | **Por revisar** |
| 2 | La categoría es `no_reembolsable` | **Rechazada** |
| 3 | La categoría es `alimentacion`, `hospedaje` o `transporte_terrestre` y el valor supera el tope de esa ciudad | **Rechazada** |
| 4 | El valor es mayor a 1.500.000 COP | **Por revisar** (requiere aprobación del director del área) |
| 5 | La categoría es `otro` | **Por revisar** |
| 6 | Ninguna de las anteriores | **Aprobada** |

Un valor igual al tope se aprueba. Los tiquetes aéreos no tienen tope, pero sí les aplica la regla 4.

"Por revisar" significa que una persona debe mirar la fila. Equivale al estado Pendiente de `gastos.csv`.

## 5. El reporte

El script escribe `reporte.md` en la raíz del proyecto, con estas partes:

1. **Resumen:** número de filas y total en COP de aprobadas, rechazadas y por revisar, y número de duplicadas. En "por revisar" se suman solo las filas que tienen valor.
2. **Aprobadas:** tabla con radicado, fecha, empleado, ciudad, categoría y valor.
3. **Rechazadas:** la misma tabla, más el motivo de cada una.
4. **Por revisar:** la misma tabla, más el motivo de cada una.
5. **Duplicadas:** radicado, empleado, valor y a qué fila repite.
6. **Mensajes:** un mensaje breve por cada empleado con rechazos, que nombre sus radicados y el motivo.

Al terminar, el script imprime una línea con los totales, en este formato:

```
A <filas> / <total> - R <filas> / <total> - P <filas> / <total> - D <filas>
```

Por ejemplo: `A 20 / 3.150.000 - R 5 / 800.000 - P 4 / 650.000 - D 1`. Esa es la línea que vas a pegar en el chat de la clase.
