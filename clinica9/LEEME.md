# Clínica de bugs · Altiplano S.A.S.

Esta mini-aplicación calcula los reembolsos de viáticos de noviembre.
Un practicante la dejó "casi lista" y tiene **cinco averías**. Tu trabajo es
encontrarlas y arreglarlas con Claude Code, **una a la vez**.

## Cómo empezar

1. Copia la carpeta `clinica9/` a la raíz de tu proyecto de viáticos.
2. En Claude Code, pide: «Arranca el servidor de la clínica con
   `python clinica9/servidor.py`, usando mi entorno virtual».
3. Abre http://127.0.0.1:8009 en el navegador o en el panel Browser.
4. La clave de administrador de prueba es: `altiplano-demo-2026`

## Reglas del juego

- Trabaja solo dentro de `clinica9/`.
- Una avería a la vez, en orden. Cada tarjeta describe el síntoma, no la causa.
- Usa la plantilla de reporte de bug (está en la diapositiva).
- Reporta en el chat de la clase: `Avería 3 ✅ en 1 prompt`.

## Archivos

| Archivo | Qué es |
|---|---|
| `servidor.py` | El servidor (FastAPI) |
| `calculos.py` | Las cuentas del reembolso |
| `config.py` | Lee el archivo `.env` |
| `static/index.html` | La página |
| `datos/legalizaciones_noviembre.csv` | Lo que envió Tesorería |
| `politica_reembolsos.md` | Las reglas que debe cumplir el cálculo |
| `log_produccion.txt` | Solo para el bonus |
