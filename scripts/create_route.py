import sys
import os

# Add project root to sys.path
sys.path.insert(0, os.path.realpath(os.path.join(os.path.dirname(__file__), '..')))

from app.db.database import SessionLocal
from app.models import SurveyRoute

def create_initial_route():
    db = SessionLocal()
    try:
        new_route = SurveyRoute(
            name="Sukhumvit Road Survey",
            description="Surveying walkway width and vegetation along Sukhumvit"
        )
        db.add(new_route)
        db.commit()
        db.refresh(new_route)
        print(f"✅ Route created successfully!")
        print(f"ID: {new_route.id}")
        print(f"Name: {new_route.name}")
    except Exception as e:
        print(f"❌ Error: {e}")
        db.rollback()
    finally:
        db.close()

if __name__ == "__main__":
    create_initial_route()
