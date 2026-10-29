#!/usr/bin/env python3
"""Main Entrypoint for Antigravity Direct API & Chatbot Server."""

import argparse
import sys
import uvicorn
from rich.console import Console
from rich.panel import Panel

from antigravity_api.auth import TokenManager
from antigravity_api.models import AVAILABLE_MODELS

console = Console()


def print_startup_banner(host: str, port: int, email: str):
    models_str = ", ".join(list(AVAILABLE_MODELS.keys())[:5]) + "..."
    console.print(
        Panel.fit(
            f"[bold cyan]Antigravity Direct API & Web Chatbot Server[/bold cyan]\n\n"
            f"[green]Authenticated Account:[/green] {email}\n"
            f"[green]Web Chat Interface:[/green]   [bold underline]http://localhost:{port}[/bold underline]\n"
            f"[green]OpenAI API Base:[/green]      http://localhost:{port}/v1\n"
            f"[green]Anthropic API Base:[/green]   http://localhost:{port}/v1/messages\n"
            f"[green]Health Check:[/green]         http://localhost:{port}/health\n\n"
            f"[dim]Available Models:[/dim] {models_str}\n"
            f"[bold yellow]Zero CLI subprocess overhead - 100% Native Python & Cloud API[/bold yellow]",
            border_style="cyan"
        )
    )


def main():
    parser = argparse.ArgumentParser(description="Antigravity Direct API Server")
    parser.add_argument("--host", default="0.0.0.0", help="Bind host (default: 0.0.0.0)")
    parser.add_argument("--port", type=int, default=8000, help="Bind port (default: 8000)")
    parser.add_argument("--reload", action="store_true", help="Auto-reload on code change")
    args = parser.parse_args()

    mgr = TokenManager()
    user_email = mgr.user_email or "vikrantranahome@gmail.com"

    print_startup_banner(args.host, args.port, user_email)

    uvicorn.run(
        "antigravity_api.server:app",
        host=args.host,
        port=args.port,
        reload=args.reload,
        log_level="info"
    )


if __name__ == "__main__":
    main()
