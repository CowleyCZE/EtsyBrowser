"""Smoke testy GUI: stránky se vykreslí, ochrana localhostu, nahrávání do fronty (bez sítě a bez Etsy)."""

import io
import json

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("httpx")
pytest.importorskip("multipart")

from fastapi.testclient import TestClient  # noqa: E402

from gui import app as gui_app  # noqa: E402
from gui import core  # noqa: E402
from src import jobs  # noqa: E402


@pytest.fixture
def client(tmp_path, monkeypatch):
    # Historie a logy úloh patří do dočasné složky, ne do projektu
    manager = jobs.JobManager(history_path=tmp_path / "history.json", log_dir=tmp_path / "logs")
    monkeypatch.setattr(jobs, "_manager", manager)
    return TestClient(gui_app.app, base_url="http://127.0.0.1:8080")


@pytest.mark.parametrize("path", ["/", "/generate", "/jobs", "/products", "/mockups", "/uploader", "/migrate", "/etsy", "/settings"])
def test_pages_render(client, path):
    response = client.get(path)
    assert response.status_code == 200, response.text[:300]


def test_non_local_host_is_rejected(tmp_path):
    foreign = TestClient(gui_app.app, base_url="http://evil.example")
    assert foreign.get("/").status_code == 403


def test_foreign_origin_post_is_rejected(client):
    response = client.post("/jobs/x/cancel", headers={"origin": "http://evil.example"}, follow_redirects=False)
    assert response.status_code == 403


def test_unknown_job_and_product_return_404(client):
    assert client.get("/jobs/neexistuje").status_code == 404
    assert client.post("/products/single/neexistuje/publish", follow_redirects=False).status_code == 404


def _png_bytes() -> bytes:
    from PIL import Image

    buffer = io.BytesIO()
    Image.new("RGB", (4, 4), "red").save(buffer, "PNG")
    return buffer.getvalue()


def test_mockup_preview_and_download(client, tmp_path, monkeypatch):
    pytest.importorskip("numpy")
    pytest.importorskip("automation.super_robot")
    from PIL import Image

    from gui import mockups

    templates = tmp_path / "tpl"
    templates.mkdir()
    Image.new("RGB", (200, 120), "white").save(templates / "t1.png")
    config = tmp_path / "templates.json"
    config.write_text(json.dumps({"Test": [{"filename": "t1.png", "x": 20, "y": 20, "w": 100, "h": 60}]}))
    monkeypatch.setattr(mockups, "TEMPLATES_DIR", templates)
    monkeypatch.setattr(mockups, "TEMPLATES_JSON", config)
    monkeypatch.setattr(mockups, "PREVIEW_DIR", tmp_path / "preview")
    monkeypatch.setattr(core, "ENV_PATH", tmp_path / "none.env")  # bez TEST_ART_PATH ze skutečného .env
    monkeypatch.delenv("TEST_ART_PATH", raising=False)

    assert "t1.png" in client.get("/mockups?template=t1.png").text
    assert client.get("/mockups/render?template=t1.png").status_code == 409  # zatím žádný obrázek

    upload = client.post("/mockups/art", files={"file": ("art.png", _png_bytes(), "image/png")},
                         data={"template": "t1.png"}, follow_redirects=False)
    assert upload.status_code == 303

    preview = client.get("/mockups/render?template=t1.png")
    assert preview.status_code == 200 and preview.headers["content-type"] == "image/jpeg"
    download = client.get("/mockups/render?template=t1.png&download=1")
    assert download.headers["content-disposition"].startswith("attachment")
    assert client.get("/mockups/render?template=nope.png").status_code == 404
    assert client.get("/mockups/template/nope.png").status_code == 404

    assert client.post("/mockups/art/clear", follow_redirects=False).status_code == 303
    assert client.get("/mockups/render?template=t1.png").status_code == 409


def test_uploader_csv_editor_and_run(client, tmp_path, monkeypatch):
    import csv

    from gui import csvtools, tasks

    path = tmp_path / "products.csv"
    path.write_text('title,description,price,quantity\n"A","desc A",5.5,3\n"B","desc B",,7\n', encoding="utf-8")
    monkeypatch.setattr(csvtools, "CSV_PATH", path)
    monkeypatch.setattr(core, "ENV_PATH", tmp_path / "none.env")
    monkeypatch.setattr(core, "CONFIG_PATH", tmp_path / "none.json")
    for key in ("ETSY_EMAIL", "ETSY_PASSWORD"):
        monkeypatch.delenv(key, raising=False)

    assert "desc A" in client.get("/uploader").text

    empty = {f"f2__{c}": "" for c in ("description", "tags", "category_path", "image_paths", "shop_section_id", "quantity")}
    form = {"row_count": "2", "f0__title": "A2", "f0__description": "desc A", "f0__price": "5,5",
            "f0__quantity": "3", "f1__title": "B", "del1": "on", "f2__title": "C", "f2__price": "7", **empty}
    bad = client.post("/uploader/csv", data={**form, "f2__price": "abc"}, follow_redirects=False)
    assert bad.status_code == 400
    assert "A2" not in path.read_text(encoding="utf-8")  # chybný formulář soubor nezmění

    assert client.post("/uploader/csv", data=form, follow_redirects=False).status_code == 303
    with open(path, encoding="utf-8", newline="") as handle:
        saved = list(csv.DictReader(handle))
    assert [r["title"] for r in saved] == ["A2", "C"]          # B smazán, C přidán
    assert saved[0]["price"] == "5.5" and saved[0]["quantity"] == "3"  # nezobrazený sloupec zůstal
    assert "tags" in saved[0]

    no_confirm = client.post("/uploader/run", data={"mode": "visible"}, follow_redirects=False)
    assert no_confirm.status_code == 303 and "kind=warn" in no_confirm.headers["location"]
    no_creds = client.post("/uploader/run", data={"confirm": "on"}, follow_redirects=False)
    assert no_creds.status_code == 303 and "kind=bad" in no_creds.headers["location"]

    monkeypatch.setenv("ETSY_EMAIL", "a@b.c")
    monkeypatch.setenv("ETSY_PASSWORD", "x")
    monkeypatch.setattr(tasks, "run_uploader", lambda headless=False: "ok")
    started = client.post("/uploader/run", data={"confirm": "on", "mode": "headless"}, follow_redirects=False)
    assert started.status_code == 303 and started.headers["location"].startswith("/jobs/")


def test_migrate_page_and_run(client, tmp_path, monkeypatch):
    from gui import tasks

    source = tmp_path / "old"
    (source / "SeAForest").mkdir(parents=True)
    (source / "SeAForest" / "Art.png").write_bytes(b"png")

    page = client.get("/migrate", params={"source": str(source)})
    assert page.status_code == 200 and "SeAForest" in page.text
    missing = client.get("/migrate", params={"source": str(tmp_path / "neni")})
    assert missing.status_code == 200 and "neexistuje" in missing.text

    no_confirm = client.post("/migrate/run", data={"source": str(source)}, follow_redirects=False)
    assert no_confirm.status_code == 303 and "kind=warn" in no_confirm.headers["location"]
    bad_dir = client.post("/migrate/run", data={"source": str(tmp_path / "neni"), "confirm": "on"}, follow_redirects=False)
    assert "kind=bad" in bad_dir.headers["location"]

    monkeypatch.setattr(tasks, "run_migration", lambda source: "ok")
    started = client.post("/migrate/run", data={"source": str(source), "confirm": "on"}, follow_redirects=False)
    assert started.status_code == 303 and started.headers["location"].startswith("/jobs/")


def test_template_editor_saves_validates_and_removes(client, tmp_path, monkeypatch):
    from PIL import Image

    from gui import mockups

    templates = tmp_path / "tpl"
    templates.mkdir()
    Image.new("RGB", (400, 300), "white").save(templates / "t1.png")
    config = tmp_path / "templates.json"
    config.write_text(json.dumps({"Stara": [{"filename": "jina.png", "x": 1, "y": 1, "w": 5, "h": 5}]}))
    monkeypatch.setattr(mockups, "TEMPLATES_DIR", templates)
    monkeypatch.setattr(mockups, "TEMPLATES_JSON", config)

    page = client.get("/mockups/editor?template=t1.png")
    assert page.status_code == 200 and "400" in page.text
    assert client.get("/mockups/editor?template=nope.png").status_code == 404

    def save(mode, points, category="Nova"):
        return client.post("/mockups/editor/save", follow_redirects=False,
                           data={"template": "t1.png", "mode": mode, "points": json.dumps(points),
                                 "category_select": "__new__", "category_new": category})

    assert save("perspective", [[50, 40], [350, 30], [350, 250], [50, 260]]).status_code == 303
    saved = json.loads(config.read_text())
    entry = saved["Nova"][0]
    assert entry["filename"] == "t1.png" and entry["corners"][1] == [350, 30]
    assert (entry["x"], entry["y"], entry["w"], entry["h"]) == (50, 30, 300, 230)
    assert saved["Stara"][0]["filename"] == "jina.png"  # cizi konfigurace zustava

    # špatné pořadí bodů (křížení), mimo obrázek a nesprávný počet bodů se neuloží
    assert save("perspective", [[50, 40], [350, 250], [350, 30], [50, 260]]).status_code == 400
    assert save("perspective", [[50, 40], [999, 30], [350, 250], [50, 260]]).status_code == 400
    assert save("rect", [[10, 10]]).status_code == 400
    assert json.loads(config.read_text()) == saved

    # přepnutí na obdélník přesune šablonu a ztratí corners
    assert save("rect", [[20, 20], [220, 170]], "Stara").status_code == 303
    saved = json.loads(config.read_text())
    assert saved["Nova"] == []
    assert [c for c in saved["Stara"] if c["filename"] == "t1.png"] == [
        {"filename": "t1.png", "x": 20, "y": 20, "w": 200, "h": 150}]

    removed = client.post("/mockups/editor/remove", data={"template": "t1.png"}, follow_redirects=False)
    assert removed.status_code == 303
    assert all(c["filename"] != "t1.png" for cs in json.loads(config.read_text()).values() for c in cs)


def test_upload_accepts_images_and_rejects_other_files(client, tmp_path, monkeypatch):
    queue_dir = tmp_path / "queue"
    monkeypatch.setattr(core, "TO_EDIT_DIR", queue_dir)

    files = [
        ("files", ("../../evil name.png", _png_bytes(), "image/png")),
        ("files", ("notes.txt", b"text", "text/plain")),
        ("files", ("fake.png", b"not an image", "image/png")),
    ]
    response = client.post("/generate/upload", files=files, follow_redirects=False)
    assert response.status_code == 303

    saved = sorted(p.name for p in queue_dir.iterdir())
    assert saved == ["evil_name.png"]  # cesta v názvu je zahozena, text i falešný obrázek odmítnuty
