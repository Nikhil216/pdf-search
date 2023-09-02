import argparse
import pathlib
from typing import List

from . import pdf
from .console import console, Prompt


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
            console.print(f"Error: {msg}", style="bold red")
            return
    while True:
        command = command_parser(console.input("> "))
        match command:
            case ["add", *rest]:
                if rest:
                    pdf_path = pathlib.Path(rest[0])
                    if not pdf_path.exists() or not pdf_path.is_file():
                        console.print(f"Error: PDF file does not exists: {pdf_path}", style="bold red")
                    metadata = pdf.read_metadata(pdf_path)
                    metadata_dict = {}
                    for key in ["Author", "Title", "Year", "CreationDate", "DOI", "Edition", "ISBN10", "ISBN13"]:
                        metadata_dict[f"/{key}"] = console.input(f'{key} [blue]({metadata.get(f"/{key}", "")})[/]: ')
                    console.print("Added PDF file")
                else:
                    console.print("Error: missing file path in add command", style="bold red")
            case ["quit"]:
                return
            case _:
                console.print(f"Error: invalid command {command}", style="bold red")


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


def command_parser(input_str: str) -> List[str]:
    input_str = input_str.strip()
    args = [""]
    quote = ""
    for c in input_str:
        if quote:
            if c == quote:
                quote = ""
            else:
                args[-1] += c
        else:
            if c == " ":
                args.append("")
            elif c in "\"'":
                quote = c
            else:
                args[-1] += c
    return args
