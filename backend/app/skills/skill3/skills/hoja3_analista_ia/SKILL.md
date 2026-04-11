---
name: hoja3-analista-ia
description: Analiza y calcula tarifas de la Hoja 3 (Table 3) del tarifario Mi Encomienda Prioritario Nacional con salida estructurada y trazable. Usar cuando el usuario pida validar rangos de peso, calcular precios por servicio C-F, detectar inconsistencias de datos, normalizar unidades g/kg/gr o generar reporte ejecutivo de hallazgos.
---

# Hoja3 Analista Ia

## Objetivo

Estandarizar el analisis de la Hoja 3 para producir resultados claros, trazables y accionables.

## Flujo de trabajo

1. Entender la solicitud y definir alcance exacto de la Hoja 3.
2. Levantar estructura de datos: filas 7-28, rangos A-B y columnas tarifarias C-F.
3. Normalizar unidades de peso a gramos para entrada y rangos internos.
4. Aplicar regla de busqueda de tarifa: `min_g <= peso_g <= max_g`.
5. Entregar salida estructurada con hallazgos, impacto y recomendaciones.

## Reglas operativas

- Mantener nomenclatura consistente para columnas y metricas.
- Si se calcula tarifa puntual, mostrar peso, rango aplicado, columna/servicio y precio final.
- Para integraciones API, priorizar salida estructurada del wrapper `backend/app/skills/skill3/tools/calcular_hoja3_json.sh`.
- Si el wrapper responde `ok=false`, elevar el error textual sin reinterpretarlo.

## Formato de salida obligatorio

Entregar siempre en este orden:

1. Resumen ejecutivo (maximo 5 lineas)
2. Hallazgos criticos
3. Hallazgos medios
4. Acciones recomendadas
5. Tabla de trazabilidad de cambios

Usar `references/plantilla_salida.md`.

## Recursos

- Cargar `references/plantilla_salida.md` cuando se necesite formato uniforme.
- Usar `../../contracts/hoja3_result.schema.json` como referencia de contrato JSON.
