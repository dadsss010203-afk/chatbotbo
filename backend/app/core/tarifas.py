"""
core/tarifas.py
Motor Python de calculo tarifario sin depender del PDF dentro del chat.
"""

from __future__ import annotations

import re
import unicodedata


TARIFF_SOURCE = {
    "label": "motor: tarifario Python",
    "source_name": "motor_tarifario_python",
    "source_page": "",
    "source_path": "",
    "source_type": "tariff_engine",
    "source_url": "",
}


TARIFF_TABLES = {
    "mi_encomienda_nacional": {
        "label": "Mi Encomienda Prioritario Nacional",
        "columns": [
            ("capitales", "Ciudades capitales"),
            ("prov_dentro", "Provincia dentro del departamento"),
            ("prov_otro", "Provincia otro departamento"),
            ("especiales", "Trinidad / Cobija"),
        ],
        "rows": [
            {"from_g": 0.1, "to_g": 500, "values": [8, 12, 17, 25], "line": "0,1g 500g 8 12 17 25"},
            {"from_g": 501, "to_g": 1000, "values": [10, 26, 19, 29], "line": "501g 1kg 10 26 19 29"},
            {"from_g": 1010, "to_g": 2000, "values": [16, 42, 25, 41], "line": "1,01kg 2kg 16 42 25 41"},
            {"from_g": 2010, "to_g": 3000, "values": [21, 57, 31, 52], "line": "2,01kg 3kg 21 57 31 52"},
            {"from_g": 3010, "to_g": 4000, "values": [26, 73, 37, 63], "line": "3,01kg 4kg 26 73 37 63"},
            {"from_g": 4010, "to_g": 5000, "values": [31, 88, 44, 75], "line": "4,01kg 5kg 31 88 44 75"},
            {"from_g": 5010, "to_g": 6000, "values": [36, 104, 51, 87], "line": "5,01kg 6kg 36 104 51 87"},
            {"from_g": 6010, "to_g": 7000, "values": [42, 119, 58, 100], "line": "6,01kg 7kg 42 119 58 100"},
            {"from_g": 7010, "to_g": 8000, "values": [47, 135, 65, 112], "line": "7,01kg 8kg 47 135 65 112"},
            {"from_g": 8010, "to_g": 9000, "values": [52, 151, 73, 125], "line": "8,01kg 9kg 52 151 73 125"},
            {"from_g": 9010, "to_g": 10000, "values": [57, 166, 80, 137], "line": "9,01kg 10kg 57 166 80 137"},
            {"from_g": 10010, "to_g": 11000, "values": [62, 182, 87, 150], "line": "10,01kg 11kg 62 182 87 150"},
            {"from_g": 11010, "to_g": 12000, "values": [68, 197, 95, 162], "line": "11,01kg 12kg 68 197 95 162"},
            {"from_g": 12010, "to_g": 13000, "values": [73, 213, 102, 175], "line": "12,01kg 13kg 73 213 102 175"},
            {"from_g": 13010, "to_g": 14000, "values": [78, 229, 109, 187], "line": "13,01kg 14kg 78 229 109 187"},
            {"from_g": 14010, "to_g": 15000, "values": [83, 244, 116, 199], "line": "14,01kg 15kg 83 244 116 199"},
            {"from_g": 15010, "to_g": 16000, "values": [88, 260, 124, 212], "line": "15,01kg 16kg 88 260 124 212"},
            {"from_g": 16010, "to_g": 17000, "values": [94, 275, 131, 224], "line": "16,01kg 17kg 94 275 131 224"},
            {"from_g": 17010, "to_g": 18000, "values": [99, 291, 138, 237], "line": "17,01kg 18kg 99 291 138 237"},
            {"from_g": 18010, "to_g": 19000, "values": [104, 307, 145, 249], "line": "18,01kg 19kg 104 307 145 249"},
            {"from_g": 19010, "to_g": 20000, "values": [109, 322, 153, 262], "line": "19,01kg 20kg 109 322 153 262"},
        ],
    },
    "ems_internacional": {
        "label": "EMS Internacional",
        "columns": [
            ("destinos_a", "América del Sur"),
            ("destinos_b", "América Central y Caribe"),
            ("destinos_c", "América del Norte"),
            ("destinos_d", "Europa y Medio Oriente"),
            ("destinos_e", "África, Asia y Oceanía"),
        ],
        "rows": [
            {"from_g": 0.1, "to_g": 250, "values": [186, 205, 230, 270, 441], "line": "0,1g 250g 186 205 230 270 441"},
            {"from_g": 251, "to_g": 500, "values": [207, 225, 250, 291, 461], "line": "251g 500g 207 225 250 291 461"},
            {"from_g": 501, "to_g": 1000, "values": [228, 246, 271, 312, 482], "line": "501g 1kg 228 246 271 312 482"},
            {"from_g": 1010, "to_g": 2000, "values": [298, 321, 352, 405, 613], "line": "1,01Kg 2kg 298 321 352 405 613"},
            {"from_g": 2010, "to_g": 3000, "values": [369, 396, 433, 528, 744], "line": "2,01kg 3kg 369 396 433 528 744"},
            {"from_g": 3010, "to_g": 4000, "values": [439, 471, 514, 632, 875], "line": "3,01kg 4kg 439 471 514 632 875"},
            {"from_g": 4010, "to_g": 5000, "values": [510, 545, 595, 736, 1006], "line": "4,01kg 5kg 510 545 595 736 1.006"},
            {"from_g": 5010, "to_g": 6000, "values": [581, 620, 676, 860, 1137], "line": "5,01kg 6kg 581 620 676 860 1.137"},
            {"from_g": 6010, "to_g": 7000, "values": [623, 678, 757, 964, 1268], "line": "6,01kg 7kg 623 678 757 964 1.268"},
            {"from_g": 7010, "to_g": 8000, "values": [666, 737, 838, 1067, 1398], "line": "7,01kg 8kg 666 737 838 1.067 1.398"},
            {"from_g": 8010, "to_g": 9000, "values": [709, 795, 920, 1171, 1529], "line": "8,01kg 9kg 709 795 920 1.171 1.529"},
            {"from_g": 9010, "to_g": 10000, "values": [751, 853, 1001, 1275, 1721], "line": "9,01kg 10kg 751 853 1.001 1.275 1.721"},
            {"from_g": 10010, "to_g": 11000, "values": [794, 911, 1082, 1400, 1851], "line": "10,01kg 11kg 794 911 1.082 1.400 1.851"},
            {"from_g": 11010, "to_g": 12000, "values": [836, 969, 1156, 1503, 1982], "line": "11,01kg 12kg 836 969 1.156 1.503 1.982"},
            {"from_g": 12010, "to_g": 13000, "values": [879, 1028, 1231, 1606, 2113], "line": "12,01kg 13kg 879 1.028 1.231 1.606 2.113"},
            {"from_g": 13010, "to_g": 14000, "values": [922, 1086, 1306, 1710, 2305], "line": "13,01kg 14kg 922 1.086 1.306 1.710 2.305"},
            {"from_g": 14010, "to_g": 15000, "values": [964, 1144, 1381, 1814, 2435], "line": "14,01kg 15kg 964 1.144 1.381 1.814 2.435"},
            {"from_g": 15010, "to_g": 16000, "values": [1007, 1202, 1456, 1918, 2566], "line": "15,01kg 16kg 1.007 1.202 1.456 1.918 2.566"},
            {"from_g": 16010, "to_g": 17000, "values": [1049, 1260, 1530, 2021, 2758], "line": "16,01kg 17kg 1.049 1.260 1.530 2.021 2.758"},
            {"from_g": 17010, "to_g": 18000, "values": [1092, 1318, 1605, 2125, 2888], "line": "17,01kg 18kg 1.092 1.318 1.605 2.125 2.888"},
            {"from_g": 18010, "to_g": 19000, "values": [1135, 1377, 1680, 2229, 3019], "line": "18,01kg 19kg 1.135 1.377 1.680 2.229 3.019"},
            {"from_g": 19010, "to_g": 20000, "values": [1177, 1435, 1755, 2333, 3211], "line": "19,01kg 20kg 1.177 1.435 1.755 2.333 3.211"},
        ],
    },
    "eca_nacional_antiguos": {
        "label": "ECA Nacional para usuarios antiguos",
        "columns": [
            ("local", "Local"),
            ("nacional", "Nacional"),
        ],
        "rows": [
            {"from_g": 1, "to_g": 20, "values": [1.5, 4], "line": "1 20 1,50 4,00"},
            {"from_g": 21, "to_g": 100, "values": [2, 5.5], "line": "21 100 2,00 5,50"},
            {"from_g": 101, "to_g": 250, "values": [3.5, 6], "line": "101 250 3,50 6,00"},
            {"from_g": 251, "to_g": 500, "values": [4, 7], "line": "251 500 4,00 7,00"},
            {"from_g": 501, "to_g": 1000, "values": [5, 8], "line": "501 1.000 5,00 8,00"},
            {"from_g": 1001, "to_g": 2000, "values": [9, 12], "line": "1.001 2.000 9,00 12,00"},
            {"from_g": 2001, "to_g": 3000, "values": [11, 16], "line": "2.001 3.000 11,00 16,00"},
            {"from_g": 3001, "to_g": 4000, "values": [13, 20], "line": "3.001 4.000 13,00 20,00"},
            {"from_g": 4001, "to_g": 5000, "values": [15, 24], "line": "4.001 5.000 15,00 24,00"},
            {"from_g": 5001, "to_g": 6000, "values": [21, 32], "line": "5.001 6.000 21,00 32,00"},
            {"from_g": 6001, "to_g": 7000, "values": [23, 36], "line": "6.001 7.000 23,00 36,00"},
            {"from_g": 7001, "to_g": 8000, "values": [24, 41], "line": "7.001 8.000 24,00 41,00"},
            {"from_g": 8001, "to_g": 9000, "values": [26, 45], "line": "8.001 9.000 26,00 45,00"},
            {"from_g": 9001, "to_g": 10000, "values": [28, 50], "line": "9.001 10.000 28,00 50,00"},
            {"from_g": 10001, "to_g": 11000, "values": [30, 54], "line": "10.001 11.000 30,00 54,00"},
            {"from_g": 11001, "to_g": 12000, "values": [32, 59], "line": "11.001 12.000 32,00 59,00"},
            {"from_g": 12001, "to_g": 13000, "values": [33, 63], "line": "12.001 13.000 33,00 63,00"},
            {"from_g": 13001, "to_g": 14000, "values": [35, 68], "line": "13.001 14.000 35,00 68,00"},
            {"from_g": 14001, "to_g": 15000, "values": [37, 72], "line": "14.001 15.000 37,00 72,00"},
            {"from_g": 15001, "to_g": 16000, "values": [39, 77], "line": "15.001 16.000 39,00 77,00"},
            {"from_g": 16001, "to_g": 17000, "values": [41, 81], "line": "16.001 17.000 41,00 81,00"},
            {"from_g": 17001, "to_g": 18000, "values": [42, 86], "line": "17.001 18.000 42,00 86,00"},
            {"from_g": 18001, "to_g": 19000, "values": [44, 90], "line": "18.001 19.000 44,00 90,00"},
            {"from_g": 19001, "to_g": 20000, "values": [46, 95], "line": "19.001 20.000 46,00 95,00"},
        ],
    },
    "eca_internacional_antiguos": {
        "label": "ECA Internacional para usuarios antiguos",
        "columns": [
            ("grupo_1", "Sudamérica"),
            ("grupo_2", "Centroamérica y Caribe"),
            ("grupo_3", "Norteamérica"),
            ("grupo_4", "Europa y Medio Oriente"),
            ("grupo_5", "África, Asia y Oceanía"),
        ],
        "rows": [
            {"from_g": 1, "to_g": 20, "values": [13, 14, 18, 21, 23], "line": "1 20 13,00 14,00 18,00 21,00 23,00"},
            {"from_g": 21, "to_g": 100, "values": [25, 29, 37, 41, 57], "line": "21 100 25,00 29,00 37,00 41,00 57,00"},
            {"from_g": 101, "to_g": 250, "values": [46, 65, 73, 79, 135], "line": "101 250 46,00 65,00 73,00 79,00 135,00"},
            {"from_g": 251, "to_g": 500, "values": [95, 97, 100, 119, 270], "line": "251 500 95,00 97,00 100,00 119,00 270,00"},
            {"from_g": 501, "to_g": 1000, "values": [126, 148, 194, 235, 337], "line": "501 1.000 126,00 148,00 194,00 235,00 337,00"},
            {"from_g": 1001, "to_g": 2000, "values": [239, 244, 271, 316, 505], "line": "1.001 2.000 239,00 244,00 271,00 316,00 505,00"},
            {"from_g": 2001, "to_g": 3000, "values": [252, 288, 360, 410, 606], "line": "2.001 3.000 252,00 288,00 360,00 410,00 606,00"},
            {"from_g": 3001, "to_g": 4000, "values": [311, 355, 418, 518, 720], "line": "3.001 4.000 311,00 355,00 418,00 518,00 720,00"},
            {"from_g": 4001, "to_g": 5000, "values": [359, 443, 464, 607, 842], "line": "4.001 5.000 359,00 443,00 464,00 607,00 842,00"},
        ],
    },
}


def _normalize(texto: str | None) -> str:
    texto = (texto or "").strip().lower()
    texto = "".join(
        ch for ch in unicodedata.normalize("NFKD", texto)
        if not unicodedata.combining(ch)
    )
    texto = re.sub(r"[^a-z0-9\s]", " ", texto)
    texto = re.sub(r"\s+", " ", texto)
    return texto.strip()


def _parse_num(token: str) -> float:
    token = (token or "").strip()
    token = token.replace(",", ".")
    return float(token)


def _extract_weight_grams(query: str) -> float | None:
    text = query.lower()
    if re.search(r"\bun\b|\buna\b", text):
        text = re.sub(r"\bun\b", "1", text)
        text = re.sub(r"\buna\b", "1", text)

    patterns = [
        r"(\d+(?:[.,]\d+)?)\s*(kg|kilo|kilos|kilogramo|kilogramos)\b",
        r"(\d+(?:[.,]\d+)?)\s*(g|gr|gramo|gramos)\b",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, re.I)
        if not match:
            continue
        value = _parse_num(match.group(1))
        unit = match.group(2).lower()
        return value * 1000 if unit.startswith("k") else value
    return None


def _detect_service(query_norm: str) -> str | None:
    if "mi encomienda" in query_norm:
        return "mi_encomienda_nacional"
    if "ems" in query_norm and "internacional" in query_norm:
        return "ems_internacional"
    if "eca" in query_norm and "internacional" in query_norm:
        return "eca_internacional_antiguos"
    if "eca" in query_norm and "nacional" in query_norm:
        return "eca_nacional_antiguos"
    if "tarifa" in query_norm or "tarifario" in query_norm or "cuanto cuesta" in query_norm:
        if "internacional" in query_norm:
            return "ems_internacional"
        if "trinidad" in query_norm or "cobija" in query_norm or "mi encomienda" in query_norm:
            return "mi_encomienda_nacional"
    return None


def _detect_column(query_norm: str, service_key: str) -> tuple[str | None, str | None]:
    if service_key == "ems_internacional":
        if any(k in query_norm for k in ("sudamerica", "america del sur", "sud america")):
            return "destinos_a", "América del Sur"
        if any(k in query_norm for k in ("centroamerica", "america central", "caribe")):
            return "destinos_b", "América Central y Caribe"
        if any(k in query_norm for k in ("america del norte", "norteamerica", "usa", "estados unidos", "canada")):
            return "destinos_c", "América del Norte"
        if any(k in query_norm for k in ("europa", "medio oriente")):
            return "destinos_d", "Europa y Medio Oriente"
        if any(k in query_norm for k in ("asia", "africa", "oceania")):
            return "destinos_e", "África, Asia y Oceanía"
        return None, None

    if service_key == "mi_encomienda_nacional":
        if any(k in query_norm for k in ("capital", "capitales", "ciudad capital")):
            return "capitales", "Ciudades capitales"
        if any(k in query_norm for k in ("mismo departamento", "dentro del departamento", "dentro de departamento", "provincia dentro")):
            return "prov_dentro", "Provincia dentro del departamento"
        if any(k in query_norm for k in ("otro departamento", "otro depto", "provincia otro")):
            return "prov_otro", "Provincia otro departamento"
        if any(k in query_norm for k in ("trinidad", "cobija", "destino especial", "especiales")):
            return "especiales", "Trinidad / Cobija"
        return None, None

    if service_key == "eca_nacional_antiguos":
        if "local" in query_norm:
            return "local", "Local"
        if "nacional" in query_norm:
            return "nacional", "Nacional"
        return None, None

    if service_key == "eca_internacional_antiguos":
        if any(k in query_norm for k in ("sudamerica", "america del sur", "sud america")):
            return "grupo_1", "Sudamérica"
        if any(k in query_norm for k in ("centroamerica", "caribe", "america central")):
            return "grupo_2", "Centroamérica y Caribe"
        if any(k in query_norm for k in ("america del norte", "norteamerica", "usa", "estados unidos", "canada")):
            return "grupo_3", "Norteamérica"
        if any(k in query_norm for k in ("europa", "medio oriente")):
            return "grupo_4", "Europa y Medio Oriente"
        if any(k in query_norm for k in ("africa", "asia", "oceania")):
            return "grupo_5", "África, Asia y Oceanía"
        return None, None

    return None, None


def _find_row(rows: list[dict], weight_g: float) -> dict | None:
    for row in rows:
        if row["from_g"] <= weight_g <= row["to_g"]:
            return row
    return None


def _format_weight(weight_g: float) -> str:
    if weight_g >= 1000:
        kilos = weight_g / 1000.0
        if kilos.is_integer():
            return f"{int(kilos)} kg"
        return f"{kilos:.2f}".rstrip("0").rstrip(".") + " kg"
    if float(weight_g).is_integer():
        return f"{int(weight_g)} g"
    return f"{weight_g:.2f}".rstrip("0").rstrip(".") + " g"


def _format_money(value: float) -> str:
    if float(value).is_integer():
        return f"{int(value)}"
    return f"{value:.2f}".rstrip("0").rstrip(".")


def resolve_tariff_query(query: str) -> dict | None:
    query_norm = _normalize(query)
    if not any(
        token in query_norm
        for token in ("tarifa", "tarifario", "cuanto cuesta", "costo", "precio", "ems", "encomienda", "eca")
    ):
        return None

    service_key = _detect_service(query_norm)
    weight_g = _extract_weight_grams(query)

    if not service_key:
        return {
            "mode": "ask",
            "prompt_context": (
                "Necesito que indiques el servicio exacto para calcular la tarifa. "
                "Opciones disponibles: EMS Internacional, Mi Encomienda Prioritario Nacional, "
                "ECA Nacional para usuarios antiguos y ECA Internacional para usuarios antiguos."
            ),
            "sources": [TARIFF_SOURCE],
            "primary_source_type": "tariff_engine",
        }

    if weight_g is None:
        return {
            "mode": "ask",
            "prompt_context": (
                f"Para calcular {TARIFF_TABLES[service_key]['label']}, indícame el peso exacto del envío en gramos o kg."
            ),
            "sources": [TARIFF_SOURCE],
            "primary_source_type": "tariff_engine",
        }

    column_key, column_label = _detect_column(query_norm, service_key)
    if not column_key:
        destinos = ", ".join(label for _, label in TARIFF_TABLES[service_key]["columns"])
        return {
            "mode": "ask",
            "prompt_context": (
                f"Ya tengo el peso {_format_weight(weight_g)} para {TARIFF_TABLES[service_key]['label']}. "
                f"Ahora necesito el destino o modalidad. Opciones: {destinos}."
            ),
            "sources": [TARIFF_SOURCE],
            "primary_source_type": "tariff_engine",
        }

    table = TARIFF_TABLES[service_key]
    row = _find_row(table["rows"], weight_g)
    if not row:
        return {
            "mode": "answer",
            "prompt_context": (
                f"No encontré un rango tarifario aplicable para {TARIFF_TABLES[service_key]['label']} "
                f"con peso {_format_weight(weight_g)}."
            ),
            "sources": [TARIFF_SOURCE],
            "primary_source_type": "tariff_engine",
        }

    columns_map = {key: idx for idx, (key, _) in enumerate(table["columns"])}
    value = row["values"][columns_map[column_key]]
    all_amounts = "; ".join(
        f"{label}: Bs {_format_money(row['values'][idx])}"
        for idx, (_, label) in enumerate(table["columns"])
    )

    return {
        "mode": "answer",
        "prompt_context": (
            f"Servicio identificado: {table['label']}.\n"
            f"Peso consultado: {_format_weight(weight_g)}.\n"
            f"Rango aplicable: {row['line']}.\n"
            f"Destino/modalidad: {column_label}.\n"
            f"Monto calculado: Bs {_format_money(value)}.\n"
            f"Montos de la fila completa: {all_amounts}."
        ),
        "sources": [TARIFF_SOURCE],
        "primary_source_type": "tariff_engine",
        "tariff_result": {
            "service": table["label"],
            "weight_g": weight_g,
            "destination": column_label,
            "amount_bs": value,
            "matched_range": row["line"],
        },
    }
