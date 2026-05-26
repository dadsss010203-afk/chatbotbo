# Ejemplos de consultas

## 1) Consulta simple por destino

Usuario: "Cuanto cuesta enviar 500g a Cobija?"

Transformacion sugerida:
- peso: 500g
- columna: I

Comando:
```bash
bash backend/app/skills/skill1/tools/calcular_hoja1_json.sh --peso "500g" --columna "I"
```

## 2) Consulta con kilos y destino Riberalta

Usuario: "Costo para 2.5 kilos a Riberalta"

Transformacion sugerida:
- peso: 2.5kg
- columna: J

Comando:
```bash
bash backend/app/skills/skill1/tools/calcular_hoja1_json.sh --peso "2.5kg" --columna "J"
```

## 3) Caso de hueco entre rangos

Usuario: "Precio para 1005g a Riberalta"

Transformacion sugerida:
- peso: 1005g
- columna: J
- aplica regla de huecos -> siguiente tarifa

Comando:
```bash
bash backend/app/skills/skill1/tools/calcular_hoja1_json.sh --peso "1005g" --columna "J"
```

## 4) Ejemplo de salida JSON esperada

```json
{
  "ok": true,
  "precio": 13,
  "columna": "I",
  "servicio": "Trinidad- Cobija",
  "fila": 12,
  "rango": {
    "min_g": 401,
    "max_g": 500
  },
  "peso_g": 500
}
```

## 5) Preguntas variadas que deben resolver igual

Usuario: "cuanto sale 2.5kg a riberalta"
- peso: 2.5kg
- columna: J

Usuario: "cotizame 500g a cobija"
- peso: 500g
- columna: I

Usuario: "precio 10 kilos rieral"
- peso: 10kg
- columna: J

Usuario: "tarifa para 750 g trinidad"
- peso: 750g
- columna: I

Usuario: "2kg a cobija"
- peso: 2kg
- columna: I

Usuario: "ems nacional para 1.2kg"
- peso: 1.2kg
- columna: G (alias de servicio)

Usuario: "seguimiento guia 12345"
- no es tarifa (debe pasar al flujo de rastreo)
