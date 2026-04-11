# Ejemplos de consultas

## 1) Consulta por columna

Usuario: "Cuanto cuesta 800g para Ciudades Capitales?"

Transformacion sugerida:
- peso: 800g
- columna: C

Comando:
```bash
bash backend/app/skills/skill3/tools/calcular_hoja3_json.sh --peso "800g" --columna "C"
```

## 2) Consulta por servicio

Usuario: "Costo para 2.5 kilos a Prov. En Otro Depto."

Transformacion sugerida:
- peso: 2.5kg
- columna: F

Comando:
```bash
bash backend/app/skills/skill3/tools/calcular_hoja3_json.sh --peso "2.5kg" --columna "F"
```
