import unittest

from core import tarifas_skill


class TestTarifasSkill(unittest.TestCase):
    def test_detecta_tarifa_nacional_con_alias_destino(self):
        req = tarifas_skill.parse_tarifa_request("precio 10 kilos rieral")
        self.assertTrue(req.is_tarifa)
        self.assertEqual(req.scope, "nacional")
        self.assertEqual(req.peso, "10kg")
        self.assertEqual(req.columna, "J")
        self.assertEqual(req.missing, [])

    def test_detecta_tarifa_nacional_por_servicio(self):
        req = tarifas_skill.parse_tarifa_request("ems nacional para 1.2kg")
        self.assertTrue(req.is_tarifa)
        self.assertEqual(req.scope, "nacional")
        self.assertEqual(req.family, "ems")
        self.assertEqual(req.columna, "G")

    def test_nacional_no_fija_familia(self):
        frag = tarifas_skill.extract_tarifa_fragment("nacional")
        self.assertEqual(frag.scope, "nacional")
        self.assertIsNone(frag.family)

    def test_detecta_tarifa_internacional(self):
        req = tarifas_skill.parse_tarifa_request("precio internacional 800g a europa")
        self.assertTrue(req.is_tarifa)
        self.assertEqual(req.scope, "internacional")
        self.assertEqual(req.columna, "F")

    def test_ambiguedad_pide_alcance(self):
        req = tarifas_skill.parse_tarifa_request("cuanto cuesta enviar 500g")
        self.assertTrue(req.is_tarifa)
        self.assertIn("alcance", req.missing)
        self.assertEqual(
            tarifas_skill.missing_message(req.missing),
            "¿Qué tarifario quieres usar?",
        )

    def test_ambiguedad_pide_alcance_encomienda(self):
        req = tarifas_skill.parse_tarifa_request("tarifa encomienda 500g")
        self.assertTrue(req.is_tarifa)
        self.assertIn("alcance_encomienda", req.missing)
        self.assertEqual(
            tarifas_skill.missing_message(req.missing),
            "¿Será nacional o internacional?",
        )

    def test_missing_message_tipo_nacional(self):
        self.assertEqual(
            tarifas_skill.missing_message(["tipo_nacional", "destino"]),
            "¿Qué servicio quieres usar?",
        )

    def test_detecta_intencion_tarifas_generica(self):
        req = tarifas_skill.parse_tarifa_request("quiero saber las tarifas")
        self.assertTrue(req.is_tarifa)
        self.assertIn("alcance", req.missing)

    def test_no_confunde_rastreo(self):
        req = tarifas_skill.parse_tarifa_request("quiero rastrear mi guia 12345")
        self.assertFalse(req.is_tarifa)

    def test_no_confunde_pregunta_informativa_ems(self):
        req = tarifas_skill.parse_tarifa_request("que es ems")
        self.assertFalse(req.is_tarifa)

    def test_resolve_columna_textual(self):
        self.assertEqual(tarifas_skill.resolve_columna("Cobija", scope="nacional"), "I")
        self.assertEqual(tarifas_skill.resolve_columna("columna h", scope="nacional"), "H")
        self.assertEqual(tarifas_skill.resolve_columna("europa", scope="internacional"), "F")
        self.assertEqual(tarifas_skill.resolve_columna("trinidad", scope="encomienda_nacional"), "D")
        self.assertEqual(tarifas_skill.resolve_columna("local", scope="ems_hoja5_nacional"), "C")
        self.assertEqual(tarifas_skill.resolve_columna("destino d", scope="ems_hoja6_internacional"), "F")
        self.assertEqual(tarifas_skill.resolve_columna("sud america", scope="super_express_documentos_internacional"), "B")

    def test_resolve_scope(self):
        self.assertEqual(tarifas_skill.resolve_scope("EMS Nacional"), "nacional")
        self.assertEqual(tarifas_skill.resolve_scope("tarifa internacional"), "internacional")
        self.assertEqual(tarifas_skill.resolve_scope("mi encomienda nacional"), "encomienda_nacional")
        self.assertEqual(tarifas_skill.resolve_scope("encomienda internacional"), "encomienda_internacional")
        self.assertEqual(tarifas_skill.resolve_scope("ems hoja 5"), "ems_hoja5_nacional")
        self.assertEqual(tarifas_skill.resolve_scope("ems hoja 6"), "ems_hoja6_internacional")
        self.assertEqual(tarifas_skill.resolve_scope("correo prioritario lc/ao nacional"), "ems_hoja5_nacional")
        self.assertEqual(tarifas_skill.resolve_scope("correo prioritario lc/ao internacional"), "ems_hoja6_internacional")
        self.assertEqual(tarifas_skill.resolve_scope("eca nacional"), "eca_nacional")
        self.assertEqual(tarifas_skill.resolve_scope("pliegos oficiales internacional"), "pliegos_internacional")
        self.assertEqual(tarifas_skill.resolve_scope("sacas m nacional"), "sacas_m_nacional")
        self.assertEqual(tarifas_skill.resolve_scope("ems contratos nacional"), "ems_contratos_nacional")
        self.assertEqual(tarifas_skill.resolve_scope("super express documentos internacional"), "super_express_documentos_internacional")

    def test_infer_scope_from_columna(self):
        self.assertEqual(tarifas_skill.infer_scope_from_columna("j"), "nacional")
        self.assertIsNone(tarifas_skill.infer_scope_from_columna("H"))
        self.assertIsNone(tarifas_skill.infer_scope_from_columna("F"))

    def test_extract_fragment_partial(self):
        frag = tarifas_skill.extract_tarifa_fragment("africa")
        self.assertEqual(frag.columna, "G")
        self.assertIsNone(frag.columna_scope)

    def test_detecta_tarifa_encomienda_nacional(self):
        req = tarifas_skill.parse_tarifa_request("mi encomienda prioritario nacional 900g ciudades capitales")
        self.assertTrue(req.is_tarifa)
        self.assertEqual(req.scope, "encomienda_nacional")
        self.assertEqual(req.columna, "C")

    def test_detecta_tarifa_encomienda_internacional(self):
        req = tarifas_skill.parse_tarifa_request("encomiendas postales internacional 800g africa")
        self.assertTrue(req.is_tarifa)
        self.assertEqual(req.scope, "encomienda_internacional")
        self.assertEqual(req.columna, "G")

    def test_detecta_tarifa_ems_hoja5_nacional(self):
        req = tarifas_skill.parse_tarifa_request("ems hoja 5 800g local")
        self.assertTrue(req.is_tarifa)
        self.assertEqual(req.scope, "ems_hoja5_nacional")
        self.assertEqual(req.columna, "C")

    def test_detecta_tarifa_ems_hoja6_internacional(self):
        req = tarifas_skill.parse_tarifa_request("ems hoja 6 800g destino d")
        self.assertTrue(req.is_tarifa)
        self.assertEqual(req.scope, "ems_hoja6_internacional")
        self.assertEqual(req.columna, "F")

    def test_columna_valida_para_scope(self):
        self.assertTrue(tarifas_skill.columna_valida_para_scope("I", "nacional"))
        self.assertFalse(tarifas_skill.columna_valida_para_scope("I", "internacional"))
        self.assertTrue(tarifas_skill.columna_valida_para_scope("B", "super_express_paquetes_internacional"))

    def test_detecta_tarifa_skill7_eca_nacional(self):
        req = tarifas_skill.parse_tarifa_request("eca nacional 900g local")
        self.assertTrue(req.is_tarifa)
        self.assertEqual(req.scope, "eca_nacional")
        self.assertEqual(req.columna, "C")

    def test_detecta_tarifa_skill8_eca_internacional(self):
        req = tarifas_skill.parse_tarifa_request("eca internacional 900g destino d")
        self.assertTrue(req.is_tarifa)
        self.assertEqual(req.scope, "eca_internacional")
        self.assertEqual(req.columna, "F")

    def test_detecta_tarifa_skill9_pliegos_nacional(self):
        req = tarifas_skill.parse_tarifa_request("pliegos oficiales nacional 1kg prov dentro depto")
        self.assertTrue(req.is_tarifa)
        self.assertEqual(req.scope, "pliegos_nacional")
        self.assertEqual(req.columna, "E")

    def test_detecta_tarifa_skill10_pliegos_internacional(self):
        req = tarifas_skill.parse_tarifa_request("pliegos oficiales internacional 1kg africa asia y oceania")
        self.assertTrue(req.is_tarifa)
        self.assertEqual(req.scope, "pliegos_internacional")
        self.assertEqual(req.columna, "G")

    def test_detecta_tarifa_skill11_sacas_nacional(self):
        req = tarifas_skill.parse_tarifa_request("sacas m nacional 700g provincial")
        self.assertTrue(req.is_tarifa)
        self.assertEqual(req.scope, "sacas_m_nacional")
        self.assertEqual(req.columna, "D")

    def test_detecta_tarifa_skill12_sacas_internacional(self):
        req = tarifas_skill.parse_tarifa_request("sacas m internacional 700g america del norte")
        self.assertTrue(req.is_tarifa)
        self.assertEqual(req.scope, "sacas_m_internacional")
        self.assertEqual(req.columna, "E")

    def test_detecta_tarifa_skill13_ems_contratos(self):
        req = tarifas_skill.parse_tarifa_request("ems contratos nacional 700g ciudades intermedias")
        self.assertTrue(req.is_tarifa)
        self.assertEqual(req.scope, "ems_contratos_nacional")
        self.assertEqual(req.columna, "D")

    def test_detecta_tarifa_skill14_super_express_nacional(self):
        req = tarifas_skill.parse_tarifa_request("super express nacional 700g")
        self.assertTrue(req.is_tarifa)
        self.assertEqual(req.scope, "super_express_nacional")

    def test_detecta_tarifa_skill15_super_express_documentos(self):
        req = tarifas_skill.parse_tarifa_request("super express documentos internacional 700g sud america")
        self.assertTrue(req.is_tarifa)
        self.assertEqual(req.scope, "super_express_documentos_internacional")
        self.assertEqual(req.columna, "B")

    def test_detecta_tarifa_skill16_super_express_paquetes(self):
        req = tarifas_skill.parse_tarifa_request("super express paquetes internacional 700g europa")
        self.assertTrue(req.is_tarifa)
        self.assertEqual(req.scope, "super_express_paquetes_internacional")
        self.assertEqual(req.columna, "F")


if __name__ == "__main__":
    unittest.main()
