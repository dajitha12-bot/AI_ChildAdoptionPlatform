import logging
import certifi
from pymongo import MongoClient
from pymongo.errors import ConnectionFailure, ServerSelectionTimeoutError
import mongomock
from config import Config

logger = logging.getLogger(__name__)

_client = None
_db = None
_is_seeding = False

def _auto_seed_if_empty(database):
    """Auto-seeds demo accounts and agency directory if users collection is empty."""
    global _is_seeding
    if _is_seeding:
        return
    try:
        if database.users.count_documents({}) == 0:
            _is_seeding = True
            logger.info("Database users collection is empty. Auto-seeding demo accounts and agencies dataset...")
            from seed.seed_data import seed
            seed()
    except Exception as e:
        logger.warning(f"Auto-seed check note: {e}")
    finally:
        _is_seeding = False

def init_db(app=None):
    global _client, _db
    if _db is not None:
        return _db

    try:
        # Try real MongoDB Atlas connection with certifi CA bundle for SSL compatibility
        client_kwargs = {
            'serverSelectionTimeoutMS': 3000
        }
        try:
            import certifi
            client_kwargs['tlsCAFile'] = certifi.where()
        except Exception as ssl_err:
            logger.warning(f"Certifi CA bundle note: {ssl_err}")

        client = MongoClient(Config.MONGO_URI, **client_kwargs)
        client.admin.command('ping')
        _client = client
        _db = client[Config.MONGO_DB_NAME]
        logger.info(f"Connected to real MongoDB Atlas database: {Config.MONGO_DB_NAME}")
    except (ConnectionFailure, ServerSelectionTimeoutError, Exception) as e:
        logger.warning(f"Could not connect to MongoDB Atlas instance ({e}). Falling back to MongoMock in-memory database.")
        _client = mongomock.MongoClient()
        _db = _client[Config.MONGO_DB_NAME]

    _auto_seed_if_empty(_db)
    return _db

def get_db():
    global _db
    if _db is None:
        init_db()
    return _db

class DatabaseProxy:
    """Proxy object allowing module-level attribute access like `db.users.find()`."""
    def __getattr__(self, name):
        database = get_db()
        return getattr(database, name)

    def __getitem__(self, name):
        database = get_db()
        return database[name]

db = DatabaseProxy()
