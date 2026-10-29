#!/usr/bin/env python3
"""Interactive Terminal Chatbot powered by Antigravity Direct API.
Zero CLI binary execution - pure Python native HTTP/SSE stream.
"""

import sys
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt

from antigravity_api.auth import TokenManager
from antigravity_api.client import AntigravityClient
from antigravity_api.models import AVAILABLE_MODELS, resolve_model_id

console = Console()


def print_banner(user_email: str, current_model: str):
    console.print(
        Panel.fit(
            f"[bold cyan]Antigravity Direct Terminal Chatbot[/bold cyan]\n"
            f"[dim]Connected Account:[/dim] [green]{user_email}[/green]\n"
            f"[dim]Active Model:[/dim] [yellow]{current_model}[/yellow]\n"
            f"[dim]Direct Google Cloud Code backend connection (No CLI subprocess)[/dim]\n"
            f"[dim]Commands:[/dim] [magenta]/model <name>[/magenta], [magenta]/models[/magenta], [magenta]/clear[/magenta], [magenta]/exit[/magenta]",
            border_style="cyan"
        )
    )


def main():
    token_mgr = TokenManager()
    if not token_mgr.access_token:
        console.print("[bold red]Error: No Antigravity OAuth token found![/bold red]")
        sys.exit(1)

    client = AntigravityClient(token_manager=token_mgr)
    current_model = "gemini-3.8-flash-high"

    print_banner(token_mgr.user_email or "vikrantranahome@gmail.com", current_model)

    conversation_history = []

    while True:
        try:
            user_input = Prompt.ask("\n[bold green]You[/bold green]").strip()
            if not user_input:
                continue

            if user_input.lower() in ("/exit", "/quit", "exit", "quit"):
                console.print("[yellow]Goodbye![/yellow]")
                break

            if user_input.lower() == "/clear":
                conversation_history = []
                console.print("[dim]Conversation history cleared.[/dim]")
                continue

            if user_input.lower() == "/models":
                console.print("\n[bold]Available Models:[/bold]")
                for m_id, info in AVAILABLE_MODELS.items():
                    console.print(f"  • [cyan]{m_id:<25}[/cyan] ({info.display_name})")
                continue

            if user_input.lower().startswith("/model"):
                parts = user_input.split(maxsplit=1)
                if len(parts) > 1:
                    resolved = resolve_model_id(parts[1])
                    current_model = resolved
                    console.print(f"[green]Switched model to:[/green] [bold yellow]{current_model}[/bold yellow]")
                else:
                    console.print(f"[yellow]Current model:[/yellow] {current_model}")
                continue

            # Add to history
            conversation_history.append({"role": "user", "parts": [{"text": user_input}]})

            console.print(f"\n[bold magenta]Antigravity ({current_model})[/bold magenta]:")

            full_reply = ""
            for chunk in client.stream_generate_content(
                model=current_model,
                contents=conversation_history,
                system_instruction="You are Antigravity, a helpful, brilliant AI assistant."
            ):
                resp = chunk.get("response", {})
                for cand in resp.get("candidates", []):
                    for part in cand.get("content", {}).get("parts", []):
                        if "text" in part and not part.get("thought", False):
                            text = part["text"]
                            full_reply += text
                            sys.stdout.write(text)
                            sys.stdout.flush()

            sys.stdout.write("\n")
            conversation_history.append({"role": "model", "parts": [{"text": full_reply}]})

        except KeyboardInterrupt:
            console.print("\n[yellow]Session paused. Type /exit to quit.[/yellow]")
        except Exception as e:
            console.print(f"\n[bold red]Error: {e}[/bold red]")


if __name__ == "__main__":
    main()
