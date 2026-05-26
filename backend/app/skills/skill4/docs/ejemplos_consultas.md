# Ejemplos de consultas

## 1) Consulta por columna

Usuario: "Cuanto cuesta 800g para America Del Sur / Destinos A?"

Transformacion sugerida:
- peso: 800g
- columna: C

Comando:
```bash
bash backend/app/skills/skill4/tools/calcular_hoja4_json.sh --peso "800g" --columna "C"
```

## 2) Consulta por servicio

Usuario: "Costo para 2.5 kilos a Europa y Medio Oriente / Destinos D"

Transformacion sugerida:
- peso: 2.5kg
- columna: F

Comando:
```bash
bash backend/app/skills/skill4/tools/calcular_hoja4_json.sh --peso "2.5kg" --columna "F"
```
