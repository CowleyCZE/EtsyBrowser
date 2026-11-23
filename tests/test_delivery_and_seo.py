"""Testy doru\u010den\u00ed bundlu p\u0159es odkaz (B-4), sad mockup\u016f (B-7, B-9), bundlu (B-8), SEO a archivace SOLO (S-5, S-6)."""

import io
import json
import os

import pytest

pytest.importorskip("numpy")

from automation import super_robot as sr  # noqa: E402

SEO_SAMPLE = """TITLE: Misty Forest Castle Wall Art Printable Digital Download
DESCRIPTION: Moody landscape print. Instant digital download.
TAGS: wall art, printable, forest, castle, misty, moody, landscape, river, decor, digital, download, nature, poster
"""


def _redirect_dirs(monkeypatch, root):
    """P\u0159esm\u011brov\u00e1n\u00ed v\u0161ech pracovn\u00edch slo\u017eek super_robot do do\u010dasn\u00e9 slo\u017eky."""
    queue = root / "in" / "_To_Edit"
    queue.mkdir(parents=True)
    paths = {
        "INPUT_QUEUE_DIR": root / "in", "TO_EDIT_DIR": queue, "SOLO_INPUT_DIR": queue,
        "WAREHOUSE_DIR": root / "w", "SINGLES_DIR": root / "w" / "Singles", "BUNDLES_DIR": root / "w" / "Bundles",
        "ARCHIVE_ROOT_DIR": root / "arch", "TOPICS_PATH": root / "in" / "topics.json",
        "DATA_DIR": root / "d", "SKU_REGISTRY_PATH": root / "d" / "sku.json",
    }
    for name, value in paths.items():
        monkeypatch.setattr(sr, name, str(value))
    return queue


# --- B-4: PDF s odkazem a doru\u010den\u00ed p\u0159es odkaz ---

def test_link_pdf_is_wellformed(tmp_path):
    url = "https://drive.google.com/file/d/" + "a" * 100 + "/view?usp=sharing"
    path = tmp_path / "link.pdf"
    sr.write_link_pdf(str(path), "N\u00e1zev (test)", url, notes=("D\u00edky",))
    data = path.read_bytes()
    assert data.startswith(b"%PDF-1.4") and data.rstrip().endswith(b"%%EOF")
    assert b"/S /URI" in data
    startxref = int(data.split(b"startxref\n")[1].split(b"\n")[0])
    lines = data[startxref:].split(b"\n")
    assert lines[0] == b"xref"
    for number, entry in enumerate(lines[3:9], 1):  # polo\u017eky xref ukazuj\u00ed p\u0159esn\u011b na "N 0 obj"
        assert data[int(entry[:10]):].startswith(f"{number} 0 obj".encode())


def test_link_pdf_rejects_bad_url(tmp_path):
    for bad in ("", "ftp://x", "https://a b"):
        with pytest.raises(ValueError):
            sr.write_link_pdf(str(tmp_path / "x.pdf"), "t", bad)


def _bundle_with_meta(tmp_path, delivery=None):
    product = tmp_path / "SP-1-B_X"
    (product / "03_Metadata").mkdir(parents=True)
    meta = {"sku": "SP-1-B", "title": "t"}
    if delivery:
        meta["delivery"] = delivery
    (product / "03_Metadata" / "listing_data.json").write_text(json.dumps(meta), encoding="utf-8")
    return str(product)


def test_external_delivery_needs_url_and_creates_pdf(tmp_path):
    missing = _bundle_with_meta(tmp_path)
    assert sr.build_external_delivery(missing, "SP-1-B") is None

    other = tmp_path / "other"
    other.mkdir()
    ok = _bundle_with_meta(other, {"download_url": "https://dropbox.example/s/abc?dl=1"})
    files = sr.build_external_delivery(ok, "SP-1-B")
    assert files and files[0].endswith("SP-1-B_Download_Your_Files.pdf") and os.path.getsize(files[0]) > 200

    broken = tmp_path / "broken"
    broken.mkdir()
    bad = _bundle_with_meta(broken, {"download_url": "not a url"})
    assert sr.build_external_delivery(bad, "SP-1-B") is None


def test_prepare_download_archive_zips_everything(tmp_path):
    import zipfile

    product = _bundle_with_meta(tmp_path)
    art = os.path.join(product, "01_Print_Files_Ready", "Art_A")
    os.makedirs(art)
    for name in ("a-1.jpg", "a-2.jpg"):
        with open(os.path.join(art, name), "wb") as f:
            f.write(b"jpg")
    zip_path = sr.prepare_download_archive(product)
    with zipfile.ZipFile(zip_path) as zf:
        assert sorted(zf.namelist()) == [os.path.join("Art_A", "a-1.jpg"), os.path.join("Art_A", "a-2.jpg")] or \
            sorted(zf.namelist()) == ["Art_A/a-1.jpg", "Art_A/a-2.jpg"]


# --- B-7 / B-9: sady mockup\u016f ---

def test_make_mockups_cycles_images_and_reports_failures(tmp_path, monkeypatch):
    seen = []

    def fake_create(art, out_path, category, used=None):
        seen.append(art)
        return not out_path.endswith("02.jpg")

    monkeypatch.setattr(sr, "create_mockup", fake_create)
    done, failed = sr.make_mockups(["a", "b"], [("01", "c"), ("02", "c"), ("03", "c")], str(tmp_path))
    assert (done, failed) == (2, ["02"])
    assert seen == ["a", "b", "a"]  # ka\u017ed\u00fd mockup dal\u0161\u00ed obraz, ne v\u017edy ten sam\u00fd


def test_make_mockups_first_is_overview_with_fallback(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(sr, "create_bundle_overview", lambda images, path, caption: calls.append(caption) or False)
    monkeypatch.setattr(sr, "create_mockup", lambda art, out, cat, used=None: True)
    done, failed = sr.make_mockups(["a", "b"], [("01", "c"), ("02", "c")], str(tmp_path), overview_caption="Set of 2")
    assert calls == ["Set of 2"] and (done, failed) == (2, [])  # kol\u00e1\u017e selhala -> b\u011b\u017en\u00fd mockup


def test_bundle_overview_is_created(tmp_path):
    from PIL import Image

    out = tmp_path / "overview.jpg"
    images = [Image.new("RGB", (30, 40), color) for color in ("red", "green", "blue", "white", "black")]
    assert sr.create_bundle_overview(images, str(out), "Set of 5") is True
    with Image.open(out) as img:
        assert img.size == (3000, 2250)


# --- B-8 / sestaven\u00ed bundlu ---

def test_build_bundle_names_art_continuously_and_flags_incomplete(tmp_path, monkeypatch):
    from PIL import Image

    _redirect_dirs(monkeypatch, tmp_path)
    count = {"n": 0}

    def fake_image(prompt):
        count["n"] += 1
        return None if count["n"] == 2 else Image.new("RGB", (30, 40), "red")

    def fake_print(img, folder, name):
        with open(os.path.join(folder, f"{name}-x.jpg"), "wb") as f:
            f.write(b"j")

    monkeypatch.setattr(sr, "generate_image", fake_image)
    monkeypatch.setattr(sr, "process_high_quality_print", fake_print)
    monkeypatch.setattr(sr, "make_mockups", lambda images, names, d, overview_caption=None: (7, ["02_Bundle_Overview"]))

    path = sr.build_bundle(None, {"bundle_theme": "M\u011bln\u00edk Test"}, ["a", "b", "c"], progress=(0, 100))
    assert "Melnik" in os.path.basename(path)
    assert sorted(os.listdir(os.path.join(path, "00_Masters"))) == ["Art_A.png", "Art_B.png"]  # bez mezery po vynechan\u00e9m obrazu
    meta = json.loads(open(os.path.join(path, "03_Metadata", "listing_data.json"), encoding="utf-8").read())
    assert meta["incomplete"] is True and meta["images_generated"] == 2 and meta["images_planned"] == 3
    assert meta["pricing"]["currency"] == "EUR"
    assert any("Nevznikly mockupy" in w for w in meta["warnings"])
    assert "Set of 2" in meta["title"]


def test_build_bundle_without_images_leaves_no_folder(tmp_path, monkeypatch):
    _redirect_dirs(monkeypatch, tmp_path)
    monkeypatch.setattr(sr, "generate_image", lambda prompt: None)
    assert sr.build_bundle(None, {"bundle_theme": "X"}, ["a", "b"]) is None
    assert not os.path.isdir(sr.BUNDLES_DIR) or os.listdir(sr.BUNDLES_DIR) == []


# --- S-5 / S-6: SOLO ---

@pytest.fixture
def solo(tmp_path, monkeypatch):
    from PIL import Image

    queue = _redirect_dirs(monkeypatch, tmp_path)
    Image.new("RGB", (1600, 2000), "blue").save(queue / "Melnik.png")
    monkeypatch.setattr(sr, "make_mockups", lambda *a, **k: (8, []))
    return queue


def test_solo_uses_topic_for_seo_and_archives_source(solo, tmp_path, monkeypatch):
    sr.save_topics({"Melnik.png": "castle, river"})
    prompts = []
    monkeypatch.setattr(sr, "GROQ_API_KEY", "x")
    monkeypatch.setattr(sr, "make_groq_client", lambda: object())
    monkeypatch.setattr(sr, "groq_complete", lambda client, prompt: prompts.append(prompt) or SEO_SAMPLE)
    monkeypatch.setattr(sr, "process_high_quality_print", lambda *a, **k: None)

    assert sr.run_solo_mode(interactive=False) == {"ok": 1, "failed": 0}
    assert "castle, river" in prompts[0] and "Melnik" in prompts[0]

    product = next((tmp_path / "w" / "Singles").iterdir())
    meta = json.loads((product / "03_Metadata" / "listing_data.json").read_text(encoding="utf-8"))
    assert meta["title"].startswith("Misty Forest") and len(meta["seo_tags"]) == 13
    assert "Instant digital download" in meta["description_generated"] and meta["seo_generated"] is True
    assert meta["pricing"]["currency"] == "EUR"

    assert not (solo / "Melnik.png").exists()  # S-6: zdroj p\u0159esunut do archivu
    assert list((tmp_path / "arch").rglob("Melnik.png"))
    assert sr.load_topics() == {}  # t\u00e9ma se spot\u0159ebovalo
    assert sr.run_solo_mode(interactive=False) == {"ok": 0, "failed": 0}  # podruh\u00e9 se nic nezpracuje (\u017e\u00e1dn\u00e9 duplicity)
    assert len(list((tmp_path / "w" / "Singles").iterdir())) == 1


def test_solo_without_groq_falls_back_to_generic_seo(solo, tmp_path, monkeypatch):
    monkeypatch.setattr(sr, "GROQ_API_KEY", None)
    monkeypatch.setattr(sr, "process_high_quality_print", lambda *a, **k: None)
    assert sr.run_solo_mode(interactive=False) == {"ok": 1, "failed": 0}
    product = next((tmp_path / "w" / "Singles").iterdir())
    meta = json.loads((product / "03_Metadata" / "listing_data.json").read_text(encoding="utf-8"))
    assert meta["title"].startswith("Melnik Wall Art") and meta["seo_generated"] is False


def test_solo_failure_keeps_source_and_removes_product(solo, tmp_path, monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("tisk selhal")

    monkeypatch.setattr(sr, "GROQ_API_KEY", None)
    monkeypatch.setattr(sr, "process_high_quality_print", boom)
    assert sr.run_solo_mode(interactive=False) == {"ok": 0, "failed": 1}
    assert (solo / "Melnik.png").exists()  # zdroj z\u016fst\u00e1v ve front\u011b pro dal\u0161\u00ed pokus
    assert list((tmp_path / "w" / "Singles").iterdir()) == []


def test_archive_queue_file_flattens_subfolders(tmp_path, monkeypatch):
    queue = _redirect_dirs(monkeypatch, tmp_path)
    (queue / "Batch_1").mkdir()
    (queue / "Batch_1" / "a.png").write_bytes(b"x")
    dst = sr.archive_queue_file("Batch_1/a.png")
    assert os.path.basename(dst) == "Batch_1__a.png" and os.path.isfile(dst)
    assert not (queue / "Batch_1" / "a.png").exists()
    sr._remove_empty_queue_dirs()
    assert not (queue / "Batch_1").exists()


# --- Groq: vyřazený model, zastavení bez promptů ---

class _FakeGroq:
    def __init__(self, working):
        self.working, self.tried = working, []
        self.chat = type("C", (), {"completions": self})()

    def create(self, messages, model):
        self.tried.append(model)
        if model != self.working:
            raise RuntimeError("Error code: 404 - model_not_found")
        msg = type("M", (), {"content": "ok"})()
        return type("R", (), {"choices": [type("Ch", (), {"message": msg})()]})()


def test_groq_complete_falls_back_when_model_is_gone(monkeypatch):
    monkeypatch.setattr(sr, "GROQ_MODEL", "llama-3.3-70b-versatile")
    client = _FakeGroq(working="qwen/qwen3.6-27b")
    assert sr.groq_complete(client, "hi") == "ok"
    assert client.tried == ["llama-3.3-70b-versatile", "openai/gpt-oss-120b", "qwen/qwen3.6-27b"]
    assert sr.GROQ_MODEL == "qwen/qwen3.6-27b"  # fungující model se zapamatuje


def test_groq_complete_raises_when_no_model_exists(monkeypatch):
    monkeypatch.setattr(sr, "GROQ_MODEL", "x/y")
    with pytest.raises(RuntimeError):
        sr.groq_complete(_FakeGroq(working="none"), "hi")


def test_generation_stops_without_prompts_and_spends_no_images(tmp_path, monkeypatch):
    _redirect_dirs(monkeypatch, tmp_path)
    monkeypatch.setattr(sr, "GROQ_API_KEY", "x")
    monkeypatch.setattr(sr, "make_groq_client", lambda: object())
    monkeypatch.setattr(sr, "groq_complete", lambda c, p: (_ for _ in ()).throw(RuntimeError("404")))
    monkeypatch.setattr(sr, "generate_image", lambda p: pytest.fail("nesmí se generovat obraz"))
    assert sr.run_generation_mode(theme="Boho", interactive=False) is False


# --- GUI ---

fastapi = pytest.importorskip("fastapi")
pytest.importorskip("httpx")
pytest.importorskip("multipart")

from fastapi.testclient import TestClient  # noqa: E402

from gui import app as gui_app  # noqa: E402
from gui import core, products, tasks  # noqa: E402
from src import jobs  # noqa: E402


@pytest.fixture
def client(tmp_path, monkeypatch):
    manager = jobs.JobManager(history_path=tmp_path / "history.json", log_dir=tmp_path / "logs")
    monkeypatch.setattr(jobs, "_manager", manager)
    return TestClient(gui_app.app, base_url="http://127.0.0.1:8080")


def test_topics_saved_only_for_queued_files(client, tmp_path, monkeypatch):
    queue_dir = tmp_path / "in" / "_To_Edit"
    queue_dir.mkdir(parents=True)
    (queue_dir / "a.png").write_bytes(b"x")
    monkeypatch.setattr(core, "TO_EDIT_DIR", queue_dir)

    response = client.post("/generate/topics", follow_redirects=False, data={
        "n": "2", "file_0": "a.png", "topic_0": "  misty   forest ", "file_1": "../evil.png", "topic_1": "x"})
    assert response.status_code == 303
    assert json.loads((tmp_path / "in" / "topics.json").read_text(encoding="utf-8")) == {"a.png": "misty forest"}
    assert tasks.queue_files()[0]["topic"] == "misty forest"
    assert "misty forest" in client.get("/generate").text


def test_bundle_download_url_is_validated_and_saved(client, tmp_path, monkeypatch):
    base = tmp_path / "B"
    meta_dir = base / "SP-1-B_X" / "03_Metadata"
    meta_dir.mkdir(parents=True)
    meta_file = meta_dir / "listing_data.json"
    meta_file.write_text(json.dumps({"sku": "SP-1-B", "title": "t", "pricing": {"currency": "USD", "amount": 9.9}}), encoding="utf-8")
    monkeypatch.setitem(products.KINDS, "bundle", ("Bundle", base))

    assert "Doru\u010den\u00ed bundlu" in client.get("/products/bundle/SP-1-B_X").text
    bad = client.post("/products/bundle/SP-1-B_X/delivery-url", data={"download_url": "ftp://x"}, follow_redirects=False)
    assert bad.status_code == 303 and "kind=bad" in bad.headers["location"]
    good = client.post("/products/bundle/SP-1-B_X/delivery-url", data={"download_url": "https://drive.example/f"}, follow_redirects=False)
    assert good.status_code == 303 and "kind=bad" not in good.headers["location"]
    assert json.loads(meta_file.read_text(encoding="utf-8"))["delivery"]["download_url"] == "https://drive.example/f"

    monkeypatch.setattr(tasks, "prepare_archive_zip", lambda product_dir: "ok")
    started = client.post("/products/bundle/SP-1-B_X/archive-zip", follow_redirects=False)
    assert started.status_code == 303 and started.headers["location"].startswith("/jobs/")

    saved = client.post("/products/bundle/SP-1-B_X", follow_redirects=False,
                        data={"title": "t", "description": "", "tags": "a", "price": "9,90"})
    assert saved.status_code == 303
    assert json.loads(meta_file.read_text(encoding="utf-8"))["pricing"] == {"currency": "EUR", "amount": 9.9}  # X-1
