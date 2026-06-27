"""
Testes de configuração de static files para produção.
Cobre: STORAGES dict em production.py, collectstatic, e serving de admin CSS.
"""
import os
import tempfile
from unittest import mock

from django.contrib.staticfiles import finders
from django.contrib.staticfiles.views import serve
from django.core.management import call_command
from django.test import RequestFactory, TestCase, override_settings


class ProductionStoragesSettingsTest(TestCase):
    """Verifica production.py: STORAGES dict, STATIC_URL e STATIC_ROOT."""

    def _load_production(self):
        env_override = {
            "FIELD_ENCRYPTION_KEY": "gq5BmjeBGD9Ji49jNTL6hSEj5woUlf515QRfBgcgSVU=",
            "DJANGO_SECRET_KEY": "test-secret-key-for-static-tests-only",
        }
        import importlib

        import smartquotation.settings.production as prod

        with mock.patch.dict(os.environ, env_override):
            importlib.reload(prod)
        return prod

    def test_storages_staticfiles_uses_whitenoise(self):
        """STORAGES.staticfiles backend deve usar whitenoise.storage.Compressed…"""
        prod = self._load_production()
        storages = getattr(prod, "STORAGES", None)
        self.assertIsNotNone(storages, "STORAGES dict deve estar definido em production.py")
        backend = storages.get("staticfiles", {}).get("BACKEND", "")
        self.assertIn(
            "whitenoise",
            backend,
            f"staticfiles backend deve usar whitenoise, mas é: {backend!r}",
        )
        self.assertIn(
            "CompressedManifest",
            backend,
            f"backend deve ser CompressedManifestStaticFilesStorage, mas é: {backend!r}",
        )

    def test_storages_default_is_set(self):
        """STORAGES.default backend deve estar definido em production.py."""
        prod = self._load_production()
        storages = getattr(prod, "STORAGES", {})
        default_backend = storages.get("default", {}).get("BACKEND", "")
        self.assertTrue(default_backend, "STORAGES.default.BACKEND não pode ser vazio")

    def test_static_root_is_app_staticfiles(self):
        """STATIC_ROOT deve ser /app/staticfiles em production.py."""
        prod = self._load_production()
        static_root = str(getattr(prod, "STATIC_ROOT", ""))
        self.assertEqual(
            static_root,
            "/app/staticfiles",
            f"STATIC_ROOT deve ser /app/staticfiles, mas é: {static_root!r}",
        )

    def test_static_url_is_slash_static(self):
        """STATIC_URL deve ser /static/ em production.py."""
        prod = self._load_production()
        static_url = getattr(prod, "STATIC_URL", "")
        self.assertEqual(
            static_url,
            "/static/",
            f"STATIC_URL deve ser /static/, mas é: {static_url!r}",
        )


class CollectStaticTest(TestCase):
    """collectstatic --noinput deve rodar sem erros e popular STATIC_ROOT."""

    def test_collectstatic_runs_and_populates_static_root(self):
        """collectstatic não falha e cria arquivos em STATIC_ROOT (incluindo admin CSS)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            with self.settings(
                STATIC_ROOT=tmpdir,
                STORAGES={
                    "default": {
                        "BACKEND": "django.core.files.storage.FileSystemStorage",
                    },
                    "staticfiles": {
                        "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage",
                    },
                },
            ):
                call_command("collectstatic", "--noinput", verbosity=0)

                # whitenoise gera versões com hash, mas base.css (ou base.<hash>.css) deve existir
                admin_css_dir = os.path.join(tmpdir, "admin", "css")
                self.assertTrue(
                    os.path.isdir(admin_css_dir),
                    f"admin/css/ deve existir em STATIC_ROOT={tmpdir} após collectstatic",
                )
                css_files = os.listdir(admin_css_dir)
                base_css = [f for f in css_files if f.startswith("base") and f.endswith(".css")]
                self.assertTrue(
                    base_css,
                    f"admin/css/base*.css deve existir após collectstatic. Encontrados: {css_files}",
                )

    def test_whitenoise_manifest_created(self):
        """collectstatic com CompressedManifest cria staticfiles.json (manifest de hashes)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            with self.settings(
                STATIC_ROOT=tmpdir,
                STORAGES={
                    "default": {
                        "BACKEND": "django.core.files.storage.FileSystemStorage",
                    },
                    "staticfiles": {
                        "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage",
                    },
                },
            ):
                call_command("collectstatic", "--noinput", verbosity=0)
                manifest = os.path.join(tmpdir, "staticfiles.json")
                self.assertTrue(
                    os.path.exists(manifest),
                    "staticfiles.json (manifest de cache-busting) deve existir após collectstatic",
                )


class AdminCSSServeTest(TestCase):
    """Admin CSS /static/admin/css/base.css retorna HTTP 200."""

    def test_admin_css_found_by_finders(self):
        """admin/css/base.css deve ser encontrado pelos staticfiles finders."""
        path = finders.find("admin/css/base.css")
        self.assertIsNotNone(
            path, "admin/css/base.css deve ser encontrado pelos staticfiles finders"
        )
        self.assertTrue(os.path.isfile(path))

    @override_settings(DEBUG=True)
    def test_admin_css_serve_returns_200(self):
        """GET /static/admin/css/base.css retorna HTTP 200 via staticfiles serve view."""
        factory = RequestFactory()
        request = factory.get("/static/admin/css/base.css")
        response = serve(request, "admin/css/base.css")
        self.assertEqual(
            response.status_code,
            200,
            "admin/css/base.css deve retornar 200; verifique staticfiles finders",
        )
