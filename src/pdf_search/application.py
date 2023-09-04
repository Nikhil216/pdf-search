import argparse
import pathlib
from datetime import datetime
from typing import List

import sqlitedict
from rich.console import Console
from rich.prompt import Prompt

from . import pdf


console = Console()


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
    with sqlitedict.SqliteDict(
        vault_path / "vault.db", tablename="pdfs", autocommit=True
    ) as file_db:
        while True:
            command = command_parser(console.input("> "))
            match command:
                case ["add", *rest]:
                    if rest:
                        pdf_file_path = pathlib.Path(rest[0])
                        if not pdf_file_path.exists() or not pdf_file_path.is_file():
                            console.print(
                                f"Error: PDF file does not exists: {pdf_file_path}",
                                style="bold red",
                            )
                            return
                        pdf_file = pdf.PdfFile(pdf_file_path)
                        pdf_types = ("book", "paper")
                        metadata_keys = ["Author", "Title", "Year", "DOI"]
                        pdf_type = console.input(f"Type: [blue]{pdf_types}[/]: ")
                        if pdf_type == "book":
                            metadata_keys += ["Edition", "ISBN10", "ISBN13"]
                        ## TODO: Add page previewer
                        metadata = pdf_file.metadata
                        metadata_dict = {}
                        for key in metadata_keys:
                            metadata_dict[f"/{key}"] = Prompt.ask(
                                key, default=metadata.get(f"/{key}", "")
                            )
                        utc_time = "+05'30"
                        time = datetime.now().strftime(f"D\072%Y%m%d%H%M%S{utc_time}")
                        metadata_dict["/ModDate"] = time
                        metadata_dict["/Producer"] = "PDF Search"
                        pdf_file.update_metadata(metadata_dict)
                        pdf_file_name = pdf_file.generate_filename()
                        pdf_file_key = pdf_file.file_hash
                        pdf_file_path = vault_path / f"{pdf_type}s" / pdf_file_name
                        pdf_file.write(pdf_file_path)
                        file_db[pdf_file_key] = {
                            "type": pdf_type,
                            "title": metadata_dict["/Title"],
                            "authors": [a.strip() for a in metadata_dict["/Author"].split(",")],
                            "year": metadata_dict["/Year"],
                            "doi": metadata_dict["/DOI"],
                            "edition": metadata_dict["/Edition"]
                            if "/Edition" in metadata_dict
                            else "",
                            "isbn10": metadata_dict["/ISBN10"]
                            if "/ISBN10" in metadata_dict
                            else "",
                            "isbn13": metadata_dict["/ISBN13"]
                            if "/ISBN13" in metadata_dict
                            else "",
                            "filename": pdf_file_name,
                        }
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
    db_path = vault_path / "vault.db"
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
    ## TODO: Check for missing files
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
