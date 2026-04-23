"""Typer-based CLI chat client for the pharmacy sales agent."""

from __future__ import annotations

import json
from pathlib import Path

import typer
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.prompt import Prompt
from rich.table import Table

from ..graph.builder import build_graph
from ..logging import configure_logging

app = typer.Typer(add_completion=False, help="Pharmacy sales agent CLI.")
console = Console()


@app.callback()
def _main() -> None:
    configure_logging()


@app.command("rx")
def cmd_rx(
    file: Path = typer.Option(..., "--file", "-f", help="Đường dẫn tới file JSON đơn thuốc."),
) -> None:
    """Kiểm đơn thuốc có cấu trúc (JSON)."""
    payload = json.loads(file.read_text(encoding="utf-8"))
    graph = build_graph()
    state = graph.invoke(
        {
            "prescription_items": payload["items"],
            "patient_age_years": payload["patient"]["age_years"],
            "patient_pregnancy": payload["patient"].get("pregnancy", False),
            "patient_allergies": payload["patient"].get("allergies", []),
        }
    )
    _render_prescription(state["final_response"])


@app.command("sym")
def cmd_sym(
    symptoms: str = typer.Option(..., "--symptoms", "-s", help='Danh sách triệu chứng, phân tách bằng ","'),
    age: float = typer.Option(..., "--age", "-a", help="Tuổi bệnh nhân (năm)."),
    pregnancy: bool = typer.Option(False, "--pregnancy/--no-pregnancy"),
    duration_days: int | None = typer.Option(None, "--duration"),
    allergies: str = typer.Option("", "--allergies"),
) -> None:
    """Tư vấn OTC theo triệu chứng."""
    graph = build_graph()
    state = graph.invoke(
        {
            "symptoms_vi": [s.strip() for s in symptoms.split(",") if s.strip()],
            "duration_days": duration_days,
            "patient_age_years": age,
            "patient_pregnancy": pregnancy,
            "patient_allergies": [a.strip() for a in allergies.split(",") if a.strip()],
        }
    )
    _render_symptom(state["final_response"])


@app.command("chat")
def cmd_chat() -> None:
    """Chế độ hỏi-đáp: chọn rx/sym và điền tham số."""
    configure_logging()
    while True:
        choice = Prompt.ask(
            "Chọn luồng",
            choices=["rx", "sym", "quit"],
            default="sym",
        )
        if choice == "quit":
            break
        if choice == "rx":
            path = Prompt.ask("Đường dẫn JSON đơn thuốc")
            cmd_rx(Path(path))
        else:
            syms = Prompt.ask("Triệu chứng (cách nhau bởi dấu phẩy)")
            age = float(Prompt.ask("Tuổi bệnh nhân", default="30"))
            cmd_sym(symptoms=syms, age=age, pregnancy=False, duration_days=None, allergies="")


def _render_prescription(resp: dict) -> None:
    table = Table(title="Kết quả kiểm đơn", show_lines=True)
    table.add_column("Thuốc")
    table.add_column("Trạng thái")
    table.add_column("Tồn kho", justify="right")
    table.add_column("Thay thế")
    table.add_column("Cảnh báo")
    for r in resp.get("items", []):
        item = r["item"]
        subs = "\n".join(
            f"- {s['name_vi']} ({s['kind']}, còn {s['qty_on_hand']})"
            for s in r.get("substitutes", [])
        ) or "-"
        notes = "\n".join(r.get("safety_notes", [])) or "-"
        status = r["status"]
        style = {"in_stock": "green", "out_of_stock": "yellow", "not_carried": "red"}.get(
            status, "white"
        )
        table.add_row(
            item.get("drug_name") or item.get("active_ingredient"),
            f"[{style}]{status}[/{style}]",
            str(r.get("qty_on_hand", 0)),
            subs,
            notes,
        )
    console.print(table)
    console.print(Panel(Markdown(resp.get("summary_vi", "")), title="Tóm tắt"))
    console.print(f"[dim]{resp.get('disclaimer', '')}[/dim]")


def _render_symptom(resp: dict) -> None:
    flags = resp.get("red_flags", [])
    if flags:
        console.print(Panel("\n".join(f"- {f}" for f in flags), title="[red]Red flags[/red]"))
    sugs = resp.get("suggestions", [])
    if sugs:
        table = Table(title="Gợi ý OTC", show_lines=True)
        table.add_column("Công thức")
        table.add_column("Score", justify="right")
        table.add_column("Thành phần")
        for s in sugs:
            items_str = "\n".join(
                f"- {it['active_ingredient']}: {it['dose_per_take_vi']} x "
                f"{it['frequency_per_day']}/ng x {it['duration_days']}ng"
                for it in s["items"]
            )
            table.add_row(s["name_vi"], f"{s['score']:.2f}", items_str)
        console.print(table)
    console.print(Panel(Markdown(resp.get("summary_vi", "")), title="Tư vấn"))
    console.print(f"[dim]{resp.get('disclaimer', '')}[/dim]")


if __name__ == "__main__":
    app()
