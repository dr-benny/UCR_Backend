import sys
import os

# Add project root to sys.path
sys.path.insert(0, os.path.realpath(os.path.join(os.path.dirname(__file__), '..')))

from app.db.database import engine, Base
from app.models import StreetAnalysis, SurveyRoute  # Import all models to register them with Base.metadata

def rebuild_database():
    print("Dropping all tables...")
    Base.metadata.drop_all(bind=engine)
    
    print("Creating all tables...")
    Base.metadata.create_all(bind=engine)
    
    print("Database rebuilding complete.")

if __name__ == "__main__":
    rebuild_database()
