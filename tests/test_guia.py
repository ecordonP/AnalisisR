"""La guía local está completa y sus enlaces internos tienen destino."""
from html.parser import HTMLParser

import AnalisisR as app


def test_guia_tiene_destinos_para_su_indice_y_no_carga_recursos_remotos():
    class Guide(HTMLParser):
        def __init__(self):
            super().__init__()
            self.ids = []
            self.anchors = []
            self.remote_resources = []
            self.procedures = 0

        def handle_starttag(self, tag, attrs):
            attrs = dict(attrs)
            if "id" in attrs:
                self.ids.append(attrs["id"])
            if attrs.get("href", "").startswith("#"):
                self.anchors.append(attrs["href"][1:])
            if tag in ("script", "img", "link", "iframe") and (
                    attrs.get("src", "").startswith(("http:", "https:", "//")) or
                    attrs.get("href", "").startswith(("http:", "https:", "//"))):
                self.remote_resources.append(attrs)
            if tag == "tr" and attrs.get("class") == "procedimiento":
                self.procedures += 1

    page = (app.ROOT / "assets" / "guia.html").read_text(encoding="utf-8")
    guide = Guide()
    guide.feed(page)
    assert len(guide.ids) == len(set(guide.ids))
    assert set(guide.anchors) <= set(guide.ids)
    assert guide.procedures >= 30
    assert not guide.remote_resources


def test_la_guia_documenta_todas_las_plantillas_en_su_orden():
    """La lista de la guía y el desplegable de plantillas no pueden divergir."""
    import re

    page = (app.ROOT / "assets" / "guia.html").read_text(encoding="utf-8")
    seccion = page.split("<h3>Plantillas con procedimientos e interpretación</h3>", 1)[1].split("</ul>", 1)[0]
    documentadas = re.findall(r"<li><b>([^:<]+):</b>", seccion)
    assert documentadas == list(app.TEMPLATES)


def test_la_guia_describe_las_pestanas_reales():
    """Los nombres y el número de pestañas de la guía deben ser los de la ventana."""
    import re

    codigo = (app.ROOT / "AnalisisR.py").read_text(encoding="utf-8")
    pestanas = re.findall(r'addTab\(page, "([^"]+)"\)', codigo)
    page = (app.ROOT / "assets" / "guia.html").read_text(encoding="utf-8")
    tabla = page.split("<caption>Las cuatro pestañas de AnalisisR</caption>", 1)[1].split("</table>", 1)[0]
    assert len(pestanas) == 4
    assert re.findall(r"<tr><td>([^<]+)</td>", tabla) == pestanas


def test_la_guia_muestra_la_misma_version_que_el_codigo():
    import re

    page = (app.ROOT / "assets" / "guia.html").read_text(encoding="utf-8")
    mostrada = re.search(r'<span class="version">Versión ([0-9.]+)', page)
    assert mostrada and mostrada.group(1) == app.VERSION
