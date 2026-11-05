"""La sintaxis se valida antes de calcular y se corrige sin compartir datos."""
import pytest

import AnalisisR as app


BAD_CODE = 'cat(dat$SALARIO[1]); resultado <- data.frame(Valor=1\nif (TRUE) print(1)'
GOOD_CODE = 'tabla(as.data.frame.matrix(with(dat, table(SALARIO, ESTUDIOS))))'


@pytest.fixture
def data(tmp_path):
    rs = app.engine.find_rscript()
    if not rs:
        pytest.skip("Requiere Rscript")
    source = tmp_path / "source.csv"
    source.write_text("SALARIO,ESTUDIOS\nVALOR_PRIVADO_A,basico\nVALOR_PRIVADO_B,superior\n", encoding="utf-8")
    profile = app.prepare_data({"data": str(source)}, tmp_path)
    return rs, profile, tmp_path


class Backend:
    last_truncated = False

    def __init__(self, responses):
        self.responses = iter(responses)
        self.prompts = []

    def chat(self, system, user):
        self.prompts.append(user)
        return next(self.responses)


def test_if_inesperado_se_detecta_sin_ejecutar_el_codigo(data, monkeypatch):
    rs, profile, _ = data
    calls = []
    run = app.engine.run_process

    def record(command, **kwargs):
        calls.append(command)
        return run(command, **kwargs)

    monkeypatch.setattr(app.engine, "run_process", record)
    with pytest.raises(app.engine.RSyntaxError) as error:
        app.engine.chat_run_r(BAD_CODE, profile, rs)
    assert "if" in str(error.value)
    assert len(calls) == 1 and "-e" in calls[0]
    assert "VALOR_PRIVADO" not in str(error.value)


def test_corrige_la_sintaxis_y_calcula_sin_compartir_salida(data):
    _, profile, folder = data
    backend = Backend(["```r\n" + BAD_CODE + "\n```", "```r\n" + GOOD_CODE + "\n```"])
    result = app.converse({"ask": "Tabla SALARIO por ESTUDIOS", "profile": profile,
                           "run_r": True, "share_output": False}, folder, backend)
    assert len(backend.prompts) == 2
    assert "ERROR DE SINTAXIS" in backend.prompts[1]
    assert "VALOR_PRIVADO" not in "\n".join(backend.prompts)
    assert "VALOR\\_PRIVADO\\_A" in result["answer"]
    assert "VALOR_PRIVADO" not in result["context_answer"]
    assert "Resultado de R" in result["answer"]
    assert (folder / "sintaxis_1.txt").is_file()
    assert not (folder / "salida_1.txt").exists()
    assert (folder / "salida_2.txt").is_file()
    assert len(result["scripts"]) == 1


def test_reintentos_de_sintaxis_tienen_limite(data):
    _, profile, folder = data
    backend = Backend(["```r\n" + BAD_CODE + "\n```"] * 3)
    result = app.converse({"ask": "Contingencia", "profile": profile,
                           "run_r": True, "share_output": False}, folder, backend)
    assert len(backend.prompts) == 3
    assert "No se ejecutó" in result["answer"] and "sintaxis" in result["answer"]
    assert result["scripts"] == []
    assert not list(folder.glob("salida_*.txt"))


def test_error_de_ejecucion_con_texto_de_sintaxis_no_se_envia(data, monkeypatch):
    _, profile, folder = data
    private_output = "unexpected 'if': SALIDA_PRIVADA_DE_LOS_DATOS"
    monkeypatch.setattr(app.engine, "chat_run_r", lambda *a, **kw: (False, private_output))
    backend = Backend(["```r\n" + GOOD_CODE + "\n```"])
    result = app.converse({"ask": "Contingencia", "profile": profile,
                           "run_r": True, "share_output": False}, folder, backend)
    assert len(backend.prompts) == 1
    assert private_output in result["answer"]
    assert private_output not in "\n".join(backend.prompts)


def test_anterior_error_de_sintaxis_no_permite_simular_un_calculo(data):
    _, profile, folder = data
    backend = Backend(["```r\n" + BAD_CODE + "\n```", "No puedo corregirlo."])
    result = app.converse({"ask": "Contingencia", "profile": profile,
                           "run_r": True, "share_output": False}, folder, backend)
    assert "No se ejecutó" in result["answer"]
    assert not list(folder.glob("salida_*.txt"))
