from datetime import datetime
import hashlib
import pathlib
import re
import json

from doctr.io import DocumentFile
from doctr.models import ocr_predictor
import fitz
import fitz.utils

from .vault import Vault

UTC_TIME = "+05'30"


class PdfFile:
    ocr_model = ocr_predictor(pretrained=True)

    def __init__(self, vault: Vault, file_path: str):
        self.vault = vault
        self.file_path = pathlib.Path(file_path)
        self.document = fitz.open(file_path)
        self.metadata = self.read_metadata()
        self.file_hash = hashlib.sha1(self.document.tobytes()).hexdigest()
        self.pdf_type = None

    def read_metadata(self) -> dict[str, str]:
        metadata = self.document.metadata
        try:
            metadata.update(json.loads(metadata["subject"]))
        except json.decoder.JSONDecodeError or KeyError:
            pass
        return metadata

    def update_metadata(self, metadata: dict):
        time = datetime.now().strftime(f"D:%Y%m%d%H%M%S{UTC_TIME}")
        metadata["modDate"] = time
        metadata["producer"] = "PDF Search"
        allowed_metadata_keys = [
            "author",
            "producer",
            "creator",
            "title",
            "format",
            "encryption",
            "creationDate",
            "modDate",
            "subject",
            "keywords",
            "trapped",
        ]
        not_allowed_metadata = {k: v for k, v in metadata.items() if k not in allowed_metadata_keys}
        allowed_metadata = {k: v for k, v in metadata.items() if k in allowed_metadata_keys}
        allowed_metadata["subject"] = json.dumps(not_allowed_metadata)
        self.document.set_metadata(allowed_metadata)
        self.metadata.update(metadata)

    def generate_filename(self):
        author_names_list = [
            [name for name in a.strip().split(" ") if not name.endswith(".")]
            for a in self.metadata["author"].split(",")
        ]
        authors_str = ", ".join(
            [
                f"{(names[0][0] if names[0] else '') if names else ''}. {names[-1] if names else ''}"
                for names in author_names_list
            ]
        )
        authors_str = f"{authors_str} - " if authors_str else ""
        valid_title = re.sub(r"[\*\?\\\\/]", "", self.metadata["title"])
        valid_title = re.sub(r'[:<>\|"-]', " ", valid_title)
        edition = f"[{self.metadata['edition']}] " if self.metadata.get("edition", "") else ""
        year = f"({self.metadata['year']})" if self.metadata.get("year", "") else ""
        return f"{authors_str}{valid_title} {edition}{year}.pdf"

    def write(self, file_path=None):
        if file_path is None:
            filename = self.generate_filename()
            file_path = self.vault.get_pdf_filepath(self.pdf_type, filename)
        self.document.save(file_path)

    def write_page_index(self, track_hashing=lambda x: x, track_indexing=lambda x: x):
        pages = []
        errors = {}
        for page in track_hashing(self.document.pages()):
            page_text = page.get_text()
            page_images = page.get_images()
            ## OCR predictions of images
            image_text = ""
            try:
                if page_images:
                    image_bytes = []
                    for xref, *_ in page_images:
                        pix = fitz.Pixmap(self.document, xref)
                        image_bytes.append(pix.pil_tobytes(format="PNG"))
                    image_doc = DocumentFile.from_images(image_bytes)
                    model_result = self.ocr_model(image_doc)
                    image_text = model_result.render()
            except Exception as e:
                errors[page.number] = e
            page_text = "\n".join([page_text, image_text])
            page_key = hashlib.sha1(page_text.encode()).hexdigest()
            pages.append(
                {
                    "id": page_key,
                    "text": page_text,
                    "file_id": self.file_hash,
                    "filename": self.generate_filename(),
                    "pdf_type": self.pdf_type,
                    "page_number": page.number + 1,
                    "authors": self.metadata["author"],
                }
            )
        self.vault.write_multiple_page_index(pages, track_indexing)
        return errors

    def write_file_index(self):
        pdf_file_name = self.generate_filename()
        fields = {
            "id": self.file_hash,
            "type": self.pdf_type,
            "title": self.metadata["title"],
            "authors": self.metadata["author"],
            "year": self.metadata["year"],
            "doi": self.metadata["DOI"] if self.metadata.get("DOI", "") else "",
            "edition": self.metadata["edition"] if self.metadata.get("edition", "") else "",
            "isbn10": (
                self.metadata["ISBN10"].replace("-", "") if self.metadata.get("ISNB10", "") else ""
            ),
            "isbn13": (
                self.metadata["ISBN13"].replace("-", "") if self.metadata.get("ISNB13", "") else ""
            ),
            "journal": self.metadata["journal"] if self.metadata.get("journal", "") else "",
            "volume": self.metadata["volume"] if self.metadata.get("volume", "") else "",
            "pages": self.metadata["pages"] if self.metadata.get("pages", "") else "",
            "filename": pdf_file_name,
        }
        self.vault.write_file_index(fields)

    def remove_file_index(self):
        return self.vault.remove_file_index(self.file_hash)
