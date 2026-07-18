"""Export do golden template (Config Eng V2 / F3/A): estrutura, camadas física/horas/comercial,
e a view de download com gate."""
import json
from datetime import date

from django.contrib.auth import get_user_model
from django_tenants.test.cases import TenantTestCase as TestCase

from apps.accounts.models import UserProfile
from apps.engineering_params.models import ProcessParameter, Rate, TenantParamConfig
from apps.engineering_params import knob_template as kt


class ExportTemplateServiceTests(TestCase):
    def setUp(self):
        cfg = TenantParamConfig.get_solo()
        cfg.perda_por_familia = {**cfg.perda_por_familia, "espelho": 1.6}
        cfg.fator_correcao_mo = 1.2345
        cfg.save()
        Rate.objects.create(operacao="FURAR", rate_hh=110, rate_hm=80, valid_from=date.today())
        ProcessParameter.objects.create(operacao="FURAR", metodo="radial", material=None,
                                        valor="0.5", unidade="min/furo", valid_from=date.today())
        from apps.materials.models import Material, MaterialPrice
        m = Material.objects.create(sigla="SA-179")
        MaterialPrice.objects.create(material=m, forma="tubo", preco_brl_kg="13.5",
                                     valid_from=date.today())

    def test_estrutura_e_versao(self):
        t = kt.export_template()
        self.assertEqual(t["template_schema_version"], kt.TEMPLATE_SCHEMA_VERSION)
        self.assertEqual(t["kind"], kt.TEMPLATE_KIND)
        self.assertEqual(set(t["physical"]), set(kt.PHYSICAL_KNOBS))
        self.assertEqual(t["knob_registry"], list(kt.PHYSICAL_KNOBS))
        self.assertTrue(t["confidential"])            # incluiu comercial

    def test_fisica_reflete_o_cfg(self):
        t = kt.export_template()
        self.assertEqual(t["physical"]["perda_por_familia"]["espelho"], 1.6)

    def test_horas_e_comercial(self):
        t = kt.export_template()
        self.assertTrue(any(h["operacao"] == "FURAR" and h["valor"] == 0.5 for h in t["horas"]))
        com = t["commercial"]
        self.assertAlmostEqual(com["fator_correcao_mo"], 1.2345)
        self.assertTrue(any(r["operacao"] == "FURAR" and r["rate_hh"] == 110.0 for r in com["rates"]))
        self.assertTrue(any(p["material"] == "SA-179" and p["forma"] == "tubo"
                            for p in com["material_prices"]))

    def test_exclui_comercial(self):
        t = kt.export_template(include_commercial=False)
        self.assertIsNone(t["commercial"])
        self.assertFalse(t["confidential"])
        # física continua
        self.assertIn("setup_frac", t["physical"])


class ExportViewTests(TestCase):
    def setUp(self):
        self.client.defaults["HTTP_HOST"] = self.get_test_tenant_domain()

    def _login(self, role):
        u = get_user_model().objects.create_user(username=f"u_{role}", password="x")
        extra = {"crea_number": "CREA-x"} if role == UserProfile.ROLE_ENGENHEIRO else {}
        UserProfile.objects.create(user=u, full_name=role, role=role, **extra)
        self.client.login(username=f"u_{role}", password="x")

    def test_download_json_com_comercial(self):
        self._login(UserProfile.ROLE_ADMIN)
        r = self.client.get("/engenharia/knobs/exportar/")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r["Content-Type"], "application/json")
        self.assertIn("attachment", r["Content-Disposition"])
        data = json.loads(r.content)
        self.assertEqual(data["kind"], kt.TEMPLATE_KIND)
        self.assertIsNotNone(data["commercial"])

    def test_download_so_fisica(self):
        self._login(UserProfile.ROLE_ADMIN)
        r = self.client.get("/engenharia/knobs/exportar/?commercial=0")
        data = json.loads(r.content)
        self.assertIsNone(data["commercial"])

    def test_orcamentista_nao_exporta(self):
        self._login(UserProfile.ROLE_ORCAMENTISTA)
        r = self.client.get("/engenharia/knobs/exportar/")
        self.assertEqual(r.status_code, 403)
