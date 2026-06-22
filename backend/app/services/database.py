import psycopg2
from psycopg2.extras import RealDictCursor, execute_values
from backend.app.config import settings

class DatabaseService:
    """Manages PostgreSQL database connections, table creation, and metadata queries."""
    
    @staticmethod
    def get_connection():
        """Returns a connection to the PostgreSQL database."""
        conn = psycopg2.connect(
            host=settings.POSTGRES_HOST,
            port=settings.POSTGRES_PORT,
            database=settings.POSTGRES_DB,
            user=settings.POSTGRES_USER,
            password=settings.POSTGRES_PASSWORD
        )
        return conn

    @classmethod
    def initialize_db(cls):
        """Creates the PostgreSQL tables and extensions if they do not already exist."""
        with cls.get_connection() as conn:
            with conn.cursor() as cursor:
                # Enable pgvector extension
                cursor.execute("CREATE EXTENSION IF NOT EXISTS vector;")
                
                # Create documents table
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS documents (
                        id VARCHAR(255) PRIMARY KEY,
                        title TEXT NOT NULL,
                        author TEXT,
                        source TEXT
                    );
                """)
                
                # Create sentences table
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS sentences (
                        id SERIAL PRIMARY KEY,
                        document_id VARCHAR(255) NOT NULL,
                        sentence_index INT NOT NULL,
                        text TEXT NOT NULL,
                        embedding vector(384),
                        FOREIGN KEY(document_id) REFERENCES documents(id) ON DELETE CASCADE
                    );
                """)
                
                # Create HNSW index on the vector embedding column for fast cosine distance search
                cursor.execute("""
                    CREATE INDEX IF NOT EXISTS sentences_embedding_hnsw_idx 
                    ON sentences USING hnsw (embedding vector_cosine_ops);
                """)
            conn.commit()

    @classmethod
    def clear_db(cls):
        """Clears all records from the tables (useful for tests)."""
        with cls.get_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute("TRUNCATE TABLE sentences, documents CASCADE;")
            conn.commit()

    @classmethod
    def get_sentence_count(cls) -> int:
        """Returns the total number of sentences in the database."""
        with cls.get_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute("SELECT COUNT(*) FROM sentences;")
                return cursor.fetchone()[0]

    @classmethod
    def insert_reference_document(cls, doc_id: str, title: str, author: str, source: str) -> None:
        """Inserts a document metadata record into the database."""
        with cls.get_connection() as conn:
            with conn.cursor() as cursor:
                query = """
                    INSERT INTO documents (id, title, author, source) 
                    VALUES (%s, %s, %s, %s)
                    ON CONFLICT (id) DO UPDATE 
                    SET title = EXCLUDED.title, 
                        author = EXCLUDED.author, 
                        source = EXCLUDED.source;
                """
                cursor.execute(query, (doc_id, title, author, source))
            conn.commit()

    @classmethod
    def insert_reference_sentences(cls, sentences: list[dict]) -> None:
        """
        Bulk inserts sentences into the database.
        Each dict in the sentences list must contain:
        {
            "document_id": str,
            "sentence_index": int,
            "text": str,
            "embedding": list[float]
        }
        """
        with cls.get_connection() as conn:
            with conn.cursor() as cursor:
                data = [
                    (
                        s["document_id"],
                        s["sentence_index"],
                        s["text"],
                        f"[{','.join(map(str, s['embedding']))}]" if s.get("embedding") is not None else None
                    )
                    for s in sentences
                ]
                query = """
                    INSERT INTO sentences (document_id, sentence_index, text, embedding)
                    VALUES %s
                    ON CONFLICT DO NOTHING;
                """
                execute_values(cursor, query, data)
            conn.commit()

    @classmethod
    def get_sentence_by_faiss_id(cls, sentence_id: int) -> dict | None:
        """Retrieves a sentence and its associated document metadata by its primary key ID (retains backward compatibility)."""
        with cls.get_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cursor:
                cursor.execute("""
                    SELECT s.text AS sentence_text, s.document_id, d.title, d.author, d.source
                    FROM sentences s
                    JOIN documents d ON s.document_id = d.id
                    WHERE s.id = %s;
                """, (sentence_id,))
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
