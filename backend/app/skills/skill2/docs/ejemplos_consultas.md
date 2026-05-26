# Ejemplos de consultas

## 1) Consulta por columna

Usuario: "Cuanto cuesta enviar 800g por America Del Sur?"

Transformacion sugerida:
- peso: 800g
- columna: C

Comando:
```bash
bash backend/app/skills/skill2/tools/calcular_hoja2_json.sh --peso "800g" --columna "C"
```

## 2) Consulta por nombre de servicio

Usuario: "Costo para 2.5 kilos a Europa y Medio Oriente"

Transformacion sugerida:
- peso: 2.5kg
- columna: F

Comando:
```bash
bash backend/app/skills/skill2/tools/calcular_hoja2_json.sh --peso "2.5kg" --columna "F"
```

## 3) Consulta por destino A-E

Usuario: "Tarifa 1.2kg destinos B"

Transformacion sugerida:
- peso: 1.2kg
- columna: D

Comando:
```bash
bash backend/app/skills/skill2/tools/calcular_hoja2_json.sh --peso "1.2kg" --columna "D"
```

## 4) Ejemplo de salida JSON esperada

```json
{
  "ok": true,
  "precio": 176,
  "columna": "C",
  "servicio": "América Del Sur (Destinos A)",
  "fila": 10,
  "rango": {
    "min_g": 501,
    "max_g": 1000
  },
  "peso_g": 800
}
```
