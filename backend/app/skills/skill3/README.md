# Skill EMS Hoja 3

Este paquete deja a tu agente listo para calcular tarifas de la Hoja 3 con un Excel reducido incluido.

## Estructura recomendada

```text
backend/app/skills/skill3/
  README.md
  data/
    Tarifario_Hoja3.xlsx
  runtime/
    calcular_hoja3_runtime.py
  tools/
    calcular_hoja3_json.sh
  contracts/
    hoja3_result.schema.json
  prompts/
    system_prompt_hoja3.txt
  docs/
    ejemplos_consultas.md
  skills/
    hoja3_analista_ia/
      SKILL.md
      agents/openai.yaml
      references/plantilla_salida.md
```

## Integracion rapida

```bash
bash backend/app/skills/skill3/tools/calcular_hoja3_json.sh --peso "800g" --columna "C"
```

Mapa de columnas:
- C: Ciudades Capitales
- D: Destinos Especiales / Trinidad -Cobija
- E: Prov. Dentro Depto.
- F: Prov. En Otro Depto.
