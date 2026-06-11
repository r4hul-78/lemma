import sqlite3
from backend.app.config import settings

class DatabaseService:
    """Manages SQLite database connections, table creation, and metadata queries."""
    
    @staticmethod
    def get_connection():
        """Returns a connection to the SQLite database with foreign keys enabled."""
        conn = sqlite3.connect(settings.SQLITE_DB_PATH)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON;")
        return conn

    @classmethod
    def initialize_db(cls):
        """Creates the SQLite tables if they do not already exist."""
        with cls.get_connection() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS documents (
                    id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    author TEXT,
                    source TEXT
                );
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS sentences (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    faiss_id INTEGER UNIQUE NOT NULL,
                    document_id TEXT NOT NULL,
                    text TEXT NOT NULL,
                    FOREIGN KEY(document_id) REFERENCES documents(id) ON DELETE CASCADE
                );
            """)
            conn.commit()

    @classmethod
    def clear_db(cls):
        """Clears all records from the tables (useful for tests)."""
        with cls.get_connection() as conn:
            conn.execute("DELETE FROM sentences;")
            conn.execute("DELETE FROM documents;")
            conn.commit()

    @classmethod
    def get_sentence_count(cls) -> int:
        """Returns the total number of sentences in the database."""
        with cls.get_connection() as conn:
            cursor = conn.execute("SELECT COUNT(*) FROM sentences;")
            return cursor.fetchone()[0]

    @classmethod
    def insert_reference_document(cls, doc_id: str, title: str, author: str, source: str) -> None:
        """Inserts a document metadata record into the database."""
        with cls.get_connection() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO documents (id, title, author, source) VALUES (?, ?, ?, ?);",
                (doc_id, title, author, source)
            )
            conn.commit()

    @classmethod
    def insert_reference_sentences(cls, sentences: list[dict]) -> None:
        """
        Bulk inserts sentences into the database.
        Each dict in the sentences list must contain:
        {
            "faiss_id": int,
            "document_id": str,
            "text": str
        }
        """
        with cls.get_connection() as conn:
            conn.executemany(
                "INSERT OR REPLACE INTO sentences (faiss_id, document_id, text) VALUES (?, ?, ?);",
                [(s["faiss_id"], s["document_id"], s["text"]) for s in sentences]
            )
            conn.commit()

    @classmethod
    def get_sentence_by_faiss_id(cls, faiss_id: int) -> dict | None:
        """Retrieves a sentence and its associated document metadata by its FAISS index ID."""
        with cls.get_connection() as conn:
            cursor = conn.execute("""
                SELECT s.text AS sentence_text, s.document_id, d.title, d.author, d.source
                FROM sentences s
                JOIN documents d ON s.document_id = d.id
                WHERE s.faiss_id = ?;
            """, (faiss_id,))
            row = cursor.fetchone()
            if row:
                return {
                    "text": row["sentence_text"],
                    "doc_id": row["document_id"],
                    "doc_title": row["title"],
                    "doc_author": row["author"],
                    "doc_source": row["source"]
                }
            return None
