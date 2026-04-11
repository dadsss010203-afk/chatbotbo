#!/usr/bin/env python3
"""
Motor de calculo para Hoja 1 (Table 1) sin dependencias externas.
Preparado para integracion en chatbot con Excel fuera de esta carpeta.

Uso:
  python3 runtime/calcular_hoja1_runtime.py --xlsx '/ruta/Tarifario.xlsx' --peso 500g --columna I
  python3 runtime/calcular_hoja1_runtime.py --xlsx '/ruta/Tarifario.xlsx' --peso 2.5kg --servicio 'Riberalta- Guayaramerín'
"""

import argparse
from pathlib import Path
import re
import zipfile
import xml.etree.ElementTree as ET

SHEET_NAME = "Table 1"
DEFAULT_XLSX = Path(__file__).resolve().parent.parent / "data" / "Tarifario_Hoja1.xlsx"

NS = {"a": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
REL_NS = {"r": "http://schemas.openxmlformats.org/package/2006/relationships"}

COLUMNAS = {
    "C": "EMS Local Cobertura 1",
    "D": "EMS Local Cobertura 2",
    "E": "EMS Local Cobertura 3",
    "F": "EMS Local Cobertura 4",
    "G": "EMS Nacional",
    "H": "Ciudades Intermedias",
    "I": "Trinidad- Cobija",
    "J": "Riberalta- Guayaramerín",
}


def parse_peso_to_grams(texto: str) -> float:
    if texto is None:
        raise ValueError("Peso vacio")
    t = texto.strip().lower().replace(" ", "").replace(",", ".")
    m = re.match(r"^([0-9]*\.?[0-9]+)(kg|g)$", t)
    if not m:
        raise ValueError(f"Formato de peso invalido: {texto}")
    valor = float(m.group(1))
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
        for row_idx in range(8, 30):
            row = data.get(row_idx, {})
            min_raw = row.get(1)
            max_raw = row.get(2)
            if not min_raw or not max_raw:
                continue
            min_g = parse_peso_to_grams(min_raw)
            max_g = parse_peso_to_grams(max_raw)
            precios = {col: row.get(col_to_index(col)) for col in COLUMNAS.keys()}
            table.append({"min_g": min_g, "max_g": max_g, "precios": precios, "row_idx": row_idx})

        return table


def find_price(peso_gramos: float, columna: str, xlsx_path: str):
    tabla = load_table_rows(xlsx_path)
    col = columna.upper()
    if col not in COLUMNAS:
        raise ValueError(f"Columna invalida: {columna}. Usa una de {sorted(COLUMNAS.keys())}")

    prev_max = None
    for row in tabla:
        if peso_gramos >= row["min_g"] and peso_gramos <= row["max_g"]:
            value = row["precios"].get(col)
            return float(value) if value is not None and value != "" else None, row
        if prev_max is not None and peso_gramos > prev_max and peso_gramos < row["min_g"]:
            value = row["precios"].get(col)
            return float(value) if value is not None and value != "" else None, row
        prev_max = row["max_g"]
    return None, None


def find_col_by_service(nombre: str):
    nombre_norm = " ".join(nombre.lower().split())
    for col, label in COLUMNAS.items():
        if " ".join(label.lower().split()) == nombre_norm:
            return col
    raise ValueError(f"Servicio no reconocido: {nombre}")


def format_grams(value: float) -> str:
    rounded = round(value)
    if abs(value - rounded) < 1e-9:
        return str(int(rounded))
    return f"{value:.3f}".rstrip("0").rstrip(".")


def main():
    parser = argparse.ArgumentParser(description="Calcula tarifa Hoja 1 (EMS Nacional)")
    parser.add_argument(
        "--xlsx",
        default=str(DEFAULT_XLSX),
        help="Ruta absoluta o relativa al archivo xlsx (por defecto usa backend/app/skills/skill1/data/Tarifario_Hoja1.xlsx)",
    )
    parser.add_argument("--peso", required=True, help="Peso con unidad, ej. 800g o 0.8kg")
    parser.add_argument("--columna", help="Columna C-J (ej. J)")
    parser.add_argument("--servicio", help="Nombre del servicio (ej. 'Riberalta- Guayaramerín')")
    parser.add_argument("--json", action="store_true", help="Salida en formato clave=valor")
    args = parser.parse_args()

    if not args.columna and not args.servicio:
        raise SystemExit("Debes indicar --columna o --servicio")
    if not Path(args.xlsx).exists():
        raise SystemExit(f"No se encontro el archivo xlsx: {args.xlsx}")

    col = args.columna if args.columna else find_col_by_service(args.servicio)
    peso_g = parse_peso_to_grams(args.peso)
    precio, row = find_price(peso_g, col, args.xlsx)

    if precio is None:
        print("Peso fuera de rango o precio vacio")
        return

    if args.json:
        print(f"precio={precio:.0f}")
        print(f"columna={col.upper()}")
        print(f"servicio={COLUMNAS[col.upper()]}")
        print(f"fila={row['row_idx']}")
        print(f"rango_min_g={format_grams(row['min_g'])}")
        print(f"rango_max_g={format_grams(row['max_g'])}")
        print(f"peso_g={format_grams(peso_g)}")
    else:
        print(f"{precio:.0f}")


if __name__ == "__main__":
    main()
