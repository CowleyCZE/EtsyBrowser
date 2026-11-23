"""FastAPI aplikace: lokální GUI pro EtsyBrowser (GUI-0 až GUI-3)."""

from __future__ import annotations

import logging
import os
import re
from pathlib import Path
from typing import Optional
from urllib.parse import quote, urlparse

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, HTMLResponse, PlainTextResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

import sys

from . import core, csvtools, mockups, products, tasks

if str(core.PROJECT_ROOT) not in sys.path:  # i při spuštění přes `uvicorn gui.app:app`
    sys.path.insert(0, str(core.PROJECT_ROOT))
from src import jobs  # noqa: E402

BASE_DIR = Path(__file__).resolve().parent
LOCAL_HOSTS = {"127.0.0.1", "localhost"}

logger = logging.getLogger("gui")
app = FastAPI(title="EtsyBrowser GUI", docs_url=None, redoc_url=None, openapi_url=None)
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

NAV = [
    ("/", "Přehled"),
    ("/generate", "Generovat"),
    ("/products", "Sklad produktů"),
    ("/mockups", "Mockupy"),
    ("/uploader", "Selenium upload"),
    ("/migrate", "Migrace"),
    ("/jobs", "Úlohy"),
    ("/etsy", "Etsy připojení"),
    ("/settings", "Nastavení"),
]


def render(request: Request, name: str, **ctx):
    ctx.setdefault("nav", NAV)
    ctx.setdefault("path", request.url.path)
    ctx["flash"] = request.query_params.get("msg")
    ctx["flash_kind"] = request.query_params.get("kind", "ok")
    status_code = ctx.pop("status_code", 200)
    return templates.TemplateResponse(request, name, ctx, status_code=status_code)


def redirect(path: str, msg: Optional[str] = None, kind: str = "ok") -> RedirectResponse:
    if msg:
        path += ("&" if "?" in path else "?") + f"msg={quote(msg)}&kind={kind}"
    return RedirectResponse(path, status_code=303)


# --- Ochrana lokální aplikace (DNS rebinding / cizí weby posílající POST) ---
@app.middleware("http")
async def local_only(request: Request, call_next):
    host = request.headers.get("host", "").rsplit(":", 1)[0].strip("[]")
    if host not in LOCAL_HOSTS:
        return PlainTextResponse("Přístup povolen jen z localhost.", status_code=403)
    if request.method == "POST":
        origin = request.headers.get("origin")
        if origin and urlparse(origin).hostname not in LOCAL_HOSTS:
            return PlainTextResponse("Neplatný původ požadavku.", status_code=403)
    return await call_next(request)


@app.exception_handler(Exception)
async def friendly_error(request: Request, exc: Exception):
    logger.exception("Neošetřená chyba na %s", request.url.path)
    return HTMLResponse(
        templates.get_template("error.html").render(
            request=request, nav=NAV, path=request.url.path, flash=None, flash_kind="ok",
            message=f"{type(exc).__name__}: {exc}",
        ),
        status_code=500,
    )


# --- GUI-1: Přehled ---
@app.get("/", response_class=HTMLResponse)
def dashboard(request: Request):
    return render(request, "dashboard.html", d=core.dashboard_data(), jobs=jobs.get_manager().list(5))


# --- GUI-2: Připojení k Etsy ---
@app.get("/etsy", response_class=HTMLResponse)
def etsy_page(request: Request):
    return render(request, "etsy.html", token=core.token_status(), oauth=core.oauth_snapshot(),
                  test=None, shop_id=core.read_env(core.ENV_PATH).get("ETSY_SHOP_ID", ""))


@app.post("/etsy/test", response_class=HTMLResponse)
def etsy_test(request: Request):
    result = core.test_etsy_connection()
    return render(request, "etsy.html", token=core.token_status(), oauth=core.oauth_snapshot(),
                  test=result, shop_id=core.read_env(core.ENV_PATH).get("ETSY_SHOP_ID", ""))


@app.post("/etsy/connect")
def etsy_connect():
    if not core.start_oauth():
        return redirect("/etsy", "Autorizace už probíhá.", "warn")
    return redirect("/etsy")


# --- GUI-3: Nastavení ---
@app.get("/settings", response_class=HTMLResponse)
def settings_page(request: Request):
    return render(request, "settings.html", s=core.settings_view(), errors=[])


@app.post("/settings", response_class=HTMLResponse)
async def settings_save(request: Request):
    form = await request.form()
    errors = core.apply_settings(form)
    if errors:
        return render(request, "settings.html", s=core.settings_view(), errors=errors)
    return redirect("/settings", "Nastavení bylo uloženo.")


# --- GUI-5/7: Generování a vstupní fronta ---
GENERATE_KEYS = ["GROQ_API_KEY", "POLLINATIONS_API_KEY"]


def _start_job(name: str, func, args: tuple = ()):
    return jobs.get_manager().submit(name, func, args=args)


@app.get("/generate", response_class=HTMLResponse)
def generate_page(request: Request):
    return render(request, "generate.html", queue=tasks.queue_files(),
                  active=jobs.get_manager().active_count(),
                  missing_bundle=tasks.missing_keys(GENERATE_KEYS), list_info=tasks.prompts_summary())


@app.post("/generate/bundle")
async def generate_bundle(request: Request):
    form = await request.form()
    theme = " ".join(str(form.get("theme", "")).split())[:100]
    missing = tasks.missing_keys(GENERATE_KEYS)
    if missing:
        return redirect("/generate", "Chybí v Nastavení: " + ", ".join(missing), "bad")
    name = "Generování bundlu: " + theme if theme else "Generování bundlu (téma z průzkumu trhu)"
    job = _start_job(name, tasks.generate_bundle, (theme,))
    return redirect(f"/jobs/{job.id}")


@app.post("/generate/upload")
async def generate_upload(request: Request):
    form = await request.form()
    uploads = [f for f in form.getlist("files") if getattr(f, "filename", "")]
    if not uploads:
        return redirect("/generate", "Nevybral(a) jsi žádný soubor.", "warn")
    saved, errors = 0, []
    for upload in uploads[:100]:
        ok, message = tasks.save_upload(upload.filename, upload.file)
        if ok:
            saved += 1
        else:
            errors.append(message)
    text = f"Nahráno {saved} obrázků do fronty."
    if errors:
        text += " Nepodařilo se: " + "; ".join(errors[:5])
    return redirect("/generate", text, "ok" if saved and not errors else "warn")


@app.post("/generate/solo")
async def generate_solo(request: Request):
    form = await request.form()
    tasks.save_topics_from_form(form)  # témata z formuláře fronty se uloží před spuštěním
    if not tasks.queue_files():
        return redirect("/generate", "Fronta je prázdná.", "warn")
    job = _start_job("Zpracování fronty obrázků (SOLO)", tasks.process_queue)
    return redirect(f"/jobs/{job.id}")


@app.post("/generate/topics")
async def generate_topics(request: Request):
    form = await request.form()
    count = tasks.save_topics_from_form(form)
    return redirect("/generate", f"Témata byla uložena ({count}).")


@app.post("/generate/list")
def generate_list():
    missing = tasks.missing_keys(GENERATE_KEYS)
    if missing:
        return redirect("/generate", "Chybí v Nastavení: " + ", ".join(missing), "bad")
    if not tasks.prompts_summary():
        return redirect("/generate", "Soubor data/prompts.json chybí nebo je neplatný.", "bad")
    job = _start_job("Generování ze seznamu (prompts.json)", tasks.generate_from_list)
    return redirect(f"/jobs/{job.id}")


@app.post("/generate/archive")
def generate_archive():
    job = _start_job("Archivace vstupní fronty", tasks.archive_queue)
    return redirect(f"/jobs/{job.id}")


# --- GUI-8: Mockupy ---
def _mockups_back(template: str) -> str:
    return "/mockups" + (f"?template={quote(template)}" if template else "")


@app.get("/mockups", response_class=HTMLResponse)
def mockups_page(request: Request, template: str = ""):
    items = mockups.list_templates()
    selected = next((t for t in items if t["name"] == template), None)
    art, label = mockups.art_path()
    return render(request, "mockups.html", items=items, selected=selected,
                  art_label=label if art else None, art_version=mockups.art_version(),
                  has_uploaded=(mockups.PREVIEW_DIR / mockups.ART_NAME).is_file())


@app.get("/mockups/template/{name}")
def mockup_template_image(request: Request, name: str):
    try:
        return FileResponse(mockups.template_path(name))
    except FileNotFoundError:
        return _not_found(request)


@app.get("/mockups/art/image")
def mockup_art_image(request: Request):
    art, _ = mockups.art_path()
    if art is None:
        return _not_found(request)
    return FileResponse(art)


@app.get("/mockups/render")
def mockup_render(template: str, download: int = 0):
    try:
        data = mockups.render(template, full=bool(download))
    except FileNotFoundError:
        return PlainTextResponse("Šablona nenalezena.", status_code=404)
    except LookupError as exc:
        return PlainTextResponse(str(exc), status_code=409)
    except Exception as exc:  # noqa: BLE001 - obrázek by se jinak jen rozbil bez vysvětlení
        logger.exception("Chyba při vytváření mockupu %s", template)
        return PlainTextResponse(f"Chyba při vytváření mockupu: {exc}", status_code=500)
    headers = {}
    if download:
        stem = re.sub(r"[^A-Za-z0-9._-]", "_", Path(template).stem)
        headers["Content-Disposition"] = f'attachment; filename="TEST_MOCKUP_{stem}.jpg"'
    return Response(data, media_type="image/jpeg", headers=headers)


@app.post("/mockups/art")
async def mockup_art_upload(request: Request):
    form = await request.form()
    back = _mockups_back(str(form.get("template", "")))
    upload = form.get("file")
    if not getattr(upload, "filename", ""):
        return redirect(back, "Nevybral(a) jsi žádný soubor.", "warn")
    ok, message = mockups.save_art(upload.filename, upload.file)
    if not ok:
        return redirect(back, message, "bad")
    return redirect(back, f"Obrázek „{message}“ je připraven pro náhledy.")


@app.post("/mockups/art/clear")
async def mockup_art_clear(request: Request):
    form = await request.form()
    mockups.clear_art()
    return redirect(_mockups_back(str(form.get("template", ""))), "Nahraný obrázek byl odebrán.")


# --- GUI-9: Editor šablon ---
def _editor_page(request: Request, name: str, errors=None, mode=None, points=None, category=None, status_code=200):
    try:
        width, height = mockups.template_size(name)
    except FileNotFoundError:
        return _not_found(request)
    saved_mode, saved_points = mockups.editor_points(name)
    entry = mockups._config_index().get(name)
    return templates.TemplateResponse(
        request, "mockup_editor.html",
        {"nav": NAV, "path": request.url.path, "flash": request.query_params.get("msg"),
         "flash_kind": request.query_params.get("kind", "ok"), "errors": errors or [],
         "name": name, "width": width, "height": height,
         "mode": mode or saved_mode, "points": saved_points if points is None else points,
         "cats": mockups.categories(), "category": category or (entry[0] if entry else ""),
         "configured": entry is not None},
        status_code=status_code,
    )


@app.get("/mockups/editor", response_class=HTMLResponse)
def mockup_editor(request: Request, template: str):
    return _editor_page(request, template)


@app.post("/mockups/editor/save", response_class=HTMLResponse)
async def mockup_editor_save(request: Request):
    form = await request.form()
    name = str(form.get("template", ""))
    category = str(form.get("category_select", ""))
    if category == "__new__":
        category = str(form.get("category_new", ""))
    mode, raw = str(form.get("mode", "")), str(form.get("points", "[]"))
    errors = mockups.save_template_config(name, category, mode, raw)
    if errors:
        parsed = mockups._parse_points(raw)
        return _editor_page(request, name, errors, mode if mode in ("perspective", "rect") else None,
                            parsed, " ".join(category.split()), status_code=400)
    return redirect(_mockups_back(name), "Rám šablony byl uložen. Níže vidíš náhled s novým nastavením.")


@app.post("/mockups/editor/remove")
async def mockup_editor_remove(request: Request):
    form = await request.form()
    name = str(form.get("template", ""))
    errors = mockups.remove_template_config(name)
    if errors:
        return redirect(_mockups_back(name), errors[0], "bad")
    return redirect(_mockups_back(name), "Konfigurace šablony byla smazána.")


# --- GUI-11: Selenium upload a products.csv ---
UPLOADER_KEYS = ["ETSY_EMAIL", "ETSY_PASSWORD"]


def _uploader_page(request: Request, columns, rows, errors=None, status_code=200):
    env = core.read_env(core.ENV_PATH)
    cfg = core.read_config()
    creds_missing = [k for k in UPLOADER_KEYS
                     if not (env.get(k) or os.environ.get(k) or cfg.get(k.replace("ETSY_", "").lower()))]
    return render(
        request, "uploader.html", columns=columns, rows=rows + [{}], saved_count=len(rows), errors=errors or [],
        fields=csvtools.COLUMNS, extras=csvtools.extra_columns(columns), warnings=csvtools.image_warnings(rows),
        creds_missing=creds_missing, selectors=csvtools.selectors_status(),
        headless_default=bool(cfg.get("headless", False)), status_code=status_code,
    )


@app.get("/uploader", response_class=HTMLResponse)
def uploader_page(request: Request):
    columns, rows = csvtools.read_rows()
    return _uploader_page(request, columns, rows)


@app.post("/uploader/csv", response_class=HTMLResponse)
async def uploader_csv_save(request: Request):
    form = await request.form()
    columns, _ = csvtools.read_rows()
    rows = csvtools.form_to_rows(form, columns)
    errors = csvtools.validate_rows(rows)
    if errors:
        return _uploader_page(request, columns, rows, errors, status_code=400)
    csvtools.write_rows(columns, rows)
    return redirect("/uploader", f"Soubor products.csv byl uložen ({len(rows)} produktů).")


@app.post("/uploader/run")
async def uploader_run(request: Request):
    form = await request.form()
    if form.get("confirm") != "on":
        return redirect("/uploader", "Spuštění je nutné potvrdit zaškrtnutím políčka.", "warn")
    _, rows = csvtools.read_rows()
    if not rows:
        return redirect("/uploader", "products.csv neobsahuje žádné produkty.", "warn")
    errors = csvtools.validate_rows(rows)
    if errors:
        return redirect("/uploader", "Uložený products.csv má chyby: " + " ".join(errors[:3]), "bad")
    cfg = core.read_config()
    missing = [k for k in UPLOADER_KEYS
               if k in tasks.missing_keys(UPLOADER_KEYS) and not cfg.get(k.replace("ETSY_", "").lower())]
    if missing:
        return redirect("/uploader", "Chybí v Nastavení: " + ", ".join(missing), "bad")
    headless = form.get("mode") == "headless"
    job = _start_job(f"Selenium upload na Etsy ({len(rows)} produktů, {'bez okna' if headless else 'viditelné okno'})",
                     tasks.run_uploader, (headless,))
    return redirect(f"/jobs/{job.id}")


# --- GUI-12: Migrace starých produktů ---
@app.get("/migrate", response_class=HTMLResponse)
def migrate_page(request: Request, source: str = ""):
    from automation import migrate_products

    source = source.strip() or migrate_products.default_source()
    exists = os.path.isdir(source)
    plan = migrate_products.plan_migration(source) if exists else []
    return render(request, "migrate.html", source=source, exists=exists, plan=plan,
                  todo=sum(1 for p in plan if not p["already_migrated"]))


@app.post("/migrate/run")
async def migrate_run(request: Request):
    form = await request.form()
    source = str(form.get("source", "")).strip()
    back = "/migrate?source=" + quote(source)
    if form.get("confirm") != "on":
        return redirect(back, "Spuštění je nutné potvrdit zaškrtnutím políčka.", "warn")
    if not os.path.isdir(source):
        return redirect(back, "Zdrojová složka neexistuje.", "bad")
    job = _start_job(f"Migrace starých produktů z {source}", tasks.run_migration, (source,))
    return redirect(f"/jobs/{job.id}")


# --- GUI-13: Úlohy ---
@app.get("/jobs", response_class=HTMLResponse)
def jobs_page(request: Request):
    items = jobs.get_manager().list()
    return render(request, "jobs.html", items=items, refresh=any(i["active"] for i in items))


@app.get("/jobs/{job_id}", response_class=HTMLResponse)
def job_page(request: Request, job_id: str):
    job = jobs.get_manager().get(job_id)
    if job is None:
        return _not_found(request)
    return render(request, "job.html", j=job.to_dict(with_log=True))


@app.post("/jobs/{job_id}/cancel")
def job_cancel(job_id: str):
    if jobs.get_manager().cancel(job_id):
        return redirect(f"/jobs/{job_id}", "Zrušení požadováno, úloha se zastaví při nejbližším kroku.", "warn")
    return redirect(f"/jobs/{job_id}", "Úloha už skončila.", "warn")


@app.get("/jobs/{job_id}/log")
def job_log(request: Request, job_id: str):
    job = jobs.get_manager().get(job_id)
    if job is None:
        return _not_found(request)
    if job.log_path.is_file():
        return FileResponse(job.log_path, media_type="text/plain; charset=utf-8", filename=f"{job.id}.log")
    return PlainTextResponse("\n".join(job.to_dict(with_log=True)["log"]))


# --- GUI-10: Publikace na Etsy (z detailu produktu) ---
@app.post("/products/{kind}/{folder}/delivery-url")
async def product_delivery_url(request: Request, kind: str, folder: str):
    form = await request.form()
    back = f"/products/{quote(kind)}/{quote(folder)}"
    try:
        errors = products.save_download_url(kind, folder, str(form.get("download_url", "")))
    except FileNotFoundError:
        return _not_found(request)
    if errors:
        return redirect(back, errors[0], "bad")
    return redirect(back, "Odkaz ke stažení byl uložen.")


@app.post("/products/{kind}/{folder}/archive-zip")
def product_archive_zip(request: Request, kind: str, folder: str):
    try:
        path = products.product_dir(kind, folder)
    except FileNotFoundError:
        return _not_found(request)
    job = _start_job(f"Příprava ZIPu ke stažení: {folder}", tasks.prepare_archive_zip, (str(path),))
    return redirect(f"/jobs/{job.id}")


@app.post("/products/{kind}/{folder}/publish")
def product_publish(request: Request, kind: str, folder: str):
    try:
        path = products.product_dir(kind, folder)
    except FileNotFoundError:
        return _not_found(request)
    job = _start_job(f"Nahrání draftu na Etsy: {folder}", tasks.publish_draft, (str(path),))
    return redirect(f"/jobs/{job.id}")


@app.post("/products/{kind}/{folder}/activate")
async def product_activate(request: Request, kind: str, folder: str):
    try:
        path = products.product_dir(kind, folder)
    except FileNotFoundError:
        return _not_found(request)
    form = await request.form()
    if form.get("confirm") != "on":
        return redirect(f"/products/{quote(kind)}/{quote(folder)}", "Zveřejnění je nutné potvrdit zaškrtnutím políčka.", "warn")
    job = _start_job(f"Zveřejnění listingu na Etsy: {folder}", tasks.activate_listing, (str(path),))
    return redirect(f"/jobs/{job.id}")


# --- GUI-4: Sklad produktů ---
def _not_found(request: Request):
    return HTMLResponse(
        templates.get_template("error.html").render(
            request=request, nav=NAV, path=request.url.path, flash=None, flash_kind="ok",
            message="Produkt nebo soubor nebyl nalezen.",
        ),
        status_code=404,
    )


@app.get("/products", response_class=HTMLResponse)
def products_page(request: Request, q: str = "", status: str = ""):
    return render(request, "products.html", items=products.list_products(q, status), q=q, status=status)


@app.get("/products/{kind}/{folder}", response_class=HTMLResponse)
def product_page(request: Request, kind: str, folder: str):
    try:
        p = products.get_product(kind, folder)
    except FileNotFoundError:
        return _not_found(request)
    return render(request, "product.html", p=p, errors=[], form=None)


@app.post("/products/{kind}/{folder}", response_class=HTMLResponse)
async def product_save(request: Request, kind: str, folder: str):
    form = await request.form()
    try:
        errors = products.save_product(kind, folder, form)
        p = products.get_product(kind, folder)
    except FileNotFoundError:
        return _not_found(request)
    if errors:
        return render(request, "product.html", p=p, errors=errors, form=dict(form))
    return redirect(f"/products/{quote(kind)}/{quote(folder)}", "Změny byly uloženy.")


@app.get("/media/{kind}/{folder}/{filename}")
def product_media(request: Request, kind: str, folder: str, filename: str):
    try:
        return FileResponse(products.media_path(kind, folder, filename))
    except FileNotFoundError:
        return _not_found(request)
