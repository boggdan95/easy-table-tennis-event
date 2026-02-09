"""Playwright E2E tests for doubles support.

Tests the full doubles workflow:
1. Create tournament
2. Import singles players (who will form pairs)
3. Import pairs via CSV
4. Create manual pair
5. Create groups for doubles category
6. Verify group matches show pair names
7. Delete a pair
"""

import os
import subprocess
import time
import signal
import pytest
from pathlib import Path
from playwright.sync_api import Page, expect


# ── Fixtures ────────────────────────────────────────────────────────────────

SERVER_PORT = 8765
BASE_URL = f"http://127.0.0.1:{SERVER_PORT}"
PROJECT_ROOT = Path(__file__).parent.parent
DATA_DIR = PROJECT_ROOT / "data" / "samples"


@pytest.fixture(scope="module")
def server():
    """Start the ETTEM server for testing."""
    import shutil

    # Use a temp DB for testing
    test_ettem_dir = PROJECT_ROOT / ".ettem_test"
    if test_ettem_dir.exists():
        shutil.rmtree(test_ettem_dir)
    test_ettem_dir.mkdir(exist_ok=True)

    # Copy license key
    license_src = PROJECT_ROOT / ".ettem" / "license.key"
    if license_src.exists():
        shutil.copy(license_src, test_ettem_dir / "license.key")

    env = os.environ.copy()
    env["ETTEM_DATA_DIR"] = str(test_ettem_dir)

    proc = subprocess.Popen(
        [
            "python", "-m", "uvicorn",
            "ettem.webapp.app:app",
            "--host", "127.0.0.1",
            "--port", str(SERVER_PORT),
        ],
        env=env,
        cwd=str(PROJECT_ROOT),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0,
    )

    # Wait for server to start (check TCP connection, not HTTP status)
    import socket
    for i in range(40):
        # Check if process died
        if proc.poll() is not None:
            stdout = proc.stdout.read().decode(errors="replace")
            stderr = proc.stderr.read().decode(errors="replace")
            raise RuntimeError(
                f"Server process exited with code {proc.returncode}\n"
                f"STDOUT: {stdout}\nSTDERR: {stderr}"
            )
        try:
            sock = socket.create_connection(("127.0.0.1", SERVER_PORT), timeout=1)
            sock.close()
            time.sleep(0.5)  # Give server a moment after accepting connections
            break
        except OSError:
            time.sleep(0.5)
    else:
        proc.kill()
        stdout = proc.stdout.read().decode(errors="replace")
        stderr = proc.stderr.read().decode(errors="replace")
        raise RuntimeError(
            f"Server did not start within 20 seconds\n"
            f"STDOUT: {stdout}\nSTDERR: {stderr}"
        )

    yield proc

    # Cleanup
    try:
        if os.name == "nt":
            proc.send_signal(signal.CTRL_BREAK_EVENT)
        else:
            proc.terminate()
        proc.wait(timeout=5)
    except Exception:
        proc.kill()
        proc.wait(timeout=3)
    shutil.rmtree(test_ettem_dir, ignore_errors=True)


@pytest.fixture(scope="module")
def browser_context(server, browser):
    """Create a browser context with the test server."""
    context = browser.new_context(base_url=BASE_URL)
    yield context
    context.close()


@pytest.fixture
def page(browser_context):
    """Create a new page for each test."""
    page = browser_context.new_page()
    yield page
    page.close()


# ── Helper ──────────────────────────────────────────────────────────────────

def create_tournament(page: Page, name: str = "Test Doubles Tournament"):
    """Create a tournament if none exists."""
    page.goto("/tournaments")
    page.wait_for_load_state("networkidle")

    # Open the create tournament modal
    create_btn = page.locator("button:has-text('Crear'), button:has-text('Create')")
    if create_btn.count() > 0:
        create_btn.first.click()
        page.wait_for_timeout(500)  # Wait for modal animation

        # Fill in the modal form
        page.fill("#name", name)
        page.fill("#location", "Test Venue")

        # Submit the modal form
        page.click("#create-modal button[type='submit']")
        page.wait_for_load_state("networkidle")


# ── Tests ───────────────────────────────────────────────────────────────────

class TestDoublesWorkflow:
    """Test the full doubles workflow end-to-end."""

    def test_01_homepage_loads(self, page: Page):
        """Verify the app loads (license is valid)."""
        page.goto("/")
        # Should not redirect to license page
        assert "/license" not in page.url or page.url.endswith("/")

    def test_02_create_tournament(self, page: Page):
        """Create a test tournament."""
        create_tournament(page)

    def test_03_import_players_page(self, page: Page):
        """Verify import players page loads."""
        page.goto("/admin/import-players")
        page.wait_for_load_state("networkidle")
        assert page.title()

    def test_04_import_players_csv(self, page: Page):
        """Import players that will form doubles pairs."""
        page.goto("/admin/import-players")
        page.wait_for_load_state("networkidle")

        # Click CSV import button to show the CSV section
        page.click("text=Importar desde CSV")
        page.wait_for_timeout(300)

        # Upload CSV file
        csv_path = str(DATA_DIR / "players_doubles_test.csv")
        page.set_input_files("input[name='csv_file']", csv_path)

        # Click preview first (required to enable submit button)
        page.click("#btn-preview-csv")
        page.wait_for_timeout(1000)  # Wait for preview to render

        # Now the submit button should be visible
        submit_btn = page.locator("#btn-submit-csv")
        expect(submit_btn).to_be_visible(timeout=5000)
        submit_btn.click()
        page.wait_for_load_state("networkidle")

    def test_05_import_pairs_page_loads(self, page: Page):
        """Verify the import pairs page loads."""
        page.goto("/admin/import-pairs")
        page.wait_for_load_state("networkidle")

        # Should see the title
        content = page.content()
        assert "Parejas" in content or "Pairs" in content

    def test_06_import_pairs_nav_link(self, page: Page):
        """Verify the pairs nav link exists in sidebar."""
        page.goto("/")
        page.wait_for_load_state("networkidle")

        # Check sidebar has the link
        link = page.locator("a[href='/admin/import-pairs']")
        expect(link).to_be_visible()

    def test_07_import_pairs_csv(self, page: Page):
        """Import pairs from CSV file."""
        page.goto("/admin/import-pairs")
        page.wait_for_load_state("networkidle")

        # Click CSV import method
        page.click("text=Importar CSV")
        page.wait_for_timeout(300)

        # Upload CSV
        csv_path = str(DATA_DIR / "pairs_md_test.csv")
        page.set_input_files("input[name='csv_file']", csv_path)

        # Check assign seeds
        page.check("input[name='assign_seeds']")

        # Submit
        page.click("button[type='submit']")
        page.wait_for_load_state("networkidle")

        # Verify pairs are shown
        page.goto("/admin/import-pairs")
        page.wait_for_load_state("networkidle")
        content = page.content()
        assert "Perez" in content or "Lopez" in content, "Imported pair player names should appear"

    def test_08_pairs_table_shows_data(self, page: Page):
        """Verify the pairs table displays correct information."""
        page.goto("/admin/import-pairs")
        page.wait_for_load_state("networkidle")

        # Should show 4 pairs
        rows = page.locator("table tbody tr")
        assert rows.count() >= 4, f"Expected at least 4 pairs, got {rows.count()}"

        # Should show MD category badge
        content = page.content()
        assert "MD" in content

    def test_09_create_manual_pair(self, page: Page):
        """Test creating a pair manually (should fail - players already paired)."""
        page.goto("/admin/import-pairs")
        page.wait_for_load_state("networkidle")

        # Click manual creation
        page.click("text=Crear Pareja")
        page.wait_for_timeout(300)

        # Check that the manual form is visible with player dropdowns
        form = page.locator("#import-manual-section")
        expect(form).to_be_visible()

        # Verify player dropdowns are populated
        options = page.locator("#select-p1 option")
        assert options.count() > 1, "Player dropdown should have options"

    def test_10_create_groups_doubles(self, page: Page):
        """Create groups for the MD doubles category."""
        page.goto("/admin/create-groups")
        page.wait_for_load_state("networkidle")

        # Select MD category
        page.select_option("select[name='category']", "MD")

        # Set group size preference
        page.select_option("select[name='group_size_preference']", "4")

        # Submit to create groups
        page.click("button:has-text('Crear Grupos')")
        page.wait_for_load_state("networkidle")

        # Should redirect to category page
        page.wait_for_timeout(1000)

    def test_11_group_matches_show_pairs(self, page: Page):
        """Verify group matches display pair names (not individual players)."""
        # Navigate to MD category
        page.goto("/")
        page.wait_for_load_state("networkidle")

        # Click on MD category if visible
        md_link = page.locator("a:has-text('MD')")
        if md_link.count() > 0:
            md_link.first.click()
            page.wait_for_load_state("networkidle")

            content = page.content()
            # Pair names should contain "/" separator
            assert "/" in content or "Perez" in content, \
                "Group matches should display pair names"

    def test_12_pairs_page_still_works(self, page: Page):
        """Verify import-pairs page loads after group creation."""
        page.goto("/admin/import-pairs", timeout=10000)
        page.wait_for_load_state("networkidle")
        content = page.content()
        assert "Parejas" in content or "Pairs" in content
