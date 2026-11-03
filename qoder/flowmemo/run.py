#!/usr/bin/env python3
"""FlowMemo launcher — starts the server and opens the workspace."""
import os
import sys
import webbrowser
import threading
import time

def main():
    port = int(os.environ.get("FLOWMEMO_PORT", "8900"))
    host = os.environ.get("FLOWMEMO_HOST", "127.0.0.1")

    os.environ.setdefault("FLOWMEMO_DB", os.path.join(os.path.dirname(__file__), "data", "flowmemo.db"))

    print(f"FlowMemo 正在启动...")
    print(f"  地址: http://{host}:{port}")
    print(f"  PowerContext: {os.environ.get('POWERCONTEXT_URL', '未配置')}")
    print()

    def open_browser():
        time.sleep(1.5)
        try:
            webbrowser.open(f"http://{host}:{port}")
        except Exception:
            pass

    threading.Thread(target=open_browser, daemon=True).start()

    import uvicorn
    from server.app import app
    uvicorn.run(app, host=host, port=port, log_level="info")

if __name__ == "__main__":
    main()
