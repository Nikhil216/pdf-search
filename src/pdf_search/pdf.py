from datetime import datetime
import hashlib
import pathlib
import re

from doctr.io import DocumentFile
from doctr.models import ocr_predictor
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
        self.file_hash = hashlib.sha1(
            b"".join(map(lambda x: x.encode(), self.reader.page_labels))
        ).hexdigest()
        self.pdf_type = None
        self.ocr_model = ocr_predictor(pretrained=True)

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
            for a in self.metadata["/Authors"].split(",")
        ]
        authors_str = ", ".join(
            [
                f"{(names[0][0] if names[0] else '') if names else ''}. {names[-1] if names else ''}"
                for names in author_names_list
            ]
        )
        authors_str = f"{authors_str} - " if authors_str else ""
        valid_title = re.sub(r"[\*\?\\\\/]", "", self.metadata["/Title"])
        valid_title = re.sub(r'[:<>\|"-]', " ", valid_title)
        edition = f"[{self.metadata['/Edition']}] " if self.metadata.get("/Edition", "") else ""
        year = f"({self.metadata['/Year']})" if self.metadata.get("/Year", "") else ""
        return f"{authors_str}{valid_title} {edition}{year}.pdf"

    def write(self, file_path=None):
        if file_path is None:
            filename = self.generate_filename()
            file_path = self.vault.get_pdf_filepath(self.pdf_type, filename)
        self.writer.write(file_path)

    def write_page_index(self, track_hashing=lambda x: x, track_indexing=lambda x: x):
        pages = []
        errors = {}
        for page in track_hashing(self.reader.pages):
            page_text = page.extract_text()
            ## OCR predictions of images
            image_text = ''
            try:
                if page.images:
                    image_files = page.images
                    image_bytes = [img.data for img in image_files]
                    image_doc = DocumentFile.from_images(image_bytes)
                    model_result = self.ocr_model(image_doc)
                    image_text = model_result.render()
            except Exception as e:
                errors[page.page_number] = e
            page_text = "\n".join([page_text, image_text])
            page_key = page.hash_func(page_text.encode()).hexdigest()
            pages.append(
                {
                    "id": page_key,
                    "text": page_text,
                    "file_id": self.file_hash,
                    "filename": self.generate_filename(),
                    "pdf_type": self.pdf_type,
                    "page_number": page.page_number + 1,
                }
            )
        self.vault.write_multiple_page_index(pages, track_indexing)
        return errors

    def write_file_index(self):
        pdf_file_name = self.generate_filename()
        fields = {
            "id": self.file_hash,
            "type": self.pdf_type,
            "title": self.metadata["/Title"],
            "authors": self.metadata["/Authors"],
            "year": self.metadata["/Year"],
            "doi": self.metadata["/DOI"] if self.metadata.get("/DOI", "") else "",
            "edition": self.metadata["/Edition"] if self.metadata.get("/Edition", "") else "",
            "isbn10": self.metadata["/ISBN10"].replace("-", "")
            if self.metadata.get("/ISNB10", "")
            else "",
            "isbn13": self.metadata["/ISBN13"].replace("-", "")
            if self.metadata.get("/ISNB13", "")
            else "",
            "journal": self.metadata["/Journal"] if self.metadata.get("/Journal", "") else "",
            "volume": self.metadata["/Volume"] if self.metadata.get("/Volume", "") else "",
            "pages": self.metadata["/Pages"] if self.metadata.get("/Pages", "") else "",
            "filename": pdf_file_name,
        }
        self.vault.write_file_index(fields)

    def remove_file_index(self):
        return self.vault.remove_file_index(self.file_hash)
