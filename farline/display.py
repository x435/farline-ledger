"""Rich output with a standard-library fallback."""

from collections.abc import Iterable, Sequence

try:
    from rich import box
    from rich.console import Console
    from rich.panel import Panel
    from rich.table import Table
    from rich.text import Text
except ImportError:
    Console = None


class Display:
    def __init__(self, plain: bool = False):
        self.console = Console(highlight=False) if not plain and Console is not None else None

    def line(self, message: str, style: str = "") -> None:
        if self.console is None:
            print(message)
        else:
            self.console.print(Text(message, style=style))

    def lines(self, messages: Iterable[str]) -> None:
        for message in messages:
            notable = message.startswith((
                "Training complete", "Manufacturing complete", "Manufacturing started",
                "Offline catch-up", "Clock anomaly",
            ))
            self.line(message, "green" if notable else "")

    def panel(self, title: str, content: str) -> None:
        if self.console is None:
            print(f"\n{title}\n{content}")
        else:
            self.console.print(Panel.fit(Text(content), title=Text(title, style="bold"),
                                         border_style="cyan", padding=(0, 1)))

    def table(self, title: str, columns: Sequence[str],
              rows: Iterable[Sequence[str]], *, right: Sequence[int] = ()) -> None:
        rows = list(rows)
        if self.console is not None:
            table = Table(title=Text(title, style="bold"), title_justify="left",
                          box=box.SIMPLE_HEAD, header_style="bold cyan", pad_edge=False)
            for index, column in enumerate(columns):
                table.add_column(column, justify="right" if index in right else "left")
            for row in rows:
                table.add_row(*(Text(cell) for cell in row))
            self.console.print(table)
            return
        print(f"\n{title}")
        widths = [max(map(len, cells)) for cells in zip(columns, *rows)]
        for row in (columns, *rows):
            cells = [cell.rjust(width) if index in right else cell.ljust(width)
                     for index, (cell, width) in enumerate(zip(row, widths))]
            print("  ".join(cells).rstrip())
