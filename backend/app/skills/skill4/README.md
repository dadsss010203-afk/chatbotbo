# Skill EMS Hoja 4

Este paquete deja a tu agente listo para calcular tarifas de la Hoja 4 con un Excel reducido incluido.

## Estructura recomendada

```text
backend/app/skills/skill4/
  README.md
  data/
    Tarifario_Hoja4.xlsx
  runtime/
    calcular_hoja4_runtime.py
  tools/
    calcular_hoja4_json.sh
  contracts/
    hoja4_result.schema.json
  prompts/
    system_prompt_hoja4.txt
  docs/
    ejemplos_consultas.md
  skills/
    hoja4_analista_ia/
      SKILL.md
      agents/openai.yaml
      references/plantilla_salida.md
```

## Integracion rapida

```bash
bash backend/app/skills/skill4/tools/calcular_hoja4_json.sh --peso "800g" --columna "C"
```

Mapa de columnas:
- C: America Del Sur / Destinos A
- D: America Central y El Caribe / Destinos B
- E: America Del Norte / Destinos C
- F: Europa y Medio Oriente / Destinos D
- G: Africa, Asia y Oceania / Destinos E
