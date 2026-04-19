---
name: hoja2-analista-ia
description: Analiza y calcula tarifas de la Hoja 2 (Table 2) del tarifario EMS Internacional con salida estructurada y trazable. Usar cuando el usuario pida validar rangos de peso, calcular precios por servicio C-G o Destinos A-E, detectar inconsistencias de datos, normalizar unidades g/kg, resolver huecos entre rangos o generar reporte ejecutivo de hallazgos.
---

# Hoja2 Analista Ia

## Objetivo

Estandarizar el analisis de la Hoja 2 para producir resultados claros, trazables y accionables, evitando respuestas ambiguas.

## Flujo de trabajo

1. Entender la solicitud y definir alcance exacto de la Hoja 2.
2. Levantar estructura de datos: filas 7-28, rangos A-B y columnas tarifarias C-G.
3. Normalizar unidades de peso a gramos para entrada y rangos internos.
4. Aplicar regla de busqueda de tarifa:
   `min_g <= peso_g <= max_g`.
5. Si el peso cae en hueco entre rangos, aplicar redondeo comercial hacia arriba
   (usar la siguiente tarifa disponible).
6. Ejecutar control de calidad: nulos, formato, rangos invertidos, solapamientos y huecos.
7. Entregar salida estructurada con hallazgos, impacto y recomendaciones.

## Reglas operativas

- Confirmar supuestos antes de aplicar transformaciones irreversibles.
- Priorizar precision sobre velocidad cuando exista riesgo de error de negocio.
- Separar hechos de inferencias; marcar explicitamente cualquier suposicion.
- Mantener nomenclatura consistente para columnas y metricas.
- No ocultar datos faltantes: reportarlos con conteo y porcentaje.
- Si se calcula tarifa puntual, mostrar: peso de entrada, rango aplicado, columna/servicio y precio final.
- Para integraciones API, priorizar salida estructurada del wrapper `backend/app/skills/skill2/tools/calcular_hoja2_json.sh`.
- Si el wrapper responde `ok=false`, elevar el error textual sin reinterpretarlo.

## Formato de salida obligatorio

Entregar siempre en este orden:

1. Resumen ejecutivo (maximo 5 lineas)
2. Hallazgos criticos (errores o riesgos altos)
3. Hallazgos medios (calidad, consistencia, formato)
4. Acciones recomendadas (priorizadas)
5. Tabla de trazabilidad de cambios

Usar la plantilla de referencia en `references/plantilla_salida.md`.

## Criterio de calidad minimo

- Cada hallazgo debe incluir evidencia puntual.
- Cada recomendacion debe incluir impacto esperado.
- Si faltan datos para concluir, indicar que falta y como obtenerlo.
- Evitar lenguaje vago como "parece" o "tal vez" sin soporte.
- Verificar al menos un caso de borde (limite exacto) y un caso en hueco entre rangos.

## Recursos

- Cargar `references/plantilla_salida.md` cuando se necesite un formato de entrega uniforme.
- Usar `../../contracts/hoja2_result.schema.json` como referencia de contrato para respuestas JSON.
