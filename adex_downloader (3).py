"""
ADEX ComexTrade - Descarga automatizada de Rankings de Empresas
===============================================================
12 archivos XLSX: 6 filtros × 2 criterios (X luego M por cada filtro)

Orden: General(X→M) → China(X→M) → Reino Unido(X→M) → ...

Accordions EXCLUSIVOS — abrir uno cierra los demás.
Cada función abre su propio accordion justo antes de usarlo.

Uso:
    set ADEX_EMAIL=correo && set ADEX_PASS=clave && python adex_downloader.py
    $env:ADEX_EMAIL="correo"; $env:ADEX_PASS="clave"; python adex_downloader.py

Dependencias:
    pip install selenium python-dateutil
"""

import os
import time
import traceback
from datetime import date
from pathlib import Path

from dateutil.relativedelta import relativedelta
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException


# ===========================================================================
# CONFIGURACIÓN
# ===========================================================================

BASE_URL = "https://www.adexdatatrade.com/"

# Por cada filtro se descarga Exportaciones luego Importaciones
FILTROS_PAIS = [
    ("General",       None),
    ("China",         "CN"),          # value del <option>
    ("Reino_Unido",   "GB"),
    ("Europa",        "6"),           # continente value
    ("Union_Europea", "91"),          # zona económica value
    ("Japon",         "JP"),
]

CRITERIOS = [
    ("Exportaciones", "X"),
    ("Importaciones", "M"),
]

MESES_ES = {
    1:"Enero",2:"Febrero",3:"Marzo",4:"Abril",5:"Mayo",6:"Junio",
    7:"Julio",8:"Agosto",9:"Septiembre",10:"Octubre",11:"Noviembre",12:"Diciembre",
}

ACCORDION = {
    "filtros_principales":  "#default_collapseOne",
    "filtros_secundarios":  "#default_collapseTwo",
    "opciones_adicionales": "#default_collapseThree",
}

# checkbox_id, select_id (nativo), opcion_value
FILTRO_CONFIG = {
    "CN": ("PaisSwitch",          "lb_Mercado",       "CN"),
    "GB": ("PaisSwitch",          "lb_Mercado",       "GB"),
    "JP": ("PaisSwitch",          "lb_Mercado",       "JP"),
    "6":  ("ContinenteSwitch",    "lb_Continente",    "6"),
    "91": ("ZonaEconomicaSwitch", "ddl_ZonaEconomica","91"),
}

ESPERA_RESULTADOS = 90  # segundos para todos los filtros

FINAL_EXTS       = {".xlsx", ".xls", ".csv"}
TEMP_EXTS        = {".crdownload", ".tmp", ".part"}
DOWNLOAD_TIMEOUT = 180


# ===========================================================================
# T-2
# ===========================================================================

def get_anio_y_meses():
    """
    T-2: los datos disponibles llegan hasta hace 2 meses.
    Ejemplos:
      Hoy 2026-03 → último dato = 2026-01 → año=2026, meses=[1]
      Hoy 2026-02 → último dato = 2025-12 → año=2025, meses=[1..12]
      Hoy 2026-01 → último dato = 2025-11 → año=2025, meses=[1..11]
      Hoy 2025-03 → último dato = 2025-01 → año=2025, meses=[1]
    """
    ultimo = date.today() - relativedelta(months=2)
    anio   = str(ultimo.year)
    meses  = list(range(1, ultimo.month + 1))  # lista de ints 1-N
    return anio, meses


# ===========================================================================
# UTILS
# ===========================================================================

def W(driver, t=12):
    return WebDriverWait(driver, t, poll_frequency=0.25)

def log(msg):
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)

def js_click(driver, el):
    driver.execute_script("arguments[0].scrollIntoView({block:'center'});", el)
    time.sleep(0.08)
    driver.execute_script("arguments[0].click();", el)

def js_select_by_value(driver, select_id, value):
    """Selecciona una opción en un <select> nativo usando JS directamente."""
    driver.execute_script(f"""
        var sel = document.getElementById('{select_id}');
        sel.value = '{value}';
        sel.dispatchEvent(new Event('change', {{bubbles:true}}));
        // También disparar para bootstrap-select
        $(sel).selectpicker('val', '{value}');
        $(sel).selectpicker('refresh');
    """)
    time.sleep(0.4)

def snapshot_dir(d):
    return {p.name for p in Path(d).glob("*") if p.is_file()}

def wait_download(download_dir, before, timeout=DOWNLOAD_TIMEOUT):
    d = Path(download_dir)
    end = time.time() + timeout
    while time.time() < end:
        current = {p.name for p in d.glob("*") if p.is_file()}
        new_files = [d/f for f in (current - before)]
        if any(p.suffix.lower() in TEMP_EXTS for p in new_files):
            time.sleep(0.4); continue
        finals = [p for p in new_files if p.suffix.lower() in FINAL_EXTS]
        if finals:
            return max(finals, key=lambda p: p.stat().st_mtime)
        time.sleep(0.4)
    raise TimeoutError("Archivo no apareció.")

def wait_idle(driver, t=10):
    try:
        WebDriverWait(driver, t, poll_frequency=0.3).until(
            lambda d: d.execute_script("return document.readyState") == "complete"
        )
    except TimeoutException:
        pass
    time.sleep(0.3)


# ===========================================================================
# DRIVER
# ===========================================================================

def make_driver(download_dir, headless=False):
    Path(download_dir).mkdir(parents=True, exist_ok=True)
    opts = Options()
    if headless:
        opts.add_argument("--headless=new")

    opts.add_argument("--start-maximized")
    opts.add_argument("--window-size=1920,1080")
    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-dev-shm-usage")
    opts.add_argument("--disable-popup-blocking")
    opts.add_experimental_option("prefs", {
        "download.default_directory":           str(Path(download_dir).resolve()),
        "download.prompt_for_download":         False,
        "download.directory_upgrade":           True,
        "safebrowsing.enabled":                 True,
        "plugins.always_open_pdf_externally":   True,
    })

    # Busca chromedriver.exe en la misma carpeta que este script
    CHROMEDRIVER_PATH = Path(__file__).parent / "chromedriver.exe"

    if CHROMEDRIVER_PATH.exists():
        from selenium.webdriver.chrome.service import Service
        return webdriver.Chrome(service=Service(str(CHROMEDRIVER_PATH)), options=opts)
    else:
        return webdriver.Chrome(options=opts)


# ===========================================================================
# LOGIN
# ===========================================================================

def login(driver, email, password, timeout=20):
    log("── LOGIN ──")
    driver.get(BASE_URL)
    w = W(driver, timeout)
    js_click(driver, w.until(EC.element_to_be_clickable(
        (By.XPATH, '//a[contains(@class,"btn-success") and normalize-space()="Login"]')
    )))
    w.until(EC.visibility_of_element_located((By.ID, "txt_Email"))).send_keys(email)
    w.until(EC.visibility_of_element_located((By.ID, "txt_Clave"))).send_keys(password)
    js_click(driver, w.until(EC.element_to_be_clickable((By.ID, "btn_Login"))))
    w.until(lambda d: d.current_url != BASE_URL)
    log("✓ Login OK")


# ===========================================================================
# NAVEGACIÓN
# ===========================================================================

def go_to_estadisticas(driver, timeout=20):
    log("Cargando Estadísticas...")
    driver.get(BASE_URL.rstrip("/") + "/Members/Estadisticas.aspx")
    W(driver, timeout).until(EC.url_contains("/Members/Estadisticas.aspx"))
    W(driver, timeout).until(EC.presence_of_element_located(
        (By.CSS_SELECTOR, 'input[name="rbl_Criterio"][value="X"]')
    ))
    wait_idle(driver)
    log("✓ Página cargada")


# ===========================================================================
# ACCORDION
# ===========================================================================

def open_accordion(driver, target_id, timeout=8):
    """Abre el accordion. Como son exclusivos, abrir uno cierra los demás."""
    css = f'div.accordion__header[data-target="{target_id}"]'
    header = W(driver, timeout).until(EC.presence_of_element_located((By.CSS_SELECTOR, css)))
    if header.get_attribute("aria-expanded") != "true":
        js_click(driver, header)
        try:
            W(driver, 5).until(
                lambda d: d.find_element(By.CSS_SELECTOR, css).get_attribute("aria-expanded") == "true"
            )
        except TimeoutException:
            pass
        time.sleep(0.3)


# ===========================================================================
# BOOTSTRAP-SELECT — abre dropdown y hace click en opción por texto visible
# Las opciones renderizan como: <a ...><span class="text">TEXTO</span></a>
# ===========================================================================

def bs_open(driver, data_id, timeout=8):
    btn = W(driver, timeout).until(EC.presence_of_element_located(
        (By.CSS_SELECTOR, f'button.dropdown-toggle[data-id="{data_id}"]')
    ))
    if btn.get_attribute("aria-expanded") != "true":
        js_click(driver, btn)
        time.sleep(0.35)
    return btn

def bs_close(driver, data_id):
    try:
        btn = driver.find_element(By.CSS_SELECTOR, f'button.dropdown-toggle[data-id="{data_id}"]')
        if btn.get_attribute("aria-expanded") == "true":
            js_click(driver, btn)
            time.sleep(0.2)
    except NoSuchElementException:
        pass

def bs_click_text(driver, data_id, text, timeout=10):
    """Click en opción cuyo <span class='text'> sea exactamente 'text'."""
    xpath = (
        f'//button[@data-id="{data_id}"]'
        f'/following-sibling::div[contains(@class,"dropdown-menu")]'
        f'//span[@class="text" and normalize-space()="{text}"]'
    )
    opt = W(driver, timeout).until(EC.element_to_be_clickable((By.XPATH, xpath)))
    js_click(driver, opt)
    time.sleep(0.25)

def bs_select_by_value(driver, data_id, value, timeout=10):
    """
    Selecciona opción por value del <option> subyacente usando JS.
    Más robusto que buscar por texto (evita problemas de tildes/mayúsculas).
    """
    # Encontrar el select nativo que tiene este data-id en su botón
    select_id = driver.execute_script(
        f"var btn = document.querySelector('button[data-id=\"{data_id}\"]');"
        f"return btn ? btn.getAttribute('data-id') : null;"
    )
    if not select_id:
        raise RuntimeError(f"No se encontró botón con data-id='{data_id}'")

    # Usar el select nativo directamente
    driver.execute_script(f"""
        var sel = document.getElementById('{data_id}');
        if (!sel) sel = document.querySelector('select[name="{data_id}"]');
        if (sel) {{
            // Desmarcar todo primero (para multi-select)
            for (var i=0; i<sel.options.length; i++) sel.options[i].selected = false;
            // Marcar el value pedido
            for (var i=0; i<sel.options.length; i++) {{
                if (sel.options[i].value === '{value}') {{
                    sel.options[i].selected = true;
                    break;
                }}
            }}
            sel.dispatchEvent(new Event('change', {{bubbles:true}}));
            // Actualizar bootstrap-select visual
            if (typeof $ !== 'undefined') {{
                $(sel).selectpicker('refresh');
            }}
        }}
    """)
    time.sleep(0.4)
    log(f"    ✓ Seleccionado value='{value}' en select '{data_id}'")


# ===========================================================================
# FILTROS PRINCIPALES (#default_collapseOne)
# ===========================================================================

def set_criterio(driver, criterio):
    """Abre filtros principales y cambia el radio criterio."""
    open_accordion(driver, ACCORDION["filtros_principales"])
    el = W(driver, 10).until(EC.presence_of_element_located(
        (By.CSS_SELECTOR, f'input[name="rbl_Criterio"][value="{criterio}"]')
    ))
    js_click(driver, el)
    time.sleep(0.5)
    log(f"  ✓ Criterio: {'Exportaciones' if criterio=='X' else 'Importaciones'}")

def set_tipo_consulta(driver):
    """
    Selecciona 'Ranking de Empresas' (value='E3') en ddl_Consulta.
    Usa JS sobre el select nativo + refresca bootstrap-select.
    """
    open_accordion(driver, ACCORDION["filtros_principales"])
    driver.execute_script("""
        var sel = document.getElementById('ddl_Consulta');
        sel.value = 'E3';
        sel.dispatchEvent(new Event('change', {bubbles:true}));
        if (typeof $ !== 'undefined') $(sel).selectpicker('refresh');
    """)
    time.sleep(0.5)
    log("  ✓ Tipo consulta: Ranking de Empresas")

def set_anio(driver, anio):
    """Selecciona el año usando JS sobre el select nativo lb_Aa."""
    open_accordion(driver, ACCORDION["filtros_principales"])
    driver.execute_script(f"""
        var sel = document.getElementById('lb_Aa');
        for (var i=0; i<sel.options.length; i++) sel.options[i].selected = false;
        for (var i=0; i<sel.options.length; i++) {{
            if (sel.options[i].value === '{anio}') {{
                sel.options[i].selected = true; break;
            }}
        }}
        sel.dispatchEvent(new Event('change', {{bubbles:true}}));
        if (typeof $ !== 'undefined') $(sel).selectpicker('refresh');
    """)
    time.sleep(0.4)
    log(f"  ✓ Año: {anio}")

def set_meses(driver, mes_numeros):
    """
    Selecciona los meses indicados (lista de int 1-12) usando JS sobre lb_Mm.
    Si son los 12 meses usa el checkbox 'Todos los meses' (más rápido).
    Si son menos de 12 (lógica T-2) selecciona solo los que corresponden.
    """
    open_accordion(driver, ACCORDION["filtros_principales"])

    if len(mes_numeros) == 12:
        # Usar checkbox "Todos los meses" de un click
        cb = W(driver, 8).until(EC.presence_of_element_located((By.ID, "rbl_mesesdoce")))
        if not cb.is_selected():
            js_click(driver, cb)
            time.sleep(0.5)
        log(f"  ✓ Meses: todos (12)")
    else:
        # Desmarcar todos primero, luego marcar solo los pedidos
        driver.execute_script("""
            var cb = document.getElementById('rbl_mesesdoce');
            if (cb && cb.checked) { cb.checked = false; }
        """)
        valores_str = "[" + ",".join(str(m) for m in mes_numeros) + "]"
        driver.execute_script(f"""
            var valores = {valores_str};
            var sel = document.getElementById('lb_Mm');
            for (var i=0; i<sel.options.length; i++) {{
                var v = parseInt(sel.options[i].value);
                sel.options[i].selected = valores.indexOf(v) !== -1;
            }}
            sel.dispatchEvent(new Event('change', {{bubbles:true}}));
            if (typeof $ !== 'undefined') $(sel).selectpicker('refresh');
        """)
        time.sleep(0.4)
        names = [MESES_ES[m] for m in mes_numeros]
        log(f"  ✓ Meses: {', '.join(names)}")


# ===========================================================================
# OPCIONES ADICIONALES (#default_collapseThree) — solo una vez al inicio
# ===========================================================================

def set_mensual(driver):
    open_accordion(driver, ACCORDION["opciones_adicionales"])
    radio = W(driver, 8).until(EC.presence_of_element_located(
        (By.CSS_SELECTOR, 'input[name="detalle"][value="0"]')
    ))
    if not radio.is_selected():
        js_click(driver, radio)
        time.sleep(0.2)
    log("  ✓ Detalle: Mensual")


# ===========================================================================
# FILTROS SECUNDARIOS (#default_collapseTwo)
# Los dropdowns de país/continente/zona tienen clase "option-switch-opt d-none"
# y se muestran solo al activar el switch correspondiente.
# ===========================================================================

def _activate_switch(driver, checkbox_id):
    open_accordion(driver, ACCORDION["filtros_secundarios"])
    cb = W(driver, 8).until(EC.presence_of_element_located((By.ID, checkbox_id)))
    if not cb.is_selected():
        lbl = driver.find_element(By.CSS_SELECTOR,
            f'label.custom-control-label[for="{checkbox_id}"]')
        js_click(driver, lbl)
        # Esperar que el div option-switch-opt deje de tener d-none
        time.sleep(0.8)
        log(f"    ✓ Switch '{checkbox_id}' activado")
    else:
        log(f"    ✓ Switch '{checkbox_id}' ya activo")

def _deactivate_switch(driver, checkbox_id):
    open_accordion(driver, ACCORDION["filtros_secundarios"])
    try:
        cb = driver.find_element(By.ID, checkbox_id)
        if cb.is_selected():
            lbl = driver.find_element(By.CSS_SELECTOR,
                f'label.custom-control-label[for="{checkbox_id}"]')
            js_click(driver, lbl)
            time.sleep(0.4)
            log(f"    ✓ Switch '{checkbox_id}' desactivado")
    except NoSuchElementException:
        pass

def set_filtro_secundario(driver, filtro_val):
    """
    Activa el switch y selecciona el valor en el select nativo via JS.
    filtro_val es el value del <option> (ej: "CN", "6", "91")
    """
    if filtro_val not in FILTRO_CONFIG:
        log(f"    ⚠ filtro_val '{filtro_val}' no en FILTRO_CONFIG")
        return
    checkbox_id, select_id, option_value = FILTRO_CONFIG[filtro_val]

    # 1. Activar switch (abre accordion filtros_secundarios)
    _activate_switch(driver, checkbox_id)

    # 2. Seleccionar valor en el select nativo via JS
    driver.execute_script(f"""
        var sel = document.getElementById('{select_id}');
        for (var i=0; i<sel.options.length; i++) sel.options[i].selected = false;
        for (var i=0; i<sel.options.length; i++) {{
            if (sel.options[i].value === '{option_value}') {{
                sel.options[i].selected = true; break;
            }}
        }}
        sel.dispatchEvent(new Event('change', {{bubbles:true}}));
        if (typeof $ !== 'undefined') $(sel).selectpicker('refresh');
    """)
    time.sleep(0.4)
    log(f"    ✓ Filtro secundario value='{option_value}' en '{select_id}'")

def limpiar_filtros_secundarios(driver):
    """Desactiva los 3 switches para consulta General."""
    open_accordion(driver, ACCORDION["filtros_secundarios"])
    for cb_id in ["ContinenteSwitch", "ZonaEconomicaSwitch", "PaisSwitch"]:
        _deactivate_switch(driver, cb_id)
    log("  ✓ Filtros secundarios limpios (General)")

def desactivar_filtro_anterior(driver, filtro_val_anterior):
    if filtro_val_anterior is None or filtro_val_anterior not in FILTRO_CONFIG:
        return
    cb_id, _, _ = FILTRO_CONFIG[filtro_val_anterior]
    _deactivate_switch(driver, cb_id)


# ===========================================================================
# APLICAR FILTRO
# ===========================================================================

def close_all_accordions(driver):
    """Cierra el accordion que esté abierto para que los resultados sean visibles."""
    for target_id in ACCORDION.values():
        css = f'div.accordion__header[data-target="{target_id}"]'
        try:
            header = driver.find_element(By.CSS_SELECTOR, css)
            if header.get_attribute("aria-expanded") == "true":
                js_click(driver, header)
                time.sleep(0.3)
        except NoSuchElementException:
            pass


def click_aplicar_filtro(driver, espera=60):
    log("  Aplicando Filtro...")
    btn = W(driver, 10).until(EC.presence_of_element_located(
        (By.CSS_SELECTOR, "button.btn-aplicar-filtro")
    ))
    # Ocultar botón exportar anterior para detectar el nuevo
    try:
        driver.execute_script(
            "var e=document.querySelector('a.btn-descargar-excel'); if(e) e.style.display='none';"
        )
    except Exception:
        pass

    # Cerrar todos los accordions ANTES de hacer click para que los resultados queden visibles
    close_all_accordions(driver)

    js_click(driver, btn)
    log(f"  ✓ Click — esperando resultados (hasta {espera}s)...")
    try:
        WebDriverWait(driver, espera, poll_frequency=0.5).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "a.btn-descargar-excel"))
        )
        log("  ✓ Resultados listos")
    except TimeoutException:
        log("  ⚠ Timeout esperando resultados, continuando...")
    wait_idle(driver, 8)


# ===========================================================================
# EXPORTAR
# ===========================================================================

def exportar_excel(driver, download_dir):
    log("  Exportando a Excel...")
    before = snapshot_dir(download_dir)
    link = W(driver, 15).until(EC.presence_of_element_located(
        (By.CSS_SELECTOR, "a.btn-descargar-excel")
    ))
    js_click(driver, link)
    time.sleep(1.5)
    # Volver a ventana principal si se abrió pestaña (NO cerrarla)
    if len(driver.window_handles) > 1:
        driver.switch_to.window(driver.window_handles[0])
    log("  ✓ Esperando archivo en disco...")
    return wait_download(download_dir, before)

def rename_file(path, criterio_label, filtro_label, anio):
    safe = f"ADEX_{criterio_label}_{filtro_label}_{anio}{path.suffix}"
    dest = path.parent / safe
    if dest.exists():
        dest = path.parent / f"ADEX_{criterio_label}_{filtro_label}_{anio}_{time.strftime('%H%M%S')}{path.suffix}"

    # Reintentar hasta 10 veces esperando que el proceso suelte el archivo (WinError 32)
    for intento in range(10):
        try:
            path.rename(dest)
            return dest
        except PermissionError:
            log(f"  ⏳ Archivo en uso, esperando... ({intento+1}/10)")
            time.sleep(2)

    # Último intento, si falla deja propagar el error
    path.rename(dest)
    return dest


# ===========================================================================
# FLUJO PRINCIPAL
# ===========================================================================

def run_all(email, password, download_dir, headless=False, anio=None, meses=None):
    """
    Orden: General(X→M) → China(X→M) → Reino Unido(X→M) → ...

    Qué cambia en cada paso:
      X→M mismo filtro : criterio + tipo consulta (año/meses/mensual intactos)
      cambio de filtro  : desactivar switch anterior, activar nuevo (criterio intacto)
    """
    if anio is None or meses is None:
        anio_auto, meses_auto = get_anio_y_meses()
        anio  = anio  or anio_auto
        meses = meses or meses_auto  # lista de ints

    total = len(FILTROS_PAIS) * len(CRITERIOS)
    log("=" * 60)
    log(f"  Año: {anio}  |  Meses: {', '.join(MESES_ES[m] for m in meses)}")
    log(f"  Total: {total} archivos  |  Salida: {download_dir}")
    log("=" * 60)

    driver      = make_driver(download_dir, headless)
    descargados = []
    errores     = []

    def setup_completo(criterio_val):
        """Configura todo desde cero (inicio o recovery)."""
        log("  [Setup completo]")
        set_criterio(driver, criterio_val)          # abre filtros_principales
        set_tipo_consulta(driver)                    # mismo accordion
        set_anio(driver, anio)                       # mismo accordion
        set_meses(driver, meses)                     # mismo accordion
        set_mensual(driver)                          # abre opciones_adicionales
        log("  [Setup completo ✓]")

    def full_recovery(criterio_val, filtro_val):
        log("  ── Recovery ──")
        try:
            while len(driver.window_handles) > 1:
                driver.switch_to.window(driver.window_handles[-1])
                driver.close()
            driver.switch_to.window(driver.window_handles[0])
        except Exception:
            pass
        go_to_estadisticas(driver)
        setup_completo(criterio_val)
        if filtro_val is not None:
            set_filtro_secundario(driver, filtro_val)
        else:
            limpiar_filtros_secundarios(driver)
        log("  ── Recovery completo ──")

    try:
        login(driver, email, password)
        go_to_estadisticas(driver)
        setup_completo(CRITERIOS[0][1])  # Setup inicial con Exportaciones

        criterio_actual   = CRITERIOS[0][1]  # "X"
        filtro_val_actual = None

        idx = 0
        for filtro_label, filtro_val in FILTROS_PAIS:
            for criterio_label, criterio_val in CRITERIOS:
                idx += 1
                tarea = f"{filtro_label} | {criterio_label}"
                log(f"\n{'─'*60}")
                log(f"  [{idx}/{total}] {tarea}")
                log(f"{'─'*60}")
                espera = ESPERA_RESULTADOS

                try:
                    # A. Cambiar criterio si necesario (+ tipo consulta)
                    if criterio_val != criterio_actual:
                        set_criterio(driver, criterio_val)      # abre filtros_principales
                        set_tipo_consulta(driver)               # mismo accordion
                        criterio_actual = criterio_val

                    # B. Cambiar filtro secundario si necesario
                    if filtro_val != filtro_val_actual:
                        desactivar_filtro_anterior(driver, filtro_val_actual)
                        if filtro_val is None:
                            limpiar_filtros_secundarios(driver)
                        else:
                            set_filtro_secundario(driver, filtro_val)
                        filtro_val_actual = filtro_val

                    # C. Aplicar + Exportar
                    click_aplicar_filtro(driver, ESPERA_RESULTADOS)
                    raw   = exportar_excel(driver, download_dir)
                    final = rename_file(raw, criterio_label, filtro_label, anio)
                    log(f"✅ {final.name}")
                    descargados.append(final)

                except Exception as e:
                    log(f"❌ ERROR: {e}")
                    log(traceback.format_exc())
                    errores.append((tarea, str(e)))
                    try:
                        full_recovery(criterio_val, filtro_val)
                        criterio_actual   = criterio_val
                        filtro_val_actual = filtro_val
                    except Exception as e2:
                        log(f"  ⚠ Recovery fallido: {e2}")
                        criterio_actual   = None
                        filtro_val_actual = None

    finally:
        driver.quit()

    log("\n" + "=" * 60)
    log(f"  RESUMEN: {len(descargados)}/{total} exitosas")
    for p in descargados:
        log(f"  ✅ {p.name}")
    if errores:
        log(f"\n  ❌ Errores ({len(errores)}):")
        for t, e in errores:
            log(f"     • {t}: {e[:120]}")
    return descargados, errores


if __name__ == "__main__":
    # ── TEST: simular fecha para verificar lógica T-2 ─────────────────────
    # Pon una fecha aquí para simular. None = usa la fecha real de hoy.
    # Ejemplo: date(2024, 4, 15) = "estamos en abril del año pasado"
    #   → último dato = febrero 2024 → año=2024, meses=[Enero, Febrero]
    TEST_DATE = date(2025, 4, 15)  # simula "estamos en abril 2025" → T-2 = feb 2025 → año=2025, meses=[Enero,Febrero]
    # TEST_DATE = None  # ← descomenta para usar fecha real

    if TEST_DATE is not None:
        ultimo     = TEST_DATE - relativedelta(months=2)
        anio_usar  = str(ultimo.year)
        meses_usar = list(range(1, ultimo.month + 1))
        print(f"\n{'='*55}")
        print(f"  MODO TEST — hoy simulado : {TEST_DATE.strftime('%Y-%m-%d')}")
        print(f"  Último dato disponible   : {ultimo.strftime('%Y-%m')} (T-2)")
        print(f"  → Año a consultar  : {anio_usar}")
        print(f"  → Meses a incluir  : {', '.join(MESES_ES[m] for m in meses_usar)}")
        print(f"{'='*55}\n")
    else:
        anio_usar, meses_usar = get_anio_y_meses()
        print(f"\n  Modo REAL → Año: {anio_usar}, "
              f"Meses: {', '.join(MESES_ES[m] for m in meses_usar)}\n")

    run_all(
        email        = os.getenv("ADEX_EMAIL", "cesarbravoc"),
        password     = os.getenv("ADEX_PASS",  "123456"),
        download_dir = str(Path.cwd() / "downloads_adex"),
        headless     = False,
        anio         = anio_usar,
        meses        = meses_usar,
    )
