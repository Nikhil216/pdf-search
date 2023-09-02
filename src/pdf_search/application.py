import argparse
import pathlib

from .console import console


def main():
    parser = argparse.ArgumentParser(description="Search through your local pdfs")
    parser.add_argument("command", choices=["interactive"], help="Start pdf-search console")
    parser.add_argument("--vault", type=pathlib.Path, default="./vault", help="path")

    args = parser.parse_args()
    match args.command:
        case "interactive":
            run_console_loop(args.vault)


def run_console_loop(vault_path: pathlib.Path):
    result = check_vault_status(vault_path)
    match result:
        case ("Ok", msg):
            if msg:
                console.print(msg)
        case ("Error", msg):
            console.print(msg, style="bold red")


def check_vault_status(vault_path: pathlib.Path):
    if not vault_path.exists() or not vault_path.is_dir():
        return ("Error", "The vault directory does not exists")
    books_path = vault_path / "books"
    papers_path = vault_path / "papers"
    db_path = vault_path / "vault.sqlite"
    created = []
    if not db_path.exists():
        db_path.touch()
        created.append("database")
    if not books_path.exists() or not books_path.is_dir():
        books_path.mkdir()
        created.append("books")
    if not papers_path.exists() or not papers_path.is_dir():
        papers_path.mkdir()
        created.append("papers")
    return ("Ok", f'Created {", ".join(created)}' if created else "")
