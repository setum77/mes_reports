"""Тесты настроек окружений."""
import importlib
import sys

import pytest
from django.core.exceptions import ImproperlyConfigured


def _reload_prod():
    """Импортирует prod-настройки заново, без кеша модуля."""
    sys.modules.pop("mes_report3.settings.prod", None)
    try:
        return importlib.import_module("mes_report3.settings.prod")
    finally:
        sys.modules.pop("mes_report3.settings.prod", None)


def test_prod_settings_require_secret_key(monkeypatch):
    """prod-настройки не должны импортироваться без DJANGO_SECRET_KEY."""
    monkeypatch.delenv("DJANGO_SECRET_KEY", raising=False)

    with pytest.raises(ImproperlyConfigured):
        _reload_prod()


def test_prod_settings_accept_secret_key(monkeypatch):
    """При заданном ключе prod-настройки импортируются и используют его."""
    monkeypatch.setenv("DJANGO_SECRET_KEY", "test-secret-key")

    module = _reload_prod()

    assert module.SECRET_KEY == "test-secret-key"
