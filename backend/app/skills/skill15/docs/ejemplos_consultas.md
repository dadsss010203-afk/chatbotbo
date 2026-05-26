# Ejemplos de consultas

## 1) Consulta por columna

Usuario: "Cuanto cuesta 800g para Sud América / Tarifa 1?"

Transformacion sugerida:
- peso: 800g
- columna: B

Comando:
```bash
bash backend/app/skills/skill15/tools/calcular_hoja15_json.sh --peso "800g" --columna "B"
```

## 2) Consulta alternativa

Usuario: "Costo para 2.5 kilos"

Transformacion sugerida:
- peso: 2.5kg
- columna: C

Comando:
```bash
bash backend/app/skills/skill15/tools/calcular_hoja15_json.sh --peso "2.5kg" --columna "C"
```
