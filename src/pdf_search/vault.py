import pathlib
import shutil
from urllib.parse import quote

from whoosh import fields as f
from whoosh.analysis import StandardAnalyzer
from whoosh.qparser import QueryParser
from whoosh.query import Every
from whoosh import index

from .console import console

PDF_TYPES = ["books", "papers", "thesis", "docs"]


def check_status_ok(method):
    def modified_method(self, *args, **kwargs):
        if not self.status_ok:
            raise Exception("Vault has failed to load! Run the method `load_vault`.")
        return method(self, *args, **kwargs)

    return modified_method


class Vault:
    def __init__(self, vault_path: str | pathlib.Path):
        self.vault_path = pathlib.Path(vault_path)
        self.file_index = None
        self.page_index = None
        self.load_vault()

    def check_vault_status(self) -> bool:
        if not self.vault_path.exists() or not self.vault_path.is_dir():
            console.print("Error: The vault directory does not exists", style="bold red")
            return False
        index_path = self.vault_path / "index"
        created = []
        if not index_path.exists() or not index_path.is_dir():
            index_path.mkdir()
            pages_schema = f.Schema(
                id=f.ID(stored=True, unique=True),
                text=f.TEXT(analyzer=StandardAnalyzer()),
                filename=f.STORED,
                pdf_type=f.STORED,
                page_number=f.NUMERIC(stored=True),
                file_id=f.ID(stored=True),
            )
            files_schema = f.Schema(
                id=f.ID(stored=True, unique=True),
                type=f.ID(stored=True),
                title=f.TEXT(stored=True, analyzer=StandardAnalyzer()),
                authors=f.IDLIST(stored=True),
                year=f.ID(stored=True),
                doi=f.ID(stored=True),
                edition=f.STORED,
                isbn10=f.ID(stored=True),
                isbn13=f.ID(stored=True),
                journal=f.ID(stored=True),
                volume=f.ID(stored=True),
                pages=f.ID(stored=True),
                keywords=f.KEYWORD(stored=True, commas=True),
                filename=f.ID(stored=True),
            )
            index.create_in(index_path, pages_schema, "pages")
            index.create_in(index_path, files_schema, "files")
            created.append("index")
        for pdf_type in PDF_TYPES:
            type_path = self.vault_path / pdf_type
            if not type_path.exists() or not type_path.is_dir():
                type_path.mkdir()
                created.append(pdf_type)
        ## TODO: Check for missing pdf files
        if created:
            console.print(f'Created {", ".join(created)}')
        return True

    def load_vault(self):
        self.status_ok = self.check_vault_status()
        if not self.status_ok:
            raise Exception("Failed to load the vault!")
        index_path = self.vault_path / "index"
        if not self.file_index:
            self.file_index = index.open_dir(index_path, "files")
        if not self.page_index:
            self.page_index = index.open_dir(index_path, "pages")

    @check_status_ok
    def write_file_index(self, fields):
        field_names = self.file_index.schema.names()
        invalid_field_names = [name for name in fields.keys() if name not in field_names]
        if invalid_field_names:
            raise ValueError(f"Invalid fields: {', '.join(invalid_field_names)}")
        file_writer = self.file_index.writer()
        file_writer.add_document(**fields)
        file_writer.commit()

    @check_status_ok
    def write_multiple_page_index(self, pages, track=lambda x: x):
        page_writer = self.page_index.writer()
        for page_fields in track(pages):
            page_writer.add_document(**page_fields)
        page_writer.commit()

    @check_status_ok
    def write_page_index(self, page_id, text, pdf_type, filename):
        page_writer = self.page_index.writer()
        page_writer.add_document(id=page_id, text=text, filename=filename, pdf_type=pdf_type)
        page_writer.commit()

    def get_pdf_url(self, pdf_type, filename) -> str:
        file_path = self.get_pdf_filepath(pdf_type, filename)
        file_path_encoded = quote(file_path.resolve().as_posix())
        file_url = f"file:///{file_path_encoded}"
        return file_url

    def get_pdf_filepath(self, pdf_type, filename) -> pathlib.Path:
        if pdf_type is None:
            raise ValueError("pdf_type cannot be None")
        return self.vault_path / pdf_type / filename

    @check_status_ok
    def remove_file_index(self, file_id):
        page_writer = self.page_index.writer()
        pages_deleted = page_writer.delete_by_term("file_id", file_id)
        page_writer.commit()
        file_writer = self.file_index.writer()
        files_deleted = file_writer.delete_by_term("id", file_id)
        file_writer.commit()
        return files_deleted, pages_deleted

    @check_status_ok
    def search_pages(self, search_query_str, limit=10):
        page_text_query = QueryParser("text", self.page_index.schema).parse(search_query_str)
        results = []
        with self.page_index.searcher() as s:
            pages = s.search(page_text_query, limit=limit)
            for page in pages:
                results.append(
                    {
                        "file_id": page["file_id"],
                        "filename": page["filename"],
                        "pdf_type": page["pdf_type"],
                        "page_number": page["page_number"],
                    }
                )
        file_query_str = " OR ".join(set([page["file_id"] for page in results]))
        file_title_query = QueryParser("id", self.file_index.schema).parse(file_query_str)
        file_map = {}
        with self.file_index.searcher() as s:
            files = s.search(file_title_query)
            for file in files:
                file_map[file["id"]] = {
                    "filename": file["filename"],
                    "pdf_type": file["type"],
                }
        for page in results:
            page["filename"] = file_map[page["file_id"]]["filename"]
            page["pdf_type"] = file_map[page["file_id"]]["pdf_type"]
        return results

    @check_status_ok
    def search_files(self, query_str, limit=10):
        file_title_query = QueryParser("title", self.file_index.schema).parse(query_str)
        results = {}
        with self.file_index.searcher() as s:
            files = s.search(file_title_query, limit=limit)
            for file in files:
                pdf_type = file["type"]
                if pdf_type not in results:
                    results[pdf_type] = []
                results[pdf_type].append(dict(file))
        return results

    @check_status_ok
    def list_all_files(self):
        file_title_query = Every()
        results = {}
        with self.file_index.searcher() as s:
            files = s.search(file_title_query)
            for file in files:
                pdf_type = file["type"]
                if pdf_type not in results:
                    results[pdf_type] = []
                results[pdf_type].append(dict(file))
        return results

    def nuke(self):
        shutil.rmtree(self.vault_path / "index")
        for pdf_type in PDF_TYPES:
            shutil.rmtree(self.vault_path / pdf_type)
