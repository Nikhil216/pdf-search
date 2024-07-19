## Introduction

A console application to search through a folder of pdf files using keyword search.

PDF files can be added and its pages can be search by keywords. It also allows for files to be browsed all at once. There is provision to classify each file into one of the types: books, papers, docs and thesis.

## Running the console

Install this package, preferably in a virtual environment and run the command

```pwsh
python -m pdf_search interactive
```

This will start a console and connect to the vault in the current directory. If a vault does not exists in the current directory then it will create one. The commands presented by the console can be lookedup by typing help in the console.

```
Commands:
    help                List all the commands available
    quit                Quit the console
    add <file>          Add the pdf file into the vault
    remove <file>       Remove the pdf file from the vault
                        The file path must be the relative path from the vault
    search <query>      Search the vault for matching files
    nuke                Delete all files and index inside the vault
    browse              Browse through the files in the vault
```

To add and remove pdf files from the vault, use the commands `add` and `remove` respectively. To list all pdf files, type `browse` command. `search` command accepts keywords which will search through all the pdf pages and return relevant pages.

## Vault

All the added files will be copied inside of the folder named vault. The vault divides the files into severl types namely, books, papers, docs and thesis. The file type should be provided by the user while adding the pdf file. The vault also contains the index of all the pages inside of the index folder. Index helps in searching text from the pages. You can move the vault folder around without affecting its working.

## Search Query

The search query accepts keywords seperated by space. It is like searching through an reverse index. When multiple keywords are present it will try to search for text in pages with all the keywords present. It does not support fuzzy matching yet so it won't correct for errors. To search text within a specific file name use `file:<keyword>` and it will search for pages in files with `<keyword>` present in the title. You can also use the `author` and `type` modifier in this way.

## Import

All the files from a provided directory can be imported at once if provided with the appropriate directory structure.

```
import_directory
|-- files
|   |-- a.pdf
|   |-- b.pdf
|-- details.xlxs
```

There should be a directory named `files` right inside of `import_directory` and a spreadsheet named `details.xlxs`. The spreadsheet should have the following columns in the order: filename, type, author, title, year, edition, ISBN10, ISBN13, DOI, journal, volume, pageRange, keywords. The `filename` should have just be the filename and not the path and it should be present in the `files` directory. Once the import is completed a log file will be generated in the `import_directory` named `import_log.txt`.


## Dev Setup for windows

You need to install the following dependencies

```
"polars == 0.19.2",
"whoosh == 2.7.4",
"rich >= 13.5, < 14",
"pymupdf == 1.23.25",
"xlsx2csv >= 0.8, < 1",
"python-doctr >= 0.7.0, < 1",
"torch >= 2.0.0, < 3",
"torchvision >= 0.15.2, < 1",
"pycryptodome == 3.19.0",
"pegen == 0.3.0",
```

Install [GTK3](https://github.com/tschoonj/GTK-for-Windows-Runtime-Environment-Installer/releases) for weezeyprint to work