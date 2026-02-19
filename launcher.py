"""
ETTEM Launcher - Easy Table Tennis Event Manager

This script launches the ETTEM web application and opens it in the default browser.
Used for creating the standalone executable with PyInstaller.
"""

import os
import sys
import platform
import signal
import webbrowser
import threading
import time
import socket

def get_free_port(start_port=8000):
    """Find an available port starting from start_port."""
    port = start_port
    while port < start_port + 100:
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.bind(('127.0.0.1', port))
                return port
        except OSError:
            port += 1
    return start_port  # fallback

def open_browser(port, delay=2):
    """Open browser after a short delay to allow server to start."""
    time.sleep(delay)
    webbrowser.open(f'http://127.0.0.1:{port}')

def setup_logging():
    """Redirect stdout/stderr to a log file on frozen macOS (no console)."""
    if getattr(sys, 'frozen', False) and platform.system() == "Darwin":
        import logging
        from pathlib import Path
        log_dir = Path.home() / "Library" / "Application Support" / "ETTEM"
        log_dir.mkdir(parents=True, exist_ok=True)
        log_file = log_dir / "ettem.log"
        # Redirect stdout/stderr to log file
        log_handle = open(log_file, "a", encoding="utf-8")
        sys.stdout = log_handle
        sys.stderr = log_handle
        return log_file
    return None

def main():
    # macOS: handle SIGTERM gracefully (sent when closing .app bundle)
    if platform.system() == "Darwin":
        signal.signal(signal.SIGTERM, lambda s, f: sys.exit(0))

    # Setup logging early (before any imports that might fail)
    log_file = setup_logging()

    # Set up paths for PyInstaller
    if getattr(sys, 'frozen', False):
        # Running as compiled executable
        base_path = sys._MEIPASS
        # Add src to path
        sys.path.insert(0, base_path)
    else:
        # Running as script
        base_path = os.path.dirname(os.path.abspath(__file__))
        sys.path.insert(0, os.path.join(base_path, 'src'))

    try:
        # Import uvicorn after path setup
        import uvicorn

        # Find available port
        port = get_free_port(8000)

        # Open browser in background thread
        browser_thread = threading.Thread(target=open_browser, args=(port,), daemon=True)
        browser_thread.start()

        print(f"""
    ================================================
        ETTEM - Easy Table Tennis Event Manager
    ================================================

    Server running at: http://127.0.0.1:{port}

    Opening browser automatically...

    Press Ctrl+C to stop the server.
    ================================================
        """)

        if log_file:
            print(f"    Log file: {log_file}")

        # Start uvicorn server
        uvicorn.run(
            "ettem.webapp.app:app",
            host="127.0.0.1",
            port=port,
            log_level="info",
            access_log=False
        )
    except Exception as e:
        print(f"FATAL ERROR: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc(file=sys.stderr)
        if log_file:
            print(f"See log file for details: {log_file}", file=sys.stderr)
        raise

if __name__ == "__main__":
    main()
