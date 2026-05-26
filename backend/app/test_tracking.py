#!/usr/bin/env python3
"""Test rápido para verificar detección de códigos de seguimiento."""

import sys
import os

# Agregar el directorio al path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from core.capabilities import detectar_codigo_seguimiento, detectar_consulta_especial

# Tests
test_cases = [
    "C0007A02018BO",
    "R123456789BO",
    "ES123456789CN",
    "123456789012",
    "C123456789",
    "Hola, mi código es C0007A02018BO",
    "rastrear C0007A02018BO",
]

print("=" * 60)
print("TEST: Detección de códigos de seguimiento")
print("=" * 60)

for test in test_cases:
    codigo = detectar_codigo_seguimiento(test)
    consulta = detectar_consulta_especial(test)
    print(f"\nEntrada: '{test}'")
    print(f"  → Código detectado: {codigo}")
    print(f"  → Consulta especial: {consulta}")

print("\n" + "=" * 60)
print("Test completado")
print("=" * 60)
