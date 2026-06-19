"""Publish layer — serve media files via cloudflared tunnels."""

import os
import subprocess
import time
import urllib.request
from typing import Optional


class PublishError(Exception):
    """Publishing failed."""
    pass


class Publisher:
    """Expose local media files via cloudflared tunnel."""

    def __init__(self, port: int = 8899):
        self.port = port
        self._tunnel_process: Optional[subprocess.Popen] = None
        self._http_process: Optional[subprocess.Popen] = None
        self._public_url: Optional[str] = None

    def publish(self, file_path: str) -> str:
        """Expose a single file or directory. Returns public URL."""
        if not os.path.exists(file_path):
            raise PublishError(f"File not found: {file_path}")

        # Start HTTP server if not running
        if self._http_process is None or self._http_process.poll() is not None:
            self._start_http_server(os.path.dirname(file_path))

        # Start tunnel if not running
        if self._tunnel_process is None or self._tunnel_process.poll() is not None:
            self._start_tunnel()

        if not self._public_url:
            raise PublishError("Could not determine public URL")

        filename = os.path.basename(file_path)
        return f"{self._public_url}/{filename}"

    def serve_dir(self, dir_path: str) -> str:
        """Serve entire directory. Returns public base URL."""
        if not os.path.isdir(dir_path):
            raise PublishError(f"Not a directory: {dir_path}")

        self._start_http_server(dir_path)
        self._start_tunnel()

        if not self._public_url:
            raise PublishError("Could not determine public URL")

        return self._public_url

    def _start_http_server(self, serve_dir: str) -> None:
        """Start Python HTTP server in background."""
        import threading

        def run_server():
            import http.server
            import socketserver

            class Handler(http.server.SimpleHTTPRequestHandler):
                def __init__(self, *args, **kwargs):
                    super().__init__(*args, directory=serve_dir, **kwargs)

            with socketserver.TCPServer(("", self.port), Handler) as httpd:
                httpd.serve_forever()

        t = threading.Thread(target=run_server, daemon=True)
        t.start()
        time.sleep(0.5)

    def _start_tunnel(self) -> None:
        """Start cloudflared tunnel, extract public URL."""
        self._tunnel_process = subprocess.Popen(
            ["cloudflared", "tunnel", "--url", f"http://localhost:{self.port}"],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )

        # Parse the trycloudflare URL from output
        deadline = time.time() + 30
        import re
        url_pattern = re.compile(r"https://[a-z-]+\.trycloudflare\.com")

        while time.time() < deadline:
            line = self._tunnel_process.stdout.readline()
            if not line:
                time.sleep(0.5)
                continue

            match = url_pattern.search(line)
            if match:
                self._public_url = match.group()
                # Verify reachable
                try:
                    urllib.request.urlopen(
                        self._public_url, timeout=5
                    )
                    return
                except Exception:
                    continue

        raise PublishError("cloudflared tunnel failed to start")

    def stop(self) -> None:
        """Stop tunnel and HTTP server."""
        for proc in [self._tunnel_process, self._http_process]:
            if proc and proc.poll() is None:
                proc.terminate()
                try:
                    proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    proc.kill()

    @property
    def is_running(self) -> bool:
        return (
            self._tunnel_process is not None
            and self._tunnel_process.poll() is None
            and self._public_url is not None
        )
