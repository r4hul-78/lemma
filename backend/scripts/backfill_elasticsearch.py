import os
import sys
import logging

# Ensure backend folder is in Python path for imports
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from backend.app.services.database import DatabaseService
from backend.app.services.elasticsearch_client import initialize_es, index_sentence_bulk

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger("backfill_migration")

def backfill():
    logger.info("Starting Elasticsearch backfill migration...")
    
    # Automatically seed database if empty
    from backend.app.services.matcher import seed_database
    seed_database()
    
    # 1. Initialize Elasticsearch Index
    try:
        initialize_es()
    except Exception as e:
        logger.error(f"Failed to initialize Elasticsearch index: {e}")
        sys.exit(1)
        
    # 2. Retrieve records from PostgreSQL
    try:
        with DatabaseService.get_connection() as conn:
            from psycopg2.extras import RealDictCursor
            with conn.cursor(cursor_factory=RealDictCursor) as cursor:
                logger.info("Reading sentences from PostgreSQL...")
                cursor.execute("""
                    SELECT document_id, sentence_index, text 
                    FROM sentences 
                    ORDER BY document_id, sentence_index;
                """)
                sentences = cursor.fetchall()
    except Exception as e:
        logger.error(f"Failed to read sentences from PostgreSQL: {e}")
        sys.exit(1)
        
    total_count = len(sentences)
    logger.info(f"Retrieved {total_count} sentences from database.")
    
    if total_count == 0:
        logger.info("No sentences found in PostgreSQL. Nothing to backfill.")
        return
        
    # 3. Bulk index to Elasticsearch
    try:
        # Convert RealDictCursor rows to clean dicts
        sentences_list = [dict(s) for s in sentences]
        index_sentence_bulk(sentences_list)
        logger.info(f"Elasticsearch backfill complete. Successfully indexed {total_count} sentences.")
    except Exception as e:
        logger.error(f"Failed to backfill sentences into Elasticsearch: {e}")
        sys.exit(1)

if __name__ == "__main__":
    backfill()
