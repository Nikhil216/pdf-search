import argparse
from datetime import datetime
import pathlib
import shutil
from typing import List

from rich.console import Console
from rich.prompt import Prompt
from rich.progress import track
import sqlitedict
from whoosh.qparser import QueryParser
from whoosh import index as whoosh_index

from . import pdf
from . import vault


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
    result = vault.check_vault_status(vault_path)
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
                            continue
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
                            "isbn10": metadata_dict["/ISBN10"].replace("-", "")
                            if "/ISBN10" in metadata_dict
                            else "",
                            "isbn13": metadata_dict["/ISBN13"].replace("-", "")
                            if "/ISBN13" in metadata_dict
                            else "",
                            "filename": pdf_file_name,
                        }
                        progress_track = lambda it: track(it, description="Indexing...")
                        index_path = vault_path / "index"
                        pdf_file.write_index(pdf_file_path, index_path, progress_track)
                        console.print("Added PDF file")
                    else:
                        console.print("Error: missing file path in add command", style="bold red")
                case ["remove", *rest]:
                    if rest:
                        pdf_file_path = pathlib.Path(rest[0])
                        pdf_file_path = vault_path / pdf_file_path
                        if pdf_file_path.exists() and pdf_file_path.is_file():
                            if pdf_file_path.is_relative_to(vault_path):
                                pdf_file = pdf.PdfFile(pdf_file_path)
                                pdf_file_key = pdf_file.file_hash
                                del file_db[pdf_file_key]
                                index_path = vault_path / "index"
                                index = whoosh_index.open_dir(index_path, "pages")
                                index_writer = index.writer()
                                index_writer.delete_by_term("file_key", pdf_file.file_hash)
                                index_writer.commit()
                                index.close()
                                pdf_file_path.unlink()
                                console.print(f"Deleted file {pdf_file_path.as_posix()}")
                            else:
                                console.print("Error: The given path is not in the vault")
                        else:
                            console.print("Error: The given path is not a file", style="bold red")
                    else:
                        console.print(
                            "Error: missing file path in remove command", style="bold red"
                        )
                case ["search", *rest]:
                    if rest:
                        search_query = " ".join(rest)
                        index_path = vault_path / "index"
                        index = whoosh_index.open_dir(index_path, "pages")
                        qp = QueryParser("text", schema=index.schema)
                        q = qp.parse(search_query)
                        with index.searcher() as s:
                            results = s.search(q)
                            for page in results:
                                console.print(page["url"], style="underline blue")
                        index.close()
                    else:
                        console.print("Error: missing search query", style="bold red")
                case ["nuke"]:
                    response = Prompt.ask(
                        "Are you sure you want to [red bold]delete[/] your vault?",
                        choices=["yes", "no"],
                    )
                    if response == "yes":
                        shutil.rmtree(vault_path / "books")
                        shutil.rmtree(vault_path / "papers")
                        shutil.rmtree(vault_path / "index")
                        #    (vault_path / "vault.db").unlink()
                        console.print("Vault has been deleted!")
                        return
                case ["help"]:
                    console.print("Commands:")
                    console.print("    [blue]help[/]\t\tList all the commands available")
                    console.print("    [blue]quit[/]\t\tQuit the console")
                    console.print("    [blue]add <file path>[/]\tAdd the file into the vault")
                    console.print(
                        "    [blue]remove <file path>[/]\tRemove the pdf file from the vault."
                    )
                    console.print("The file path must be the relative path from the vault")
                    console.print(
                        "    [blue]search <query>[/]\tSearch the vault for matching files"
                    )
                    console.print("    [blue]nuke[/]\t\tDelete all files and index inside the vault")
                case ["quit"]:
                    return
                case _:
                    console.print(f"Error: invalid command {command}", style="bold red")




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
