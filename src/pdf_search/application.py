import argparse
import pathlib
import math
import msvcrt
import os
from typing import List
import webbrowser

import polars as pl
from rich.progress import Progress, SpinnerColumn, TextColumn, track
from rich.prompt import Prompt
from rich.live import Live
from rich.layout import Layout
from rich.table import Table
from rich.text import Text
from rich.panel import Panel
from rich.columns import Columns

from . import pdf
from .vault import Vault, PDF_TYPES
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
    vault = Vault(vault_path)
    if vault.status_ok:
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
                        with Progress(
                            TextColumn("Reading"),
                            SpinnerColumn("line"),
                            console=console,
                            transient=True,
                            refresh_per_second=10,
                        ) as progress:
                            progress.add_task("Reading PDF")
                            pdf_file = pdf.PdfFile(vault, pdf_file_path)
                        metadata_keys = ["Authors", "Title", "Year"]
                        pdf_type = Prompt.ask("Type", console=console, choices=PDF_TYPES)
                        pdf_file.pdf_type = pdf_type
                        if pdf_type == "books":
                            metadata_keys += ["Edition", "ISBN10", "ISBN13"]
                        if pdf_type == "papers":
                            metadata_keys += ["DOI", "Journal", "Volume", "PageRange", "Keywords"]
                        ## TODO: Add page previewer
                        metadata = pdf_file.metadata
                        metadata_dict = {}
                        for key in metadata_keys:
                            metadata_dict[f"/{key}"] = Prompt.ask(
                                key, default=metadata.get(f"/{key}", "")
                            )
                        pdf_file.update_metadata(metadata_dict)
                        pdf_file.write_file_index()
                        pdf_file.write_page_index(
                            track_hashing=lambda x: track(x, "Hashing", transient=True),
                            track_indexing=lambda x: track(x, "Indexing", transient=True),
                        )
                        with Progress(
                            TextColumn("Writing PDF"),
                            SpinnerColumn("line"),
                            console=console,
                            transient=True,
                            refresh_per_second=10,
                        ) as progress:
                            progress.add_task("Writing")
                            pdf_file.write()
                        console.print("Added PDF file")
                    else:
                        console.print("Error: missing file path in add command", style="bold red")
                case ["remove", *rest]:
                    if rest:
                        pdf_file_path = pathlib.Path(rest[0])
                        pdf_file_path = vault_path / pdf_file_path
                        if pdf_file_path.exists() and pdf_file_path.is_file():
                            if pdf_file_path.is_relative_to(vault_path):
                                pdf_file = pdf.PdfFile(vault, pdf_file_path)
                                files_deleted, pages_deleted = pdf_file.remove_file_index()
                                pdf_file_path.unlink()
                                console.print(
                                    f"Deleted file {pdf_file_path.as_posix()},"
                                    f" {files_deleted} file index and {pages_deleted} pages index"
                                )
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
                        query_str = " ".join(rest)
                        pages = vault.search_pages(query_str, limit=100)
                        console_loop_search_panel(pages)
                    else:
                        console.print("Error: missing search query", style="bold red")
                case ["browse"]:
                    files = vault.list_all_files()
                    console_loop_browse_panel(files, vault.get_pdf_url)
                case ["import", *rest]:
                    if rest:
                        import_dir_path = pathlib.Path(rest[0])
                        total, errors = import_pdf_files(vault, import_dir_path)
                        console.print(f"Imported {total - len(errors)}/{total} PDF files")
                        if errors:
                            console.print("Import Errors:", style="red bold")
                            for filename, error in errors.items():
                                console.print(f"  {filename}", style="red")
                                console.print(f"  >>> {error}", style="red")
                    else:
                        console.print("Error: Missing improt directory path", style="red bold")
                case ["nuke"]:
                    response = Prompt.ask(
                        "Are you sure you want to [red bold]delete[/] your vault?",
                        choices=["yes", "no"],
                    )
                    if response == "yes":
                        vault.nuke()
                        console.print("Vault has been deleted!")
                        return
                case ["help"]:
                    console.print("Commands:")
                    console.print("    [blue]help[/]\t\tList all the commands available")
                    console.print("    [blue]quit[/]\t\tQuit the console")
                    console.print("    [blue]add <file>[/]\t\tAdd the pdf file into the vault")
                    console.print("    [blue]remove <file>[/]\tRemove the pdf file from the vault")
                    console.print("\t\t\tThe file path must be the relative path from the vault")
                    console.print(
                        "    [blue]search <query>[/]\tSearch the vault for matching files"
                    )
                    console.print(
                        "    [blue]nuke[/]\t\tDelete all files and index inside the vault"
                    )
                    console.print("    [blue]browse[/]\t\tBrowse through the files in the vault")
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


def search_panel(pages, selected, page, page_count):
    display = Layout()
    if pages:
        pages_table = Table()
        pages_table.add_column("Page")
        pages_table.add_column("Type")
        pages_table.add_column(f"File [{page + 1}/{page_count}]")
        for i, page in enumerate(pages):
            style = "blue" if i == selected else ""
            pages_table.add_row(
                str(page["page_number"]), page["pdf_type"], page["filename"], style=style
            )
    else:
        pages_table = Text("No pages found!")
    action_panel = Panel(
        f"j: down\nk: up\nh: prev page\nn: next page\no: open file\nq: quit", title="Actions"
    )
    pages_panel = Panel(pages_table, title="Pages")
    action_layout = Layout(action_panel, ratio=1)
    pages_layout = Layout(pages_panel, ratio=5)
    display.split_row(action_layout, pages_layout)
    return display


def browse_panel(files, pdf_type, selected_idx):
    display = Layout()
    if files:
        files_table = Table()
        files_table.add_column(pdf_type)
        for i, file in enumerate(files):
            style = "blue" if i == selected_idx else ""
            files_table.add_row(file["filename"], style=style)
    else:
        files_table = Text("No files found!")
    action_panel = Panel(
        "j: down\nk: up\nh: prev type\nl: next type\no: open file\nq: quit",
        title="Actions",
    )
    details = [f"[bold]{k}[/]: {v}" for k, v in files[selected_idx].items()]
    details_rows = Columns(details, equal=True, expand=False)
    details_panel = Panel(details_rows, title="Details", expand=False)
    files_panel = Panel(files_table, title="Files")
    action_layout = Layout(action_panel, ratio=1)
    files_layout = Layout(files_panel, ratio=4)
    details_layout = Layout(details_panel, ratio=2)
    display.split_row(action_layout, files_layout, details_layout)
    return display


def import_pdf_files(vault, import_dir_path):
    if not import_dir_path.exists():
        raise FileNotFoundError(f"Import directory not found: {import_dir_path}")
    pdf_dir_path = import_dir_path / "files"
    excel_path = import_dir_path / "details.xlsx"
    import_schema = {
        "Filename": str,
        "Type": str,
        "Authors": str,
        "Title": str,
        "Year": str,
        "Edition": str,
        "ISBN10": str,
        "ISBN13": str,
        "DOI": str,
        "Journal": str,
        "Volume": str,
        "PageRange": str,
        "Keywords": str,
        "Course": str,
    }
    df = pl.read_excel(
        excel_path, read_csv_options={"dtypes": import_schema, "missing_utf8_is_empty_string": True}
    )
    files_filenames = set(os.listdir(pdf_dir_path))
    details_filenames = set(df["Filename"].map_elements(lambda filename: f"{filename}.pdf"))
    missing_pdfs = files_filenames - details_filenames
    if missing_pdfs:
        console.print(f"Warning: Found {len(missing_pdfs)} missing pdf files", style="yellow")
        for idx, pdf_filename in enumerate(missing_pdfs):
            console.print(f"{idx:6}. {pdf_filename}")
    missing_details = details_filenames - files_filenames
    if missing_details:
        console.print(f"Warning: Found {len(missing_details)} missing details", style="yellow")
        for idx, pdf_filename in enumerate(missing_details):
            console.print(f"{idx:6}. {pdf_filename}")
    rows = df.rows(named=True)
    tot = len(rows)
    errors = {}
    for idx, record in enumerate(rows):
        filename = record["Filename"]
        try:
            if filename not in missing_pdfs:
                pdf_file_path = pdf_dir_path / f"{filename}.pdf"
                with Progress(
                    TextColumn(f"[green][{idx}/{tot}][/] [blue]Reading -[/] {filename[:40]}..."),
                    SpinnerColumn("line"),
                    console=console,
                    transient=True,
                    refresh_per_second=10,
                ) as progress:
                    progress.add_task("Reading")
                    pdf_file = pdf.PdfFile(vault, pdf_file_path)
                metadata_dict = {}
                for key in record:
                    if key not in ["Type", "Filename"]:
                        metadata_dict[f"/{key}"] = record[key]
                pdf_file.pdf_type = record["Type"]
                pdf_file.update_metadata(metadata_dict)
                pdf_file.write_file_index()
                pdf_file.write_page_index(
                    track_hashing=lambda x: track(
                        x,
                        f"[green][{idx}/{tot}][/] [blue]Hashing -[/] {filename[:40]}...",
                        transient=True,
                        console=console,
                    ),
                    track_indexing=lambda x: track(
                        x,
                        f"[green][{idx}/{tot}][/] [blue]Indexing -[/] {filename[:40]}...",
                        transient=True,
                        console=console,
                    ),
                )
                with Progress(
                    TextColumn(f"[green][{idx}/{tot}][/] [blue]Writing -[/] {filename[:40]}..."),
                    SpinnerColumn("line"),
                    console=console,
                    transient=True,
                    refresh_per_second=10,
                ) as progress:
                    progress.add_task("Writing")
                    pdf_file.write()
        except Exception as e:
            errors[filename] = e
    return tot, errors


def console_loop_search_panel(pages):
    length = len(pages)
    selected = 0
    page_len = 10
    page = 0
    page_count = math.floor(length / page_len)
    start = page * page_len
    end = (page + 1) * page_len
    with Live(
        search_panel(pages[start:end], selected, page, page_count),
        transient=True,
        auto_refresh=False,
    ) as live:
        while True:
            live.update(
                search_panel(pages[start:end], selected, page, page_count),
                refresh=True,
            )
            key = msvcrt.getch()
            match key:
                case b"q":
                    break
                case b"j":
                    if length:
                        selected = (selected + 1) % page_len
                case b"k":
                    if length:
                        selected = (selected - 1) % page_len
                case b"h":
                    if length:
                        page = (page - 1) % page_count
                        start = page * page_len
                        end = (page + 1) * page_len
                        selected = 0
                case b"l":
                    if length:
                        page = (page + 1) % page_count
                        start = page * page_len
                        end = (page + 1) * page_len
                        selected = 0
                case b"o":
                    if length:
                        browser = webbrowser.get()
                        url = pages[start:end][selected]["url"]
                        browser.open(url)
                case _:
                    continue


def console_loop_browse_panel(files, get_pdf_url):
    types = list(files.keys())
    t_len = len(types)
    t_idx = 0
    lens = {i: len(v) for i, v in enumerate(files.values())}
    idxs = {t: 0 for t in range(t_len)}
    if not files:
        console.print("No files found! Add PDF file using the `add` command.")
        return
    with Live(
        browse_panel(
            files[types[t_idx]],
            types[t_idx],
            idxs[t_idx],
        ),
        transient=True,
        auto_refresh=False,
    ) as live:
        while True:
            live.update(
                browse_panel(
                    files[types[t_idx]],
                    types[t_idx],
                    idxs[t_idx],
                ),
                refresh=True,
            )
            key = msvcrt.getch()
            match key:
                case b"q":
                    break
                case b"j":
                    if lens[t_idx]:
                        idxs[t_idx] = (idxs[t_idx] + 1) % lens[t_idx]
                case b"k":
                    if lens[t_idx]:
                        idxs[t_idx] = (idxs[t_idx] - 1) % lens[t_idx]
                case b"h":
                    if t_len:
                        t_idx = (t_idx - 1) % t_len
                case b"l":
                    if t_len:
                        t_idx = (t_idx + 1) % t_len
                case b"o":
                    if lens[t_idx]:
                        filename = files[types[t_idx]][idxs[t_idx]]["filename"]
                        browser = webbrowser.get()
                        url = get_pdf_url(types[t_idx], filename)
                        browser.open(url)
                case _:
                    continue
