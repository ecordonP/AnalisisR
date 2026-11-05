"""Comprueba el onedir protegido con sus ejecutables y el R instalado en el sistema."""
from __future__ import annotations

import hashlib
import json
import marshal
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import zipfile

from PyInstaller.archive.readers import CArchiveReader


def verify(bundle: Path) -> dict:
    bundle = bundle.resolve()
    info = json.loads((bundle / "build-info.json").read_text(encoding="utf-8"))
    assert info["application"] == "AnalisisR" and info["format"] == "onedir"
    project = Path(__file__).resolve().parents[1]
    for name, digest in info["source_hashes"].items():
        assert hashlib.sha256((project / name).read_bytes()).hexdigest() == digest, f"Fuente modificada: {name}"
    for name, digest in info["executables"].items():
        assert hashlib.sha256((bundle / name).read_bytes()).hexdigest() == digest, name
        archive = CArchiveReader(str(bundle / name))
        assert "__pyarmor__" in marshal.loads(archive.extract("AnalisisR")).co_names
        pyz = archive.open_embedded_archive("PYZ.pyz")
        for module in info["protected"]:
            if module != "AnalisisR.py":
                assert "__pyarmor__" in pyz.extract(Path(module).stem).co_names, module

    root = bundle / "temporales"
    root.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="validacion_", dir=root) as directory:
        qa = Path(directory)
        env = dict(os.environ)
        # R_HOME y el PATH se quitan a propósito: la detección debe encontrar R por sí sola.
        for name in ("PYTHONHOME", "PYTHONPATH", "R_HOME", "R_LIBS", "R_LIBS_SITE", "QT_PLUGIN_PATH"):
            env.pop(name, None)
        # Se conserva la biblioteca personal de R, que es donde está instalado casi todo;
        # %v lo sustituye R por su versión. Sin esto el perfil aislado la ocultaría.
        env["R_LIBS_USER"] = os.environ.get("R_LIBS_USER") or str(
            Path(os.environ.get("LOCALAPPDATA", str(Path.home() / "AppData/Local"))) / "R" / "win-library" / "%v")
        windows = Path(os.environ.get("SystemRoot", "C:/Windows"))
        env.update(PATH=str(windows / "System32") + os.pathsep + str(windows),
                   APPDATA=str(qa / "config"), TEMP=str(qa), TMP=str(qa), TMPDIR=str(qa),
                   USERPROFILE=str(qa / "usuario"), HOME=str(qa / "usuario"), LOCALAPPDATA=str(qa / "local"),
                   QT_QPA_PLATFORM="offscreen", PYTHONDONTWRITEBYTECODE="1")
        worker = bundle / "AnalisisRWorker.exe"

        def operation(name, request, executable=worker):
            folder = qa / name
            folder.mkdir()
            path = folder / "request.json"
            path.write_text(json.dumps(request, ensure_ascii=False), encoding="utf-8")
            result = subprocess.run([str(executable), "--worker", str(path)], cwd=qa, env=env,
                                    capture_output=True, text=True, encoding="utf-8", errors="replace",
                                    timeout=300, creationflags=subprocess.CREATE_NO_WINDOW)
            response = json.loads((folder / "result.json").read_text(encoding="utf-8")) if (folder / "result.json").exists() else {}
            assert result.returncode == 0 and "error" not in response, response or result.stderr or result.stdout
            return response

        ui = operation("interfaz", {"action": "selftest"}, bundle / "AnalisisR.exe")
        assert ui["frozen"] and ui["tabs"] == 4 and ui["templates"] == 28 and ui["guide"] and ui["icon"]
        # El paquete no lleva R: el trabajador debe encontrar el del sistema sin PATH ni R_HOME.
        assert ui["r_ready"] and ui["rscript"]
        assert ui["max_tokens"] == 64000 and ui["timeout"] == 300
        assert Path(ui["tempdir"]).resolve().is_relative_to(root)
        assert Path(ui["session_folder"]).resolve().is_relative_to(root) and not Path(ui["session_folder"]).exists()
        diagnosis = operation("diagnostico", {"action": "diagnose"})
        rscript = Path(diagnosis["rscript"]).resolve()
        assert rscript.is_file() and not rscript.is_relative_to(bundle), "El paquete no debe incluir R."
        assert not (bundle / "runtime" / "R").exists(), "Se ha colado R portable en el paquete."
        assert diagnosis["packages"] and all(item["installed"] for item in diagnosis["packages"])

        source = qa / "datos.csv"
        source.write_text("x,grupo\n1,0\n2,1\n3,0\n", encoding="utf-8")
        profile = operation("csv", {"action": "profile", "data": str(source)})
        assert profile["n_rows"] == 3 and profile["n_cols"] == 2

        with zipfile.ZipFile(qa / "datos.xlsx", "w", zipfile.ZIP_DEFLATED) as xlsx:
            xlsx.writestr("[Content_Types].xml", '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/><Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/></Types>')
            xlsx.writestr("_rels/.rels", '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/></Relationships>')
            xlsx.writestr("xl/workbook.xml", '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets><sheet name="Datos" sheetId="1" r:id="rId1"/></sheets></workbook>')
            xlsx.writestr("xl/_rels/workbook.xml.rels", '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/></Relationships>')
            rows = '<row r="1"><c r="A1" t="inlineStr"><is><t>x</t></is></c><c r="B1" t="inlineStr"><is><t>grupo</t></is></c></row>'
            for number, group in enumerate((0, 1, 0), start=2):
                rows += f'<row r="{number}"><c r="A{number}"><v>{number-1}</v></c><c r="B{number}"><v>{group}</v></c></row>'
            xlsx.writestr("xl/worksheets/sheet1.xml", '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData>' + rows + '</sheetData></worksheet>')

        script = qa / "comprobar_r.R"
        script.write_text('''args <- commandArgs(TRUE)
set.seed(42)
z <- rnorm(150)
y <- as.data.frame(sapply(1:5,function(i) z+rnorm(150,sd=.7)))
names(y) <- paste0("item",1:5)
invisible(capture.output(a <- coefficientalpha::alpha(y,varphi=0,se=TRUE,test=TRUE,complete=TRUE)))
invisible(capture.output(o <- coefficientalpha::omega(y,varphi=0,se=TRUE,test=TRUE,complete=TRUE)))
stopifnot(is.finite(a$alpha),is.finite(o$omega),a$alpha>0,a$alpha<1,o$omega>0,o$omega<1)
haven::write_sav(data.frame(x=1:3,grupo=c(0,1,0)),file.path(args[1],"datos.sav"))
jsonlite::write_json(list(alfa=a$alpha,omega=o$omega,tempdir=tempdir()),file.path(args[1],"r_result.json"),auto_unbox=TRUE)
''', encoding="utf-8")
        result = subprocess.run([str(rscript), str(script), str(qa)],
                                cwd=qa, env=env, capture_output=True, text=True, encoding="utf-8",
                                errors="replace", timeout=300, creationflags=subprocess.CREATE_NO_WINDOW)
        assert result.returncode == 0, result.stderr or result.stdout
        statistical = json.loads((qa / "r_result.json").read_text(encoding="utf-8"))
        assert Path(statistical["tempdir"]).resolve().is_relative_to(root)
        spss = operation("spss", {"action": "profile", "data": str(qa / "datos.sav")})
        assert spss["n_rows"] == 3 and spss["n_cols"] == 2
        excel = operation("excel", {"action": "profile", "data": str(qa / "datos.xlsx")})
        assert excel["n_rows"] == 3 and excel["n_cols"] == 2

    report = {"protected_modules": info["protected"], "r_packages_checked": len(diagnosis["packages"]),
              "system_r": str(rscript), "bundled_r": False,
              "executables": info["executables"],
              "gui": True, "csv": True, "spss": True, "excel": True,
              "coefficientalpha": True, "all_temporaries_in_installation": True}
    (project / "build" / "validation.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report


if __name__ == "__main__":
    print(json.dumps(verify(Path(sys.argv[1])), ensure_ascii=False, indent=2))
