from datetime import datetime
import hashlib
import pathlib
import re
from urllib.parse import quote

from rich.progress import track
import pypdf

from .vault import Vault

UTC_TIME = "+05'30"


class PdfFile:
    def __init__(self, vault: Vault, file_path: str):
        self.vault = vault
        self.file_path = pathlib.Path(file_path)
        self.reader = pypdf.PdfReader(file_path)
        self.writer = pypdf.PdfWriter(file_path)
        self.writer.clone_document_from_reader(self.reader)
        self.metadata = dict(self.reader.metadata)
        self.file_hash = hashlib.sha1(self.reader.pages[0].hash_value_data()).hexdigest()
        self.pdf_type = None

    def read_metadata(self) -> pypdf.PdfReader.metadata:
        return self.metadata

    def update_metadata(self, metadata: dict):
        time = datetime.now().strftime(f"D\072%Y%m%d%H%M%S{UTC_TIME}")
        metadata["/ModDate"] = time
        metadata["/Producer"] = "PDF Search"
        self.writer.add_metadata(metadata)
        self.metadata.update(metadata)

    def generate_filename(self):
        author_names_list = [
            [name for name in a.strip().split(" ") if not name.endswith(".")]
            for a in self.metadata["/Author"].split(",")
        ]
        authors_str = ", ".join([f"{names[0][0]}. {names[-1]}" for names in author_names_list])
        valid_title = re.sub(r"\*\?\\\\/", "", self.metadata["/Title"])
        valid_title = re.sub(r':<>\|"-', " ", valid_title)
        year = self.metadata["/Year"]
        edition = f"[{self.metadata['/Edition']}] " if "/Edition" in self.metadata else ""
        return f"{authors_str} - {valid_title} {edition}({year}).pdf"

    def write(self, file_path=None):
        if file_path is None:
            filename = self.generate_filename()
            file_path = self.vault.get_pdf_filepath(self.pdf_type, filename)
        self.writer.write(file_path)

    def write_page_index(self):
        pages = []
        for page in track(self.reader.pages, "Hashing"):
            page_key = page.hash_func(page.hash_value_data()).hexdigest()
            page_text = page.extract_text()
            file_path_encoded = quote(self.file_path.resolve().as_posix())
            page_url = f"file:///{file_path_encoded}#page={page.page_number + 1}"
            pages.append(
                {
                    "id": page_key,
                    "text": page_text,
                    "url": page_url,
                    "file_id": self.file_hash,
                    "page_number": page.page_number + 1,
                }
            )
        self.vault.write_multiple_page_index(pages)

    def write_file_index(self):
        pdf_file_name = self.generate_filename()
        fields = {
            "id": self.file_hash,
            "type": self.pdf_type,
            "title": self.metadata["/Title"],
            "authors": self.metadata["/Author"],
            "year": self.metadata["/Year"],
            "doi": self.metadata["/DOI"],
            "edition": self.metadata["/Edition"] if "/Edition" in self.metadata else "",
            "isbn10": self.metadata["/ISBN10"].replace("-", "")
            if "/ISBN10" in self.metadata
            else "",
            "isbn13": self.metadata["/ISBN13"].replace("-", "")
            if "/ISBN13" in self.metadata
            else "",
            "filename": pdf_file_name,
        }
        self.vault.write_file_index(fields)

    def remove_file_index(self):
        self.vault.remove_file_index(self.file_hash)
