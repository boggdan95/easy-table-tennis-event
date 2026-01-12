"""
ETTEM Launcher - Easy Table Tennis Event Manager

This script launches the ETTEM web application and opens it in the default browser.
Used for creating the standalone executable with PyInstaller.
"""

import os
import sys
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

def main():
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

    # Start uvicorn server
    uvicorn.run(
        "ettem.webapp.app:app",
        host="127.0.0.1",
        port=port,
        log_level="warning",
        access_log=False
    )

if __name__ == "__main__":
    main()
