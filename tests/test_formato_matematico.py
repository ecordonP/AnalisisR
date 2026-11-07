"""Notación matemática legible sin modificar scripts ni estructura de tablas."""
import os

import pytest

import analisisr_docx as documents


EXAMPLE = r"Hipótesis: $H_0: \mu_{SEXO=0} = \mu_{SEXO=1}$ vs $H_1: \mu_{SEXO=0} \neq \mu_{SEXO=1}$."
EXPECTED = "Hipótesis: H₀: μ(SEXO=0) = μ(SEXO=1) vs H₁: μ(SEXO=0) ≠ μ(SEXO=1)."


@pytest.mark.parametrize("source,expected", [
    (EXAMPLE, EXPECTED),
    (r"\(R^2 = 0.8,\ p \leq 0.05\)", "R² = 0.8, p ≤ 0.05"),
    (r"$$\frac{\bar{x}_1-\bar{x}_2}{\sqrt{n}}$$", "\n\n(x̄₁-x̄₂)/(√(n))\n\n"),
    (r"\[\chi^2 \geq 3.84\]", "\n\nχ² ≥ 3.84\n\n"),
    ("Costes: $5 y $10. Valor 20 €.", "Costes: $5 y $10. Valor 20 €."),
    ("| Resultado |\n| --- |\n| \\[1\\] 2.5 |", "| Resultado |\n| --- |\n| \\[1\\] 2.5 |"),
    (r"No compatible: $\begin{matrix}1&2\end{matrix}$", r"No compatible: $\begin{matrix}1&2\end{matrix}$"),
])
def test_conversion_de_notacion_y_limites(source, expected):
    assert documents.readable_math(source) == expected


@pytest.mark.parametrize("code", [
    '`dat$SEXO; formula <- "$H_0$"`',
    '``r"`$H_0$`"``',
    '```r\nprint("$H_0$")\ndat$SEXO\n```',
    '~~~~r\nprint("$H_0$")\n~~~~',
    '```r\nprint("$H_0$")',
])
def test_codigo_literal_incluso_con_cerca_sin_cerrar(code):
    source = EXAMPLE + "\n\n" + code
    assert documents.readable_math(source) == EXPECTED + "\n\n" + code


def test_chat_formatea_formulas_negrita_y_tablas_sin_html_activo():
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    pytest.importorskip("PySide6")
    import analisisr_ui as ui

    qt = ui.QApplication.instance() or ui.QApplication([])
    browser = ui.QTextBrowser()
    source = ("**Contraste**\n\n" + EXAMPLE + "\n\n"
              "| Parámetro | Resultado |\n| --- | --- |\n| $\\mu$ | $p < 0.05$ |\n\n"
              '```r\nprint("$H_0$")\n```')
    ui.render_chat(browser, "AnalizaR Desktop", source)
    text = browser.toPlainText()
    assert EXPECTED in text and '**' not in text
    assert 'print("$H_0$")' in text
    tables = [frame for frame in browser.document().rootFrame().childFrames() if isinstance(frame, ui.QTextTable)]
    assert len(tables) == 1 and tables[0].columns() == 2
    assert tables[0].cellAt(1, 0).firstCursorPosition().block().text() == "μ"
    assert tables[0].cellAt(1, 1).firstCursorPosition().block().text() == "p < 0.05"
    assert browser.document().find("Contraste").charFormat().fontWeight() >= 700
    browser.close()
    qt.processEvents()


def test_word_muestra_formulas_y_conserva_r(tmp_path):
    docx = pytest.importorskip("docx")
    source = EXAMPLE + '\n\n| Símbolo | Valor |\n| --- | --- |\n| $\\mu$ | 1 |\n\n```r\nprint("$H_0$")\n```'
    output = documents.markdown_to_docx(source, tmp_path / "formulas.docx")
    report = docx.Document(output)
    assert EXPECTED in [p.text for p in report.paragraphs]
    assert report.tables[0].cell(1, 0).text == "μ"
    assert 'print("$H_0$")' in [p.text for p in report.paragraphs]
