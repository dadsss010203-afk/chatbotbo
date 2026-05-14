import unittest
from unittest.mock import MagicMock, patch

from core import tarifas_skill


class TestTarifasPostarApi(unittest.TestCase):
    def test_groups_internacional(self):
        self.assertTrue(tarifas_skill.postar_scope_requires_destination_group("internacional"))
        self.assertFalse(tarifas_skill.postar_scope_requires_destination_group("nacional"))

        groups = tarifas_skill.postar_destination_group_quick_replies("internacional")
        self.assertEqual(len(groups), 5)
        self.assertTrue(str(groups[0].get("value")).startswith("DEST_GROUP::"))

    def test_resuelve_grupo_destino(self):
        g1 = tarifas_skill.resolve_postar_destination_group("América del Sur", "internacional")
        self.assertEqual(g1, "dest_a_")

        g2 = tarifas_skill.resolve_postar_destination_group("DEST_GROUP::dest_d_", "internacional")
        self.assertEqual(g2, "dest_d_")

    def test_destinos_por_grupo(self):
        south_america = tarifas_skill.postar_destination_quick_replies(
            "internacional",
            destination_group="dest_a_",
        )
        labels = {opt.get("label") for opt in south_america}
        self.assertIn("Argentina", labels)
        self.assertNotIn("Estados Unidos", labels)

    def test_resuelve_destino_postar_desde_label(self):
        col_nat = tarifas_skill.resolve_columna("Area Urbana (Hasta 2.5 Km)", scope="nacional")
        self.assertEqual(col_nat, "DEST::local_1")

        col_dep = tarifas_skill.resolve_columna("Santa Cruz", scope="nacional")
        self.assertEqual(col_dep, "DEST::nacional_santa_cruz")

        col_int = tarifas_skill.resolve_columna("Estados Unidos", scope="internacional")
        self.assertEqual(col_int, "DEST::dest_c_eeuu")

    def test_quick_replies_postar_nacional(self):
        options = tarifas_skill.postar_destination_quick_replies("nacional")
        labels = {opt.get("label") for opt in options}
        self.assertIn("Area Urbana (Hasta 2.5 Km)", labels)
        self.assertIn("Santa Cruz", labels)
        self.assertNotIn("Cobertura 1", labels)

    @patch("core.tarifas_skill.set_tariff")
    @patch("core.tarifas_skill.get_tariff", return_value=None)
    @patch("core.tarifas_skill.requests.post")
    def test_ejecutar_tarifa_postar_ok(self, mock_post, _mock_get_cache, _mock_set_cache):
        response = MagicMock()
        response.status_code = 200
        response.json.return_value = {
            "success": True,
            "categoria": "EMS INT",
            "peso": 0.8,
            "destino": "dest_d_espana",
            "tarifa": 186.2,
        }
        mock_post.return_value = response

        result = tarifas_skill.ejecutar_tarifa(
            peso="800g",
            columna="F",
            scope="internacional",
        )

        self.assertTrue(result["ok"])
        self.assertEqual(result["engine"], "postar_api")
        self.assertEqual(result["categoria"], "EMS INT")
        self.assertEqual(result["destino"], "dest_d_espana")
        self.assertEqual(result["precio"], 186.2)
        self.assertEqual(result["scope"], "internacional")
        self.assertEqual(result["skill_id"], tarifas_skill.SKILL_CONFIG["internacional"]["skill_id"])

        self.assertEqual(mock_post.call_count, 1)
        called_url = mock_post.call_args.kwargs["url"] if "url" in mock_post.call_args.kwargs else mock_post.call_args.args[0]
        self.assertEqual(called_url, tarifas_skill.POSTAR_API_URL)
        sent_payload = mock_post.call_args.kwargs["json"]
        self.assertEqual(sent_payload["categoria"], "EMS INT")
        self.assertEqual(sent_payload["destino"], "dest_d_espana")
        self.assertAlmostEqual(sent_payload["peso"], 0.8)

    def test_ejecutar_tarifa_scope_no_soportado_en_postar(self):
        result = tarifas_skill.ejecutar_tarifa(
            peso="700g",
            columna="B",
            scope="super_express_documentos_internacional",
        )
        self.assertFalse(result["ok"])
        self.assertIn("no está disponible", result["error"])
        self.assertEqual(result["engine"], "postar_api")

    @patch("core.tarifas_skill.get_tariff", return_value=None)
    @patch("core.tarifas_skill.requests.post")
    def test_ejecutar_tarifa_postar_con_token_destino(self, mock_post, _mock_get_cache):
        response = MagicMock()
        response.status_code = 200
        response.json.return_value = {
            "success": True,
            "categoria": "EMS NAT",
            "peso": 0.5,
            "destino": "nacional_santa_cruz",
            "tarifa": 42.0,
        }
        mock_post.return_value = response

        result = tarifas_skill.ejecutar_tarifa(
            peso="500g",
            columna="DEST::nacional_santa_cruz",
            scope="nacional",
        )

        self.assertTrue(result["ok"])
        self.assertEqual(result["destino"], "nacional_santa_cruz")
        sent_payload = mock_post.call_args.kwargs["json"]
        self.assertEqual(sent_payload["destino"], "nacional_santa_cruz")

    @patch("core.tarifas_skill.get_tariff", return_value=None)
    @patch("core.tarifas_skill.requests.post")
    def test_ejecutar_tarifa_out_of_range(self, mock_post, _mock_get_cache):
        response = MagicMock()
        response.status_code = 422
        response.json.return_value = {"message": "Peso fuera de rango para este tarifario"}
        response.text = "Peso fuera de rango para este tarifario"
        mock_post.return_value = response

        result = tarifas_skill.ejecutar_tarifa(
            peso="999kg",
            columna="F",
            scope="internacional",
        )

        self.assertFalse(result["ok"])
        self.assertEqual(result.get("error_code"), "out_of_range")
        self.assertEqual(result["engine"], "postar_api")


if __name__ == "__main__":
    unittest.main()
