# Reglas para una solicitud de viáticos

Altiplano S.A.S. · Política de viáticos 2.0

Una solicitud se radica **antes** de viajar. Trae siete datos:

| Dato | Ejemplo |
|---|---|
| Empleado | Natalia Guzmán |
| Ciudad de destino | Cartagena |
| Fecha de salida | 2026-11-03 |
| Noches | 2 |
| Motivo | Feria comercial |
| Valor por noche del hotel cotizado | 310000 |
| Valor del tiquete | 690000 |

**Costo estimado** = valor del tiquete + noches × valor por noche.

## Reglas, en orden

Se revisan de arriba hacia abajo. **La primera que se cumple decide el estado** y las demás ya no se miran.

| # | Regla | Estado |
|---|---|---|
| 1 | La ciudad no está en `ciudades.csv` (incluye viajes fuera de Colombia) | Por revisar |
| 2 | El valor por noche es mayor que el tope de hospedaje de la ciudad | Rechazada |
| 3 | El tiquete cuesta más de $1.500.000 COP (política, sección 3) | Pendiente de director |
| 4 | En cualquier otro caso | Aprobada |

## Detalles que importan

- "Más de" y "mayor que" significan estrictamente mayor. Un valor **igual** al tope cumple.
- La ciudad y el nombre del empleado se comparan sin importar mayúsculas ni tildes: "medellin" es Medellín.
- Un viaje de ida y vuelta el mismo día tiene 0 noches y valor por noche 0.
- El empleado debe existir en `empleados.csv`. Si no existe, no se registra nada.
- Los radicados son consecutivos: S-101, S-102… La siguiente solicitud toma el número que sigue al mayor.
- Los estados de `solicitudes_historicas.csv` los asignaron personas antes de este sistema. No se recalculan.
