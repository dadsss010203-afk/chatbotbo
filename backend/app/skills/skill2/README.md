# Skill EMS Hoja 2

Este paquete deja a tu agente listo para calcular tarifas de la Hoja 2 con un Excel reducido incluido dentro de la carpeta.

Nota: en esta version se incluye `Table 2` en `data/Tarifario_Hoja2.xlsx`.

## Estructura recomendada

```text
backend/app/skills/skill2/
  README.md
  data/
    Tarifario_Hoja2.xlsx
  runtime/
    calcular_hoja2_runtime.py
  tools/
    calcular_hoja2_json.sh
  contracts/
    hoja2_result.schema.json
  prompts/
    system_prompt_hoja2.txt
  docs/
    ejemplos_consultas.md
  skills/
    hoja2_analista_ia/
      SKILL.md
      agents/openai.yaml
      references/plantilla_salida.md
```

## Integracion rapida

1. Copiar `backend/app/skills/skill2/` a tu proyecto.
2. Ejecutar calculos con:

```bash
bash backend/app/skills/skill2/tools/calcular_hoja2_json.sh --peso "800g" --columna "C"
```

3. Opcional: usar `--xlsx` para otro archivo externo.

## Mapa de columnas

- `C`: America Del Sur (Destinos A)
- `D`: America Central y El Caribe (Destinos B)
- `E`: America Del Norte (Destinos C)
- `F`: Europa y Medio Oriente (Destinos D)
- `G`: Africa, Asia y Oceania (Destinos E)
