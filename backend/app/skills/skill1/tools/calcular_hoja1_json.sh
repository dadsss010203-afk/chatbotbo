#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RUNTIME="$SCRIPT_DIR/../runtime/calcular_hoja1_runtime.py"

peso=""
columna=""
servicio=""
xlsx=""
pretty=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --peso)
      peso="${2:-}"; shift 2 ;;
    --columna)
      columna="${2:-}"; shift 2 ;;
    --servicio)
      servicio="${2:-}"; shift 2 ;;
    --xlsx)
      xlsx="${2:-}"; shift 2 ;;
    --pretty)
      pretty=1; shift ;;
    -h|--help)
      cat <<'USAGE'
Uso:
  backend/app/skills/skill1/tools/calcular_hoja1_json.sh --peso "500g" --columna "I" [--xlsx "/ruta.xlsx"] [--pretty]
  backend/app/skills/skill1/tools/calcular_hoja1_json.sh --peso "2.5kg" --servicio "Riberalta- Guayaramerín" [--xlsx "/ruta.xlsx"] [--pretty]
USAGE
      exit 0 ;;
    *)
      echo "{\"ok\":false,\"error\":\"Parametro no reconocido: $1\"}"
      exit 2 ;;
  esac
done

json_escape() {
  local s="${1:-}"
  s=${s//\\/\\\\}
  s=${s//"/\\"}
  s=${s//$'\n'/\\n}
  s=${s//$'\r'/}
  s=${s//$'\t'/\\t}
  printf '%s' "$s"
}

json_value() {
  local v="${1:-}"
  if [[ -z "$v" ]]; then
    printf 'null'
  elif [[ "$v" =~ ^-?[0-9]+([.][0-9]+)?$ ]]; then
    printf '%s' "$v"
  else
    printf '"%s"' "$(json_escape "$v")"
  fi
}

if [[ -z "$peso" ]]; then
  echo '{"ok":false,"error":"Falta --peso"}'
  exit 2
fi

if [[ -z "$columna" && -z "$servicio" ]]; then
  echo '{"ok":false,"error":"Debes indicar --columna o --servicio"}'
  exit 2
fi

cmd=(python3 "$RUNTIME" --peso "$peso" --json)
if [[ -n "$columna" ]]; then
  cmd+=(--columna "$columna")
fi
if [[ -n "$servicio" ]]; then
  cmd+=(--servicio "$servicio")
fi
if [[ -n "$xlsx" ]]; then
  cmd+=(--xlsx "$xlsx")
fi

set +e
output="$(${cmd[@]} 2>&1)"
status=$?
set -e

if [[ $status -ne 0 ]]; then
  if [[ $pretty -eq 1 ]]; then
    printf '{\n  "ok": false,\n  "exit_code": %s,\n  "error": "%s"\n}\n' "$status" "$(json_escape "$output")"
  else
    printf '{"ok":false,"exit_code":%s,"error":"%s"}\n' "$status" "$(json_escape "$output")"
  fi
  exit "$status"
fi

precio=""; columna_out=""; servicio_out=""; fila=""; rango_min_g=""; rango_max_g=""; peso_g=""
while IFS='=' read -r k v; do
  [[ -z "${k:-}" ]] && continue
  case "$k" in
    precio) precio="$v" ;;
    columna) columna_out="$v" ;;
    servicio) servicio_out="$v" ;;
    fila) fila="$v" ;;
    rango_min_g) rango_min_g="$v" ;;
    rango_max_g) rango_max_g="$v" ;;
    peso_g) peso_g="$v" ;;
  esac
done <<< "$output"

if [[ -z "$precio" && "$output" != *=* ]]; then
  if [[ $pretty -eq 1 ]]; then
    printf '{\n  "ok": false,\n  "error": "%s",\n  "raw": "%s"\n}\n' "No se pudo parsear salida del calculador" "$(json_escape "$output")"
  else
    printf '{"ok":false,"error":"No se pudo parsear salida del calculador","raw":"%s"}\n' "$(json_escape "$output")"
  fi
  exit 1
fi

if [[ $pretty -eq 1 ]]; then
  cat <<JSON
{
  "ok": true,
  "precio": $(json_value "$precio"),
  "columna": $(json_value "$columna_out"),
  "servicio": $(json_value "$servicio_out"),
  "fila": $(json_value "$fila"),
  "rango": {
    "min_g": $(json_value "$rango_min_g"),
    "max_g": $(json_value "$rango_max_g")
  },
  "peso_g": $(json_value "$peso_g")
}
JSON
else
  cat <<JSON
{"ok":true,"precio":$(json_value "$precio"),"columna":$(json_value "$columna_out"),"servicio":$(json_value "$servicio_out"),"fila":$(json_value "$fila"),"rango":{"min_g":$(json_value "$rango_min_g"),"max_g":$(json_value "$rango_max_g")},"peso_g":$(json_value "$peso_g")}
JSON
fi
