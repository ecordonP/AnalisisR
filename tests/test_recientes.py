import json

import AnalisisR as app


def test_recientes_conservan_cinco_ordenados_y_sin_duplicados(tmp_path, monkeypatch):
    monkeypatch.setattr(app.secrets, "config_dir", lambda: tmp_path)
    paths = [tmp_path / f"datos{i}.csv" for i in range(6)]
    for path in paths:
        app.remember_data_file(path)
    assert app.recent_data_files() == list(reversed(paths[1:]))
    app.remember_data_file(paths[3])
    expected = [paths[3], paths[5], paths[4], paths[2], paths[1]]
    assert app.recent_data_files() == expected
    assert json.loads((tmp_path / "recent_data.json").read_text(encoding="utf-8")) == [str(p) for p in expected]


def test_recientes_corruptos_no_impiden_arrancar(tmp_path, monkeypatch):
    monkeypatch.setattr(app.secrets, "config_dir", lambda: tmp_path)
    for text in ("invalid json", '{"other":1}', '[1,null]'):
        (tmp_path / "recent_data.json").write_text(text, encoding="utf-8")
        assert app.recent_data_files() == []
