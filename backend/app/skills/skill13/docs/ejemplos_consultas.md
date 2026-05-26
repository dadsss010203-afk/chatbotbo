# Ejemplos de consultas

## 1) Consulta por columna

Usuario: "Cuanto cuesta 800g para EMS Nacional?"

Transformacion sugerida:
- peso: 800g
- columna: C

Comando:
```bash
bash backend/app/skills/skill13/tools/calcular_hoja13_json.sh --peso "800g" --columna "C"
```

## 2) Consulta alternativa

Usuario: "Costo para 2.5 kilos"

Transformacion sugerida:
- peso: 2.5kg
- columna: D

Comando:
```bash
bash backend/app/skills/skill13/tools/calcular_hoja13_json.sh --peso "2.5kg" --columna "D"
```
