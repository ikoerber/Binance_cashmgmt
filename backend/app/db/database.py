"""Database connection and session management"""
from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

# Base class für alle Models
Base = declarative_base()

# Engine wird später initialisiert
engine = None
SessionLocal = None


def init_db(database_url: str):
    """
    Initialisiert Database Engine und Session

    Args:
        database_url: SQLAlchemy Database URL
                      z.B. "sqlite:///./cashmgnt.db"
    """
    global engine, SessionLocal

    engine = create_engine(
        database_url,
        # SQLite-spezifisch: Foreign Keys aktivieren
        connect_args={"check_same_thread": False} if database_url.startswith("sqlite") else {},
        echo=False  # Set True für SQL-Debugging
    )

    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db():
    """
    Dependency für FastAPI: Liefert DB Session

    Verwendung:
        @app.get("/endpoint")
        def endpoint(db: Session = Depends(get_db)):
            ...
    """
    if SessionLocal is None:
        raise RuntimeError("Database not initialized. Call init_db() first.")

    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def create_tables():
    """Erstellt alle Tabellen (für Development/Tests)"""
    if engine is None:
        raise RuntimeError("Database not initialized. Call init_db() first.")

    Base.metadata.create_all(bind=engine)
