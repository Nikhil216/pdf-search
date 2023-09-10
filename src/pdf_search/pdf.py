import hashlib
import pathlib
import re
from urllib.parse import quote

import pypdf
from whoosh import index as whoosh_index


class PdfFile:
    def __init__(self, file_path: str):
        self.file_path = pathlib.Path(file_path)
        self.reader = pypdf.PdfReader(file_path)
        self.writer = pypdf.PdfWriter(file_path)
        self.writer.clone_document_from_reader(self.reader)
        self.metadata = dict(self.reader.metadata)
        self.file_hash = hashlib.sha1(self.reader.pages[0].hash_value_data()).hexdigest()

    def read_metadata(self) -> pypdf.PdfReader.metadata:
        return self.metadata

    def update_metadata(self, metadata: dict):
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

    def write(self, file_path):
        if file_path is None:
            file_path = self.generate_filename()
        self.writer.write(file_path)

    def write_index(self, file_path: pathlib.Path, index_path: pathlib.Path, progress_track):
        index = whoosh_index.open_dir(index_path, "pages")
        index_writer = index.writer()
        for page in progress_track(self.reader.pages):
            page_key = page.hash_func(page.hash_value_data()).hexdigest()
            page_text = page.extract_text()
            file_path_encoded = quote(file_path.resolve().as_posix())
            page_url = f"file:///{file_path_encoded}#page={page.page_number}"
            # import pdb
            # pdb.set_trace()
            index_writer.add_document(
                key=page_key,
                text=page_text,
                url=page_url
            )
        index_writer.commit()
        index.close()