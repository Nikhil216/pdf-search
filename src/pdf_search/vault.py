import pathlib
import shutil
from urllib.parse import quote

from rich.progress import track
from whoosh import fields as f
from whoosh.analysis import StemmingAnalyzer
from whoosh.qparser import QueryParser
from whoosh import index

from .console import console


class Vault:
    def __init__(self, vault_path: str | pathlib.Path):
        self.vault_path = pathlib.Path(vault_path)
        self.status_ok = self.check_vault_status()
        if self.status_ok:
            index_path = self.vault_path / "index"
            self.file_index = index.open_dir(index_path, "files")
            self.page_index = index.open_dir(index_path, "pages")

    def check_vault_status(self) -> bool:
        if not self.vault_path.exists() or not self.vault_path.is_dir():
            console.print("Error: The vault directory does not exists", style="bold red")
            return False
        books_path = self.vault_path / "books"
        papers_path = self.vault_path / "papers"
        index_path = self.vault_path / "index"
        created = []
        if not index_path.exists() or not index_path.is_dir():
            index_path.mkdir()
            pages_schema = f.Schema(
                id=f.ID(stored=True, unique=True),
                text=f.TEXT(analyzer=StemmingAnalyzer()),
                url=f.STORED,
                page_number=f.NUMERIC(stored=True),
                file_id=f.ID(stored=True),
            )
            files_schema = f.Schema(
                id=f.ID(stored=True, unique=True),
                type=f.ID(stored=True),
                title=f.TEXT(stored=True, analyzer=StemmingAnalyzer()),
                authors=f.IDLIST(stored=True),
                year=f.ID(stored=True),
                doi=f.ID(stored=True),
                edition=f.STORED,
                isbn10=f.ID(stored=True, unique=True),
                isbn13=f.ID(stored=True, unique=True),
                filename=f.ID(stored=True),
            )
            index.create_in(index_path, pages_schema, "pages")
            index.create_in(index_path, files_schema, "files")
            created.append("index")
        if not books_path.exists() or not books_path.is_dir():
            books_path.mkdir()
            created.append("books")
        if not papers_path.exists() or not papers_path.is_dir():
            papers_path.mkdir()
            created.append("papers")
        ## TODO: Check for missing pdf files
        if created:
            console.print(f'Created {", ".join(created)}')
        return True

    def write_file_index(self, fields):
        field_names = self.file_index.schema.names()
        invalid_field_names = [name for name in fields.keys() if name not in field_names]
        if invalid_field_names:
            raise ValueError(f"Invalid fields: {', '.join(invalid_field_names)}")
        if self.status_ok:
            file_writer = self.file_index.writer()
            file_writer.add_document(**fields)
            file_writer.commit()

    def write_multiple_page_index(self, pages):
        if self.status_ok:
            page_writer = self.page_index.writer()
            for page_fields in track(pages, "Indexing"):
                page_writer.add_document(**page_fields)
            page_writer.commit()

    def write_page_index(self, page_id, text, url):
        if self.status_ok:
            page_writer = self.page_index.writer()
            page_writer.add_document(id=page_id, text=text, url=url)
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

    def remove_file_index(self, file_id):
        if self.status_ok:
            page_writer = self.page_index.writer()
            page_writer.delete_by_term("file_id", file_id)
            page_writer.commit()
            file_writer = self.file_index.writer()
            file_writer.delete_by_term("id", file_id)
            file_writer.commit()

    def search_pages(self, search_query_str, limit=10):
        if self.status_ok:
            page_text_query = QueryParser("text", self.page_index.schema).parse(search_query_str)
            results = []
            with self.page_index.searcher() as s:
                pages = s.search(page_text_query, limit=limit)
                for page in pages:
                    results.append(
                        {
                            "url": page["url"],
                            "page_number": page["page_number"],
                            "file_id": page["file_id"],
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

    def search_files(self, query_str, limit=10):
        if self.status_ok:
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

    def list_all_files(self):
        if self.status_ok:
            file_title_query = QueryParser("type", self.file_index.schema).parse("books OR papers")
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
        shutil.rmtree(self.vault_path / "books")
        shutil.rmtree(self.vault_path / "papers")
        shutil.rmtree(self.vault_path / "index")