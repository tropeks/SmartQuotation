"""Regressão do filtro pt-BR `brl` (FINDING-001: valores em R$ sem separador de milhar)."""
from django.template import Context, Template
from django.test import SimpleTestCase


def _render(value, tag="|brl"):
    return Template("{% load money %}" + "{{ v" + tag + " }}").render(Context({"v": value}))


class BrlFilterTests(SimpleTestCase):
    def test_thousands_separator_two_decimals(self):
        self.assertEqual(_render(435060.55), "435.060,55")

    def test_millions(self):
        self.assertEqual(_render(1234567.5), "1.234.567,50")

    def test_zero_decimals_rounds_and_groups(self):
        self.assertEqual(_render(34860.0, "|brl:0"), "34.860")

    def test_small_value_no_group(self):
        self.assertEqual(_render(82.0), "82,00")
        self.assertEqual(_render(0.0), "0,00")

    def test_negative(self):
        self.assertEqual(_render(-1234.5), "-1.234,50")

    def test_non_numeric_passes_through(self):
        self.assertEqual(_render("N/A"), "N/A")
        self.assertEqual(_render(None), "None")
