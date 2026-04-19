# Skill EMS Hoja 1

Este paquete deja a tu agente listo para calcular tarifas de la Hoja 1 con un Excel reducido incluido dentro de la carpeta.

Nota: en esta version ya se incluye un archivo reducido con solo `Table 1` en `data/Tarifario_Hoja1.xlsx`.

## Estructura recomendada

```text
backend/app/skills/skill1/
  README.md
  data/
    Tarifario_Hoja1.xlsx
  runtime/
    calcular_hoja1_runtime.py
  tools/
    calcular_hoja1_json.sh
  contracts/
    hoja1_result.schema.json
  prompts/
    system_prompt_hoja1.txt
  docs/
    ejemplos_consultas.md
  skills/
    hoja1_analista_ia/
      SKILL.md
      agents/openai.yaml
      references/plantilla_salida.md
```

- `skills/hoja1_analista_ia/`: comportamiento de la skill y formato de salida.
- `runtime/calcular_hoja1_runtime.py`: motor de calculo real (lee Table 1 del Excel).
- `tools/calcular_hoja1_json.sh`: wrapper con salida JSON real (sin tocar logica Python).
- `contracts/hoja1_result.schema.json`: contrato sugerido para consumidores API.
- `prompts/system_prompt_hoja1.txt`: prompt operativo para el agente.
- `docs/ejemplos_consultas.md`: ejemplos de uso y salidas esperadas.

## Requisito minimo

- Python 3 disponible.
- Archivo `backend/app/skills/skill1/data/Tarifario_Hoja1.xlsx` presente (ya incluido en este paquete).

## Integracion rapida (3 pasos)

1. Copiar esta carpeta completa `backend/app/skills/skill1/` a tu proyecto de chatbot.
2. En cada consulta de tarifa, ejecutar (modo recomendado JSON):

```bash
bash backend/app/skills/skill1/tools/calcular_hoja1_json.sh \
  --peso "500g" \
  --columna "I"
```

3. Si quieres usar otro Excel externo, puedes pasar `--xlsx "/ruta/archivo.xlsx"`.

Referencia de documentación:
- Prompt: `backend/app/skills/skill1/prompts/system_prompt_hoja1.txt`
- Ejemplos: `backend/app/skills/skill1/docs/ejemplos_consultas.md`
- Contrato JSON: `backend/app/skills/skill1/contracts/hoja1_result.schema.json`

## Modo runtime directo (compatibilidad)

Si necesitas mantener el formato original `clave=valor`, usa:

```bash
python3 backend/app/skills/skill1/runtime/calcular_hoja1_runtime.py \
  --peso "500g" \
  --columna "I" \
  --json
```

## Mapeo de destinos

- `I`: Trinidad- Cobija
- `J`: Riberalta- Guayaramerín
- `H`: Ciudades Intermedias
- `G`: EMS Nacional
- `C-D-E-F`: EMS Local Cobertura 1-4

## Regla de huecos entre rangos

Si el peso cae entre dos rangos (ejemplo: 1005g entre 1000g y 1010g), el motor aplica la siguiente tarifa disponible (redondeo comercial hacia arriba).

## Formato de respuesta sugerido al usuario final

- Precio final en bolivianos.
- Servicio/columna aplicada.
- Rango de peso aplicado.
- (Opcional) nota de que se aplico regla de huecos.

## Troubleshooting rapido

- Error `Falta --peso`: agrega `--peso "500g"` o `--peso "2.5kg"`.
- Error `Debes indicar --columna o --servicio`: agrega uno de esos parametros.
- Error `No se encontro el archivo xlsx`: valida la ruta de `--xlsx`.
- Respuesta `Peso fuera de rango o precio vacio`: verifica que el peso este dentro de los rangos de la Hoja 1.

## Cobertura de lenguaje natural (chat)

La integración backend reconoce consultas variadas de precio, por ejemplo:
- "cuanto sale 2.5kg a riberalta"
- "cotizame 500g a cobija"
- "precio 10 kilos rieral"
