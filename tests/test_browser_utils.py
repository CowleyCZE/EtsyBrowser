"""Testy pomocných funkcí prohlížeče (bez spouštění Chrome)."""

import os

import pytest

pytest.importorskip("selenium")
pytest.importorskip("selenium_stealth")
pytest.importorskip("webdriver_manager")

from src.browser_utils import _fix_driver_path, build_user_agent  # noqa: E402


def test_user_agent_uses_real_chrome_major_version():
    assert "Chrome/158.0.0.0 " in build_user_agent("158.0.8127.36")
    assert "Chrome/120.0.0.0 " in build_user_agent("")        # záložní hodnota, když verze chybí
    assert "Chrome/120.0.0.0 " in build_user_agent("neco")


def test_fix_driver_path_replaces_notice_file_with_chromedriver(tmp_path):
    notice = tmp_path / "THIRD_PARTY_NOTICES.chromedriver"
    notice.write_text("licence")
    driver = tmp_path / "chromedriver"
    driver.write_text("binary")
    driver.chmod(0o644)

    fixed = _fix_driver_path(str(notice))

    assert fixed == str(driver)
    if os.name == "posix":
        assert os.access(driver, os.X_OK)  # musí být spustitelný, jinak by hlásil Permission denied


def test_fix_driver_path_keeps_correct_path_and_missing_driver(tmp_path):
    driver = tmp_path / "chromedriver"
    driver.write_text("binary")
    assert _fix_driver_path(str(driver)) == str(driver)

    notice = tmp_path / "sub" / "LICENSE.chromedriver"
    notice.parent.mkdir()
    notice.write_text("x")
    assert _fix_driver_path(str(notice)) == str(notice)  # nic lepšího není, vrátí původní
