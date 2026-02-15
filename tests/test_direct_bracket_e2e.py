"""Playwright E2E tests for KO Directo (direct bracket without groups).

Tests the full flow:
1. Create tournament
2. Import players for doubles
3. Import pairs
4. Go to KO Directo page
5. Generate direct bracket (seeded + random modes)
6. Verify bracket displays correctly
"""

import os
import subprocess
import time
import signal
import shutil
import pytest
from pathlib import Path

# Only run if playwright is installed
pytest.importorskip("playwright")
from playwright.sync_api import Page, expect


# ── Config ───────────────────────────────────────────────────────────────────

SERVER_PORT = 8766
BASE_URL = f"http://127.0.0.1:{SERVER_PORT}"
PROJECT_ROOT = Path(__file__).parent.parent
DATA_DIR = PROJECT_ROOT / "data" / "samples"


# ── Fixtures ─────────────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def server():
    """Start a fresh ETTEM server for testing."""
    test_ettem_dir = PROJECT_ROOT / ".ettem_test_direct"
    if test_ettem_dir.exists():
        shutil.rmtree(test_ettem_dir)
    test_ettem_dir.mkdir(exist_ok=True)

    # Copy license key if available
    license_src = PROJECT_ROOT / ".ettem" / "license.key"
    if license_src.exists():
        shutil.copy(license_src, test_ettem_dir / "license.key")

    env = os.environ.copy()
    env["ETTEM_DATA_DIR"] = str(test_ettem_dir)
    env["PYTHONPATH"] = str(PROJECT_ROOT / "src")

    proc = subprocess.Popen(
        [
            str(PROJECT_ROOT / ".venv" / "bin" / "python"), "-m", "uvicorn",
            "ettem.webapp.app:app",
            "--host", "127.0.0.1",
            "--port", str(SERVER_PORT),
        ],
        env=env,
        cwd=str(PROJECT_ROOT),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )

    # Wait for server to accept connections
    import socket
    for _ in range(40):
        if proc.poll() is not None:
            stdout = proc.stdout.read().decode(errors="replace")
            stderr = proc.stderr.read().decode(errors="replace")
            raise RuntimeError(f"Server died: {stderr}")
        try:
            sock = socket.create_connection(("127.0.0.1", SERVER_PORT), timeout=1)
            sock.close()
            time.sleep(0.5)
            break
        except OSError:
            time.sleep(0.5)
    else:
        proc.kill()
        raise RuntimeError("Server did not start within 20 seconds")

    yield proc

    try:
        proc.terminate()
        proc.wait(timeout=5)
    except Exception:
        proc.kill()
        proc.wait(timeout=3)
    shutil.rmtree(test_ettem_dir, ignore_errors=True)


@pytest.fixture(scope="module")
def browser_context(server, browser):
    context = browser.new_context(base_url=BASE_URL)
    yield context
    context.close()


@pytest.fixture
def page(browser_context):
    page = browser_context.new_page()
    yield page
    page.close()


# ── Tests ────────────────────────────────────────────────────────────────────

class TestDirectBracketE2E:
    """Test the full KO Directo workflow for doubles."""

    def test_01_homepage_loads(self, page: Page):
        """App loads without license redirect."""
        page.goto("/")
        page.wait_for_load_state("networkidle")
        assert "/license" not in page.url or page.url.endswith("/")

    def test_02_create_tournament(self, page: Page):
        """Create a test tournament."""
        page.goto("/tournaments")
        page.wait_for_load_state("networkidle")

        create_btn = page.locator("button:has-text('Crear'), button:has-text('Create')")
        if create_btn.count() > 0:
            create_btn.first.click()
            page.wait_for_timeout(500)
            page.fill("#name", "Test KO Directo")
            page.fill("#location", "Test Venue")
            page.click("#create-modal button[type='submit']")
            page.wait_for_load_state("networkidle")

    def test_03_import_players(self, page: Page):
        """Import 8 doubles players from CSV."""
        page.goto("/admin/import-players")
        page.wait_for_load_state("networkidle")

        page.click("text=Importar desde CSV")
        page.wait_for_timeout(300)

        csv_path = str(DATA_DIR / "players_doubles_test.csv")
        page.set_input_files("input[name='csv_file']", csv_path)

        page.click("#btn-preview-csv")
        page.wait_for_timeout(1000)

        submit_btn = page.locator("#btn-submit-csv")
        expect(submit_btn).to_be_visible(timeout=5000)
        submit_btn.click()
        page.wait_for_load_state("networkidle")

    def test_04_import_pairs(self, page: Page):
        """Import 4 pairs from CSV."""
        page.goto("/admin/import-pairs")
        page.wait_for_load_state("networkidle")

        page.click("text=Importar CSV")
        page.wait_for_timeout(300)

        csv_path = str(DATA_DIR / "pairs_md_test.csv")
        page.set_input_files("input[name='csv_file']", csv_path)

        # Check assign seeds
        assign_seeds = page.locator("input[name='assign_seeds']")
        if assign_seeds.count() > 0:
            assign_seeds.check()

        page.click("button[type='submit']")
        page.wait_for_load_state("networkidle")

    def test_05_direct_bracket_page_loads(self, page: Page):
        """KO Directo page loads and shows MD category."""
        page.goto("/admin/direct-bracket")
        page.wait_for_load_state("networkidle")

        content = page.content()
        assert "KO Directo" in content
        assert "MD" in content

    def test_06_direct_bracket_nav_link(self, page: Page):
        """Dashboard has KO Directo button."""
        page.goto("/")
        page.wait_for_load_state("networkidle")

        link = page.locator("a[href='/admin/direct-bracket']")
        expect(link).to_be_visible()

    def test_07_preview_shows_competitors(self, page: Page):
        """Selecting a category shows competitor preview."""
        page.goto("/admin/direct-bracket")
        page.wait_for_load_state("networkidle")

        page.select_option("select[name='category']", "MD")
        page.wait_for_timeout(500)

        # Preview info should appear
        preview = page.locator("#preview-info")
        expect(preview).to_be_visible()

        # Should show "N parejas → bracket de M" for a doubles category
        preview_text = preview.text_content()
        assert "parejas" in preview_text
        assert "bracket" in preview_text

        # Competitors table should appear
        competitors_card = page.locator("#competitors-card")
        expect(competitors_card).to_be_visible()

    def test_08_generate_seeded_bracket(self, page: Page):
        """Generate a seeded direct bracket for MD via preview."""
        page.goto("/admin/direct-bracket")
        page.wait_for_load_state("networkidle")

        page.select_option("select[name='category']", "MD")
        page.select_option("select[name='best_of']", "5")
        page.select_option("select[name='draw_mode']", "seeded")
        page.fill("input[name='random_seed']", "42")

        # Click "Ver Sorteo" to see preview
        page.click("button:has-text('Ver Sorteo')")
        page.wait_for_load_state("networkidle")

        # Should be on preview page with matchups
        content = page.content()
        assert "Vista Previa" in content or "Sorteo" in content
        assert "Confirmar" in content

        # Click "Confirmar y Generar" to execute
        page.click("button:has-text('Confirmar y Generar')")
        page.wait_for_load_state("networkidle")

        # Should redirect to bracket page
        assert "/bracket/MD" in page.url or "MD" in page.content()

        # Should show bracket matches
        content = page.content()
        assert "Perez" in content or "Lopez" in content or "Rodriguez" in content

    def test_09_bracket_visual_works(self, page: Page):
        """Visual bracket page loads for the direct bracket."""
        page.goto("/category/MD/bracket")
        page.wait_for_load_state("networkidle")

        content = page.content()
        # Should show bracket visualization
        assert "MD" in content

    def test_10_category_shows_ko_directo(self, page: Page):
        """Category page shows KO Directo info (no groups)."""
        page.goto("/category/MD")
        page.wait_for_load_state("networkidle")

        content = page.content()
        assert "KO Directo" in content

    def test_11_regenerate_with_random_draw(self, page: Page):
        """Regenerate bracket with random draw mode via preview."""
        page.goto("/admin/direct-bracket")
        page.wait_for_load_state("networkidle")

        page.select_option("select[name='category']", "MD")
        page.select_option("select[name='draw_mode']", "random")
        page.fill("input[name='random_seed']", "99")

        # Click "Ver Sorteo" then confirm
        page.click("button:has-text('Ver Sorteo')")
        page.wait_for_load_state("networkidle")

        page.click("button:has-text('Confirmar y Generar')")
        page.wait_for_load_state("networkidle")

        # Should redirect to bracket page
        assert "/bracket/MD" in page.url or "MD" in page.content()

    def test_12_create_groups_page_shows_banner(self, page: Page):
        """Create groups page shows KO Directo info banner."""
        page.goto("/admin/create-groups")
        page.wait_for_load_state("networkidle")

        content = page.content()
        assert "KO Directo" in content
        link = page.locator("a[href='/admin/direct-bracket']")
        expect(link).to_be_visible()
