import pandas as pd

from observatorio.core.http import DataSourceError
from observatorio.data import loaders
from observatorio.data.pipeline import load_all


def indicator(name: str) -> pd.DataFrame:
    return pd.DataFrame([{
        "departamento": "Nariño", "codigo_divipola": "52", "anio": 2020,
        "indicador": name, "categoria": "Prueba", "valor": 1.0,
        "unidad": "u", "fuente": "test", "fuente_url": "",
    }])


def test_poverty_timeout_does_not_skip_gini(monkeypatch):
    def get_json(source, url, params):
        if "incidencia de pobreza" in source:
            raise DataSourceError("DANE timeout")
        return {"features": [{"attributes": {
            "DPTO_CNMBR": "Nariño", "DPTO_CCDGO": "52", "GINI_2012": 0.5,
        }}]}

    monkeypatch.setattr(loaders, "get_json", get_json)
    quality = []
    result = loaders.load_poverty_gini(quality)

    assert len(result) == 1
    assert result[0]["indicador"].tolist() == ["Coeficiente de Gini"]
    assert any(row.get("Estado") == "No disponible" for row in quality)


def test_one_failed_loader_does_not_stop_later_sources(monkeypatch):
    monkeypatch.setattr(loaders, "load_population", lambda quality: pd.DataFrame())
    monkeypatch.setattr(loaders, "load_gdp", lambda population, quality: [indicator("PIB")])
    monkeypatch.setattr(loaders, "load_homicides", lambda population, quality: [indicator("Homicidios")])
    monkeypatch.setattr(loaders, "load_finance", lambda population, quality: [indicator("Finanzas")])

    def fail_poverty(quality):
        raise DataSourceError("DANE timeout")

    monkeypatch.setattr(loaders, "load_poverty_gini", fail_poverty)
    monkeypatch.setattr(loaders, "load_education", lambda quality: [indicator("Educación")])
    monkeypatch.setattr(loaders, "load_ctei", lambda quality: [indicator("CTeI")])

    master, quality = load_all()

    assert {"PIB", "Homicidios", "Finanzas", "Educación", "CTeI"}.issubset(set(master.indicador))
    assert (quality["Estado"] == "No disponible").any()
