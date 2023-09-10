import pathlib

from whoosh import fields as f
from whoosh.analysis import StemmingAnalyzer
from whoosh import index as whoosh_index


def check_vault_status(vault_path: pathlib.Path):
    if not vault_path.exists() or not vault_path.is_dir():
        return ("Error", "The vault directory does not exists")
    books_path = vault_path / "books"
    papers_path = vault_path / "papers"
    index_path = vault_path / "index"
    db_path = vault_path / "vault.db"
    created = []
    if not db_path.exists():
        db_path.touch()
        created.append("database")
    if not index_path.exists() or not index_path.is_dir():
        index_path.mkdir()
        schema = f.Schema(
            key=f.ID(stored=True), text=f.TEXT(analyzer=StemmingAnalyzer()), url=f.STORED
        )
        whoosh_index.create_in(index_path, schema, "pages")
        created.append("index")
    if not books_path.exists() or not books_path.is_dir():
        books_path.mkdir()
        created.append("books")
    if not papers_path.exists() or not papers_path.is_dir():
        papers_path.mkdir()
        created.append("papers")
    ## TODO: Check for missing files
    return ("Ok", f'Created {", ".join(created)}' if created else "")