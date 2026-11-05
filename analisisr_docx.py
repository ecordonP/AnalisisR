#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""analisisr_docx.py — exportación a Word (.docx) sin dependencias externas.

Un .docx es un ZIP con partes OOXML. Escribirlas directamente evita añadir
`python-docx` al proyecto, que se sostiene sobre la librería estándar (igual que
se prefirió DPAPI a `cryptography`). `python-docx` se usa **sólo en los tests**,
para comprobar con un lector independiente que el archivo es válido.

Cubre el subconjunto de Markdown que producen los informes de AnalisisR:
títulos, párrafos, negrita/cursiva/código, listas, citas, líneas y tablas.
"""

from __future__ import annotations

import datetime as _dt
import re
import zipfile
from pathlib import Path
from xml.sax.saxutils import escape
from analisisr_session import temporary_file, replace_file

NS_W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
NS_R = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"

CONTENT_TYPES = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
<Default Extension="xml" ContentType="application/xml"/>
<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>
<Override PartName="/word/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.styles+xml"/>
<Override PartName="/word/numbering.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.numbering+xml"/>
<Override PartName="/docProps/core.xml" ContentType="application/vnd.openxmlformats-package.core-properties+xml"/>
<Override PartName="/docProps/app.xml" ContentType="application/vnd.openxmlformats-officedocument.extended-properties+xml"/>
</Types>"""

RELS_ROOT = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>
<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties" Target="docProps/core.xml"/>
<Relationship Id="rId3" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/extended-properties" Target="docProps/app.xml"/>
</Relationships>"""

RELS_DOC = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>
<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/numbering" Target="numbering.xml"/>
</Relationships>"""

APP_PROPS = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Properties xmlns="http://schemas.openxmlformats.org/officeDocument/2006/extended-properties">
<Application>AnalisisR</Application>
</Properties>"""

# Estilos: cuerpo Calibri 11, títulos en azul corporativo, cita y código.
STYLES = f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:styles xmlns:w="{NS_W}">
<w:docDefaults><w:rPrDefault><w:rPr>
<w:rFonts w:ascii="Calibri" w:hAnsi="Calibri" w:cs="Calibri"/>
<w:sz w:val="22"/><w:szCs w:val="22"/><w:lang w:val="es-ES"/>
</w:rPr></w:rPrDefault>
<w:pPrDefault><w:pPr><w:spacing w:after="120" w:line="276" w:lineRule="auto"/></w:pPr></w:pPrDefault>
</w:docDefaults>
<w:style w:type="paragraph" w:default="1" w:styleId="Normal"><w:name w:val="Normal"/><w:qFormat/></w:style>
<w:style w:type="paragraph" w:styleId="Title"><w:name w:val="Title"/><w:basedOn w:val="Normal"/>
<w:qFormat/><w:pPr><w:spacing w:before="0" w:after="120"/></w:pPr>
<w:rPr><w:b/><w:sz w:val="48"/><w:szCs w:val="48"/><w:color w:val="1F3864"/></w:rPr></w:style>
<w:style w:type="paragraph" w:styleId="Subtitle"><w:name w:val="Subtitle"/><w:basedOn w:val="Normal"/>
<w:qFormat/><w:rPr><w:sz w:val="28"/><w:color w:val="2E5395"/></w:rPr></w:style>
<w:style w:type="paragraph" w:styleId="Heading1"><w:name w:val="heading 1"/><w:basedOn w:val="Normal"/>
<w:next w:val="Normal"/><w:qFormat/>
<w:pPr><w:keepNext/><w:spacing w:before="320" w:after="120"/><w:outlineLvl w:val="0"/></w:pPr>
<w:rPr><w:b/><w:sz w:val="32"/><w:szCs w:val="32"/><w:color w:val="1F3864"/></w:rPr></w:style>
<w:style w:type="paragraph" w:styleId="Heading2"><w:name w:val="heading 2"/><w:basedOn w:val="Normal"/>
<w:next w:val="Normal"/><w:qFormat/>
<w:pPr><w:keepNext/><w:spacing w:before="240" w:after="80"/><w:outlineLvl w:val="1"/></w:pPr>
<w:rPr><w:b/><w:sz w:val="26"/><w:szCs w:val="26"/><w:color w:val="1F3864"/></w:rPr></w:style>
<w:style w:type="paragraph" w:styleId="Heading3"><w:name w:val="heading 3"/><w:basedOn w:val="Normal"/>
<w:next w:val="Normal"/><w:qFormat/>
<w:pPr><w:keepNext/><w:spacing w:before="200" w:after="60"/><w:outlineLvl w:val="2"/></w:pPr>
<w:rPr><w:b/><w:sz w:val="24"/><w:color w:val="2E5395"/></w:rPr></w:style>
<w:style w:type="paragraph" w:styleId="Quote"><w:name w:val="Quote"/><w:basedOn w:val="Normal"/>
<w:pPr><w:ind w:left="454" w:right="454"/><w:pBdr><w:left w:val="single" w:sz="18" w:space="8" w:color="BFC8D6"/></w:pBdr></w:pPr>
<w:rPr><w:i/><w:color w:val="4B5768"/></w:rPr></w:style>
<w:style w:type="paragraph" w:styleId="ListParagraph"><w:name w:val="List Paragraph"/>
<w:basedOn w:val="Normal"/><w:pPr><w:spacing w:after="60"/></w:pPr></w:style>
<w:style w:type="character" w:styleId="CodeChar"><w:name w:val="Code Char"/>
<w:rPr><w:rFonts w:ascii="Consolas" w:hAnsi="Consolas"/><w:sz w:val="19"/>
<w:shd w:val="clear" w:color="auto" w:fill="F1F5F9"/></w:rPr></w:style>
<w:style w:type="paragraph" w:styleId="Footer"><w:name w:val="Footer"/><w:basedOn w:val="Normal"/>
<w:pPr><w:spacing w:before="240"/></w:pPr>
<w:rPr><w:sz w:val="17"/><w:color w:val="6B7280"/></w:rPr></w:style>
</w:styles>"""

# Una lista con viñeta y otra numerada; suficiente para los informes.
NUMBERING = f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:numbering xmlns:w="{NS_W}">
<w:abstractNum w:abstractNumId="0"><w:lvl w:ilvl="0"><w:start w:val="1"/>
<w:numFmt w:val="bullet"/><w:lvlText w:val="•"/><w:lvlJc w:val="left"/>
<w:pPr><w:ind w:left="454" w:hanging="227"/></w:pPr></w:lvl></w:abstractNum>
<w:abstractNum w:abstractNumId="1"><w:lvl w:ilvl="0"><w:start w:val="1"/>
<w:numFmt w:val="decimal"/><w:lvlText w:val="%1."/><w:lvlJc w:val="left"/>
<w:pPr><w:ind w:left="454" w:hanging="227"/></w:pPr></w:lvl></w:abstractNum>
<w:num w:numId="1"><w:abstractNumId w:val="0"/></w:num>
<w:num w:numId="2"><w:abstractNumId w:val="1"/></w:num>
</w:numbering>"""


# --------------------------------------------------------------------------- #
# Markdown -> bloques
# --------------------------------------------------------------------------- #

def _math_text(source: str) -> str:
    """Notación estadística habitual a Unicode, sin evaluar expresiones."""
    symbols = dict(zip(
        "alpha beta gamma delta epsilon varepsilon zeta eta theta lambda mu nu xi pi rho sigma tau phi psi omega Gamma Delta Theta Lambda Sigma Phi Omega".split(),
        "α β γ δ ε ε ζ η θ λ μ ν ξ π ρ σ τ φ ψ ω Γ Δ Θ Λ Σ Φ Ω".split()))
    symbols.update(dict(neq="≠", ne="≠", leq="≤", le="≤", geq="≥", ge="≥",
                        approx="≈", sim="∼", pm="±", times="×", cdot="·", infty="∞",
                        sum="∑", prod="∏", chi="χ", mid="│", vert="│",
                        to="→", rightarrow="→", Rightarrow="⇒", left="", right="",
                        log="log", ln="ln", exp="exp", min="min", max="max"))
    symbols["in"] = "∈"
    scripts = {
        "_": dict(zip("0123456789+-=()aehijklmnoprstuvx", "₀₁₂₃₄₅₆₇₈₉₊₋₌₍₎ₐₑₕᵢⱼₖₗₘₙₒₚᵣₛₜᵤᵥₓ")),
        "^": dict(zip("0123456789+-=()in", "⁰¹²³⁴⁵⁶⁷⁸⁹⁺⁻⁼⁽⁾ⁱⁿ")),
    }

    def group(pos):
        if pos >= len(source) or source[pos] != "{":
            raise ValueError("Falta un grupo matemático")
        depth, end = 1, pos + 1
        while end < len(source) and depth:
            if source[end] == "{" and source[end - 1] != "\\":
                depth += 1
            elif source[end] == "}" and source[end - 1] != "\\":
                depth -= 1
            end += 1
        if depth:
            raise ValueError("Grupo matemático incompleto")
        return source[pos + 1:end - 1], end

    out, i = [], 0
    while i < len(source):
        ch = source[i]
        i += 1
        if ch == "\\":
            command = re.match(r"[A-Za-z]+|.", source[i:])
            if not command:
                raise ValueError("Comando incompleto")
            name = command[0]
            i += len(name)
            if name in symbols:
                out.append(symbols[name])
            elif name in ("frac", "dfrac", "tfrac", "sqrt", "text", "mathrm", "mathbf", "operatorname", "hat", "bar", "overline"):
                while i < len(source) and source[i].isspace():
                    i += 1
                arg, i = group(i)
                value = arg if name in ("text", "mathrm", "operatorname") else _math_text(arg)
                if name in ("frac", "dfrac", "tfrac"):
                    while i < len(source) and source[i].isspace():
                        i += 1
                    denominator, i = group(i)
                    value = f"({value})/({_math_text(denominator)})"
                elif name == "sqrt":
                    value = f"√({value})"
                elif name in ("hat", "bar", "overline"):
                    value = value + ("\u0302" if name == "hat" else "\u0304")
                out.append(value)
            elif name in (",", ";", ":", " ", "quad", "qquad"):
                out.append(" ")
            elif name == "!":
                pass
            elif name in ("%", "_", "{", "}", "$", "&"):
                out.append(name)
            else:
                raise ValueError("Notación no compatible")
        elif ch in scripts:
            if i >= len(source):
                raise ValueError("Índice incompleto")
            if source[i] == "{":
                arg, i = group(i)
                value = _math_text(arg)
            else:
                value, i = source[i], i + 1
            mapping = scripts[ch]
            out.append("".join(mapping[c] for c in value) if all(c in mapping for c in value)
                       else ("(" + value + ")" if ch == "_" else "^(" + value + ")"))
        elif ch == "{":
            arg, i = group(i - 1)
            out.append(_math_text(arg))
        elif ch == "}":
            raise ValueError("Grupo matemático inválido")
        else:
            out.append(ch)
    return "".join(out)


def readable_math(md: str) -> str:
    """Prepara fórmulas para Markdown; conserva código, importes y fórmulas desconocidas."""
    pattern = re.compile(
        r"(?P<code>(?P<ticks>`+).*?(?P=ticks))|"
        r"\$\$(?P<display>.*?)\$\$|^ {0,3}\\\[(?P<bracket>.*?)\\\][ \t]*(?=\r?$)|"
        r"\\\((?P<paren>.*?)\\\)|(?<![\\$])\$(?![\s$])(?P<inline>[^\n$]*?\S)(?<!\\)\$(?!\w)",
        re.S | re.M)

    def replace(match):
        if match["code"]:
            return match[0]
        formula = next(match[name] for name in ("display", "bracket", "paren", "inline") if match[name] is not None)
        try:
            # shortcut: solo notación estadística común; ampliar ante nuevas estructuras LaTeX.
            text = _math_text(formula)
        except (ValueError, RecursionError):
            return match[0]
        text = re.sub(r"([\\`*_\[\]<>|])", r"\\\1", text)
        return "\n\n" + text.strip() + "\n\n" if match["display"] is not None or match["bracket"] is not None else text

    out, pending, fence = [], [], None
    for line in md.splitlines(keepends=True):
        marker = re.match(r"^ {0,3}(`{3,}|~{3,})(.*)$", line.rstrip("\r\n"))
        if fence:
            out.append(line)
            if marker and marker[1][0] == fence[0] and len(marker[1]) >= len(fence) and not marker[2].strip():
                fence = None
        elif marker:
            out.append(pattern.sub(replace, "".join(pending)))
            pending = []
            out.append(line)
            fence = marker[1]
        else:
            pending.append(line)
    out.append(pattern.sub(replace, "".join(pending)))
    return "".join(out)


def parse_markdown(md: str) -> list[dict]:
    """Convierte el Markdown de los informes en bloques simples.

    No pretende ser un parser completo: cubre lo que el sistema produce y trata
    cualquier otra línea como párrafo, que es el comportamiento seguro.
    """
    bloques: list[dict] = []
    lineas = readable_math(md).replace("\r\n", "\n").replace("\r", "\n").split("\n")
    i = 0
    while i < len(lineas):
        ln = lineas[i]
        txt = ln.strip()

        if not txt:
            i += 1
            continue
        if txt.startswith("```"):
            code = []
            i += 1
            while i < len(lineas) and not lineas[i].strip().startswith("```"):
                code.append(lineas[i])
                i += 1
            i += 1
            bloques.append({"tipo": "code", "texto": "\n".join(code)})
            continue
        if re.fullmatch(r"(-{3,}|\*{3,}|_{3,})", txt):
            bloques.append({"tipo": "hr"})
            i += 1
            continue
        m = re.match(r"^(#{1,6})\s+(.*)$", txt)
        if m:
            bloques.append({"tipo": "heading", "nivel": min(len(m.group(1)), 3),
                            "texto": m.group(2).strip()})
            i += 1
            continue
        # tabla: | a | b |  seguida de |---|---|
        if txt.startswith("|") and i + 1 < len(lineas) and \
                re.match(r"^\|[\s:\-|]+\|$", lineas[i + 1].strip()):
            filas = []
            cabecera = [c.strip().replace(r"\|", "|")
                        for c in re.split(r"(?<!\\)\|", txt.strip("|"))]
            i += 2
            while i < len(lineas) and lineas[i].strip().startswith("|"):
                filas.append([c.strip().replace(r"\|", "|") for c in
                              re.split(r"(?<!\\)\|", lineas[i].strip().strip("|"))])
                i += 1
            bloques.append({"tipo": "tabla", "cabecera": cabecera, "filas": filas})
            continue
        if txt.startswith(">"):
            cita = []
            while i < len(lineas) and lineas[i].strip().startswith(">"):
                cita.append(lineas[i].strip().lstrip(">").strip())
                i += 1
            bloques.append({"tipo": "quote", "texto": " ".join(c for c in cita if c)})
            continue
        m = re.match(r"^(\d+[.)])\s+(.*)$", txt)
        if m:
            items = []
            while i < len(lineas):
                mm = re.match(r"^(?:\d+[.)]|[-*+])\s+(.*)$", lineas[i].strip())
                if not mm:
                    break
                items.append(mm.group(1).strip())
                i += 1
            bloques.append({"tipo": "numbered", "items": items})
            continue
        if re.match(r"^[-*+]\s+", txt):
            items = []
            while i < len(lineas):
                mm = re.match(r"^[-*+]\s+(.*)$", lineas[i].strip())
                if not mm:
                    break
                items.append(mm.group(1).strip())
                i += 1
            bloques.append({"tipo": "bullets", "items": items})
            continue
        # párrafo: se unen líneas consecutivas
        parrafo = [txt]
        i += 1
        while i < len(lineas):
            sig = lineas[i].strip()
            if not sig or re.match(r"^(#{1,6}\s|[-*+]\s|\d+[.)]\s|>|\||-{3,})", sig):
                break
            parrafo.append(sig)
            i += 1
        bloques.append({"tipo": "paragraph", "texto": " ".join(parrafo)})
    return bloques


# --------------------------------------------------------------------------- #
# Ejecuciones con formato en línea
# --------------------------------------------------------------------------- #

def _runs(texto: str) -> str:
    """Convierte **negrita**, *cursiva* y `código` en runs con formato."""
    piezas: list[str] = []
    patron = re.compile(r"(\*\*.+?\*\*|__.+?__|\*[^*]+?\*|_[^_]+?_|`[^`]+?`)")
    for trozo in patron.split(texto):
        if not trozo:
            continue
        props: list[str] = []
        if (trozo.startswith("**") and trozo.endswith("**")) or \
           (trozo.startswith("__") and trozo.endswith("__")):
            trozo, props = trozo[2:-2], ["<w:b/>"]
        elif (trozo.startswith("*") and trozo.endswith("*") and len(trozo) > 2) or \
             (trozo.startswith("_") and trozo.endswith("_") and len(trozo) > 2):
            trozo, props = trozo[1:-1], ["<w:i/>"]
        elif trozo.startswith("`") and trozo.endswith("`") and len(trozo) > 2:
            trozo, props = trozo[1:-1], ['<w:rStyle w:val="CodeChar"/>']
        rpr = f"<w:rPr>{''.join(props)}</w:rPr>" if props else ""
        piezas.append(f'<w:r>{rpr}<w:t xml:space="preserve">{escape(trozo)}</w:t></w:r>')
    return "".join(piezas) or "<w:r><w:t/></w:r>"


def _parrafo(texto: str, estilo: str | None = None, num_id: int | None = None,
             alineacion: str | None = None) -> str:
    ppr: list[str] = []
    if estilo:
        ppr.append(f'<w:pStyle w:val="{estilo}"/>')
    if num_id:
        ppr.append(f'<w:numPr><w:ilvl w:val="0"/><w:numId w:val="{num_id}"/></w:numPr>')
    if alineacion:
        ppr.append(f'<w:jc w:val="{alineacion}"/>')
    ppr_xml = f"<w:pPr>{''.join(ppr)}</w:pPr>" if ppr else ""
    return f"<w:p>{ppr_xml}{_runs(texto)}</w:p>"


def _tabla(cabecera: list[str], filas: list[list[str]]) -> str:
    ancho = 9000 // max(len(cabecera), 1)
    bordes = ("<w:tblBorders>" + "".join(
        f'<w:{l} w:val="single" w:sz="4" w:space="0" w:color="C9D2DE"/>'
        for l in ("top", "left", "bottom", "right", "insideH", "insideV")) + "</w:tblBorders>")
    xml = [f'<w:tbl><w:tblPr><w:tblW w:w="{ancho * len(cabecera)}" w:type="dxa"/>{bordes}'
           '<w:tblLayout w:type="fixed"/></w:tblPr><w:tblGrid>'
           + "".join(f'<w:gridCol w:w="{ancho}"/>' for _ in cabecera)
           + "</w:tblGrid>"]

    def celda(texto: str, encabezado: bool) -> str:
        texto = re.sub(r"\\([\\`*_{}\[\]()#+.!<>|~-])", r"\1", texto)
        sombreado = '<w:shd w:val="clear" w:color="auto" w:fill="EEF2F7"/>' if encabezado else ""
        negrita = "<w:b/>" if encabezado else ""
        return (f'<w:tc><w:tcPr><w:tcW w:w="{ancho}" w:type="dxa"/>{sombreado}</w:tcPr>'
                f'<w:p><w:pPr><w:spacing w:after="0"/></w:pPr>'
                f'<w:r><w:rPr>{negrita}</w:rPr><w:t xml:space="preserve">'
                f'{escape(texto)}</w:t></w:r></w:p></w:tc>')

    if cabecera:
        xml.append("<w:tr>" + "".join(celda(c, True) for c in cabecera) + "</w:tr>")
    for fila in filas:
        xml.append("<w:tr>" + "".join(celda(c, False) for c in fila) + "</w:tr>")
    xml.append("</w:tbl>")
    # Word exige un párrafo tras una tabla antes del siguiente bloque
    xml.append("<w:p/>")
    return "".join(xml)


# --------------------------------------------------------------------------- #
# Escritura del paquete
# --------------------------------------------------------------------------- #

def _core_props(titulo: str) -> str:
    ahora = _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    return f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties"
 xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:dcterms="http://purl.org/dc/terms/"
 xmlns:dcmitype="http://purl.org/dc/dcmitype/" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
<dc:title>{escape(titulo)}</dc:title>
<dc:creator>AnalisisR</dc:creator>
<cp:lastModifiedBy>AnalisisR</cp:lastModifiedBy>
<dcterms:created xsi:type="dcterms:W3CDTF">{ahora}</dcterms:created>
<dcterms:modified xsi:type="dcterms:W3CDTF">{ahora}</dcterms:modified>
</cp:coreProperties>"""


def document_xml(bloques: list[dict], titulo: str | None = None,
                 subtitulo: str | None = None, pie: str | None = None) -> str:
    cuerpo: list[str] = []
    if titulo:
        cuerpo.append(_parrafo(titulo, "Title"))
    if subtitulo:
        cuerpo.append(_parrafo(subtitulo, "Subtitle"))
    for b in bloques:
        t = b["tipo"]
        if t == "heading":
            cuerpo.append(_parrafo(b["texto"], f"Heading{b['nivel']}"))
        elif t == "paragraph":
            cuerpo.append(_parrafo(b["texto"]))
        elif t == "code":
            for line in b["texto"].split("\n"):
                cuerpo.append('<w:p><w:pPr><w:spacing w:after="0"/></w:pPr>'
                              '<w:r><w:rPr><w:rStyle w:val="CodeChar"/></w:rPr>'
                              f'<w:t xml:space="preserve">{escape(line)}</w:t></w:r></w:p>')
        elif t == "quote":
            cuerpo.append(_parrafo(b["texto"], "Quote"))
        elif t == "bullets":
            for item in b["items"]:
                cuerpo.append(_parrafo(item, "ListParagraph", num_id=1))
        elif t == "numbered":
            for item in b["items"]:
                cuerpo.append(_parrafo(item, "ListParagraph", num_id=2))
        elif t == "tabla":
            cuerpo.append(_tabla(b["cabecera"], b["filas"]))
        elif t == "hr":
            cuerpo.append('<w:p><w:pPr><w:pBdr><w:bottom w:val="single" w:sz="6" '
                          'w:space="1" w:color="C9D2DE"/></w:pBdr></w:pPr></w:p>')
    if pie:
        cuerpo.append(_parrafo(pie, "Footer"))

    sect = ('<w:sectPr><w:pgSz w:w="11906" w:h="16838"/>'
            '<w:pgMar w:top="1134" w:right="1134" w:bottom="1134" w:left="1134" '
            'w:header="709" w:footer="709" w:gutter="0"/></w:sectPr>')
    return (f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            f'<w:document xmlns:w="{NS_W}" xmlns:r="{NS_R}">'
            f"<w:body>{''.join(cuerpo)}{sect}</w:body></w:document>")


def markdown_to_docx(markdown: str, out: Path, *, titulo: str | None = None,
                     subtitulo: str | None = None, pie: str | None = None) -> Path:
    """Escribe `out` (.docx) a partir del Markdown. Devuelve la ruta."""
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    nombre = titulo or out.stem
    partes = {
        "[Content_Types].xml": CONTENT_TYPES,
        "_rels/.rels": RELS_ROOT,
        "docProps/core.xml": _core_props(nombre),
        "docProps/app.xml": APP_PROPS,
        "word/_rels/document.xml.rels": RELS_DOC,
        "word/document.xml": document_xml(parse_markdown(markdown), titulo, subtitulo, pie),
        "word/styles.xml": STYLES,
        "word/numbering.xml": NUMBERING,
    }
    with temporary_file(".docx.tmp") as tmp:
        with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as z:
            for ruta, contenido in partes.items():
                z.writestr(ruta, contenido)
        replace_file(tmp, out)
    return out
