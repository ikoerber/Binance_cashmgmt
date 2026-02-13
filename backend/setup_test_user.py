"""
Setup Script - Erstellt Test-User in DB

Verwendung:
    python setup_test_user.py
"""
from app.db.database import init_db, create_tables, SessionLocal
from app.db.models import User
import os
import uuid
from dotenv import load_dotenv

def setup_test_user():
    """Erstellt Test-User in DB"""

    # DB initialisieren
    load_dotenv()
    database_url = os.getenv("DATABASE_URL", "sqlite:///./cashmgnt.db")
    init_db(database_url)
    create_tables()

    # Session erstellen (nach init_db!)
    from app.db.database import SessionLocal as SL
    db = SL()

    try:
        # Prüfe ob User schon existiert
        existing_user = db.query(User).filter(User.id == "user_123").first()

        if existing_user:
            print("✅ User 'user_123' existiert bereits")
            print(f"   Email: {existing_user.email}")
            print(f"   Created: {existing_user.created_at}")
        else:
            # User erstellen
            user = User(
                id="user_123",
                email="test@example.com"
            )
            db.add(user)
            db.commit()

            print("✅ User 'user_123' erfolgreich erstellt!")
            print(f"   Email: {user.email}")
            print(f"   ID: {user.id}")

        print("\n📝 Nächste Schritte:")
        print("1. Binance API-Keys in backend/.env eintragen")
        print("2. Backend starten: uvicorn app.main:app --reload")
        print("3. Fills synchronisieren: POST /api/sync/user_123/fills")

    except Exception as e:
        print(f"❌ Fehler: {e}")
        db.rollback()
    finally:
        db.close()

if __name__ == "__main__":
    setup_test_user()
