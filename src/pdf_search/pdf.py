import pathlib

import pypdf

def read_metadata(path: pathlib.Path) -> dict:
    reader = pypdf.PdfReader(path)
    return reader.metadata