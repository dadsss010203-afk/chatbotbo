#!/usr/bin/env python3
"""Motor de calculo para Hoja 16 (Table 16) sin dependencias externas."""

import argparse
from pathlib import Path
import re
import zipfile
import xml.etree.ElementTree as ET

SHEET_NAME = "Table 16"
DEFAULT_XLSX = Path(__file__).resolve().parent.parent / "data" / "Tarifario_Hoja16.xlsx"

NS = {"a": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
REL_NS = {"r": "http://schemas.openxmlformats.org/package/2006/relationships"}

COLUMNAS = {
    "B": ["SUD AMERICA / Tarifa 1"],
    "C": ["Centro América y Florida EE.UU. / Tarifa 2"],
    "D": ["Resto de EEUU / Tarifa 3"],
    "E": ["CARIBE / Tarifa 4"],
    "F": ["EUROPA / Tarifa 5"],
    "G": ["MEDIO ORIENTE / Tarifa 6"],
    "H": ["AFRICA Y ASIA / Tarifa 7"],
}

WEIGHT_RE = re.compile(r"^([0-9]*\.?[0-9]+)(kg|g|gr)$")


def parse_peso_to_grams(texto: str) -> float:
    if texto is None:
        raise ValueError("Peso vacio")
    t = texto.strip().lower().replace(" ", "").replace(",", ".")
    t = t.replace(".kg", "kg").replace(".gr", "gr").replace(".g", "g")
    m = WEIGHT_RE.match(t)
    if not m:
        raise ValueError(f"Formato de peso invalido: {texto}")
    valor = float(m.group(1))
    if valor <= 0:
        raise ValueError(f"Peso invalido (debe ser > 0): {texto}")
    unidad = m.group(2)
    return valor * 1000.0 if unidad == "kg" else valor


def col_to_index(col: str) -> int:
    col = col.upper()
    n = 0
    for ch in col:
        n = n * 26 + (ord(ch) - 64)
    return n


def load_shared_strings(z: zipfile.ZipFile):
    sst = {}
    if "xl/sharedStrings.xml" not in z.namelist():
        return sst
    root = ET.fromstring(z.read("xl/sharedStrings.xml"))
    for i, si in enumerate(root.findall("a:si", NS)):
        texts = [t.text or "" for t in si.findall(".//a:t", NS)]
        sst[i] = "".join(texts)
    return sst


def cell_value(c, sst):
    t = c.attrib.get("t")
    v = c.find("a:v", NS)
    if v is None:
        return None
    if t == "s":
        return sst.get(int(v.text), "")
    return v.text


def resolve_sheet_path(z: zipfile.ZipFile, sheet_name: str) -> str:
    wb = ET.fromstring(z.read("xl/workbook.xml"))
    sheets = wb.findall("a:sheets/a:sheet", NS)
    rels = ET.fromstring(z.read("xl/_rels/workbook.xml.rels"))
    rid_to_target = {r.attrib["Id"]: r.attrib["Target"] for r in rels.findall("r:Relationship", REL_NS)}
    for s in sheets:
        if s.attrib.get("name") == sheet_name:
            rid = s.attrib["{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id"]
            target = rid_to_target[rid]
            return "xl/" + target.lstrip("/")
    raise ValueError(f"No se encontro la hoja: {sheet_name}")


def normalize_price(value: str):
    if value is None:
        return None
    v = str(value).strip()
    if v == "":
        return None
    if re.match(r"^[0-9]+$", v):
        return float(v)
    try:
        num = float(v)
        if num < 10 and "." in v:
            return float(int(round(num * 1000)))
        return float(f"{num:.3f}")
    except ValueError:
        return None


def load_table_rows(xlsx_path: str):
    with zipfile.ZipFile(xlsx_path) as z:
        sst = load_shared_strings(z)
        sheet_path = resolve_sheet_path(z, SHEET_NAME)
        root = ET.fromstring(z.read(sheet_path))
        rows = root.findall(".//a:sheetData/a:row", NS)

        data = {}
        for r in rows:
            row_idx = int(r.attrib.get("r", "0"))
            row_vals = {}
            for c in r.findall("a:c", NS):
                ref = c.attrib.get("r", "")
                col = ""
                for ch in ref:
                    if ch.isalpha():
                        col += ch
                    else:
                        break
                if not col:
                    continue
                row_vals[col_to_index(col)] = cell_value(c, sst)
            data[row_idx] = row_vals

        table = []
        for row_idx in range(6, 47):
            row = data.get(row_idx, {})
            w_raw = row.get(1)
            if not w_raw:
                continue
            try:
                w_g = parse_peso_to_grams(w_raw)
            except ValueError:
                continue
            precios = {col: normalize_price(row.get(col_to_index(col))) for col in COLUMNAS.keys()}
            table.append({"w_g": w_g, "precios": precios, "row_idx": row_idx})

        table.sort(key=lambda x: x["w_g"])
        return table


def find_price(peso_gramos: float, columna: str, xlsx_path: str):
    tabla = load_table_rows(xlsx_path)
    col = columna.upper()
    if col not in COLUMNAS:
        raise ValueError(f"Columna invalida: {columna}. Usa una de {sorted(COLUMNAS.keys())}")
    for row in tabla:
        if peso_gramos <= row["w_g"]:
            return row["precios"].get(col), row
    return None, None


def normalize_text(value: str) -> str:
    t = " ".join(value.lower().split())
    return (
        t.replace("á", "a")
        .replace("é", "e")
        .replace("í", "i")
        .replace("ó", "o")
        .replace("ú", "u")
        .replace("ñ", "n")
    )


def find_col_by_service(nombre: str):
    nombre_norm = normalize_text(nombre)
    for col, labels in COLUMNAS.items():
        for label in labels:
            if normalize_text(label) == nombre_norm:
                return col
    raise ValueError(f"Servicio no reconocido: {nombre}")


def service_label(col: str) -> str:
    return COLUMNAS[col][0]


def format_grams(value: float) -> str:
    rounded = round(value)
    if abs(value - rounded) < 1e-9:
        return str(int(rounded))
    return f"{value:.3f}".rstrip("0").rstrip(".")


def format_price(value: float) -> str:
    if value is None:
        return ""
    rounded = round(value)
    if abs(value - rounded) < 1e-9:
        return str(int(rounded))
    return f"{value:.3f}".rstrip("0").rstrip(".")


def main():
    parser = argparse.ArgumentParser(description="Calcula tarifa Hoja 16 (Table 16)")
    parser.add_argument(
        "--xlsx",
        default=str(DEFAULT_XLSX),
        help="Ruta absoluta o relativa al archivo xlsx (por defecto usa backend/app/skills/skill16/data/Tarifario_Hoja16.xlsx)",
    )
    parser.add_argument("--peso", required=True, help="Peso con unidad, ej. 800g o 0.8kg")
    parser.add_argument("--columna", help="Columna B-H (ej. B)")
    parser.add_argument("--servicio", help="Nombre del servicio (ej. 'SUD AMERICA / Tarifa 1')")
    parser.add_argument("--json", action="store_true", help="Salida en formato clave=valor")
    args = parser.parse_args()

    if not args.columna and not args.servicio:
        raise SystemExit("Debes indicar --columna o --servicio")
    if not Path(args.xlsx).exists():
        raise SystemExit(f"No se encontro el archivo xlsx: {args.xlsx}")

    try:
        col = args.columna.upper() if args.columna else find_col_by_service(args.servicio)
        peso_g = parse_peso_to_grams(args.peso)
        precio, row = find_price(peso_g, col, args.xlsx)
    except ValueError as exc:
        raise SystemExit(str(exc))

    if precio is None:
        print("Peso fuera de rango o precio vacio")
        return

    if args.json:
        print(f"precio={format_price(precio)}")
        print(f"columna={col}")
        print(f"servicio={service_label(col)}")
        print(f"fila={row['row_idx']}")
        print(f"rango_min_g={format_grams(row['w_g'])}")
        print(f"rango_max_g={format_grams(row['w_g'])}")
        print(f"peso_g={format_grams(peso_g)}")
    else:
        print(format_price(precio))


if __name__ == "__main__":
    main()
