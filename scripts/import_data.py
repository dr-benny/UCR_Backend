import json
import os
import sys

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

from geoalchemy2.elements import WKTElement
from app.db.database import SessionLocal
from app.models.analysis import StreetAnalysis
from app.models.route import SurveyRoute
from datetime import datetime

def restore_backup(backup_dir: str):
    json_path = os.path.join(backup_dir, "database.json")
    if not os.path.exists(json_path):
        print(f"❌ Backup JSON not found at: {json_path}")
        return

    with open(json_path, 'r', encoding='utf-8') as f:
        data = json.load(f)

    db = SessionLocal()
    
    try:
        # Import routes
        print(f"📌 Importing {len(data.get('routes', []))} routes...")
        for r_data in data.get("routes", []):
            route = db.query(SurveyRoute).filter(SurveyRoute.id == r_data["id"]).first()
            if not route:
                route = SurveyRoute(
                    id=r_data["id"],
                    name=r_data.get("name"),
                    description=r_data.get("description")
                )
                if r_data.get("created_at"):
                    route.created_at = datetime.fromisoformat(r_data["created_at"])
                if r_data.get("updated_at"):
                    route.updated_at = datetime.fromisoformat(r_data["updated_at"])
                db.add(route)
            else:
                route.name = r_data.get("name")
                route.description = r_data.get("description")
        
        db.commit()

        # Import analyses
        print(f"📌 Importing {len(data.get('analyses', []))} analyses...")
        for a_data in data.get("analyses", []):
            analysis = db.query(StreetAnalysis).filter(StreetAnalysis.id == a_data["id"]).first()
            
            lon = a_data.get("longitude", 0.0)
            lat = a_data.get("latitude", 0.0)
            geom = WKTElement(f"POINT({lon} {lat})", srid=4326)
            
            if not analysis:
                analysis = StreetAnalysis(
                    id=a_data["id"],
                    route_id=a_data.get("route_id"),
                    order_index=a_data.get("order_index", 0),
                    geom=geom,
                    heading=a_data.get("heading"),
                    pitch=a_data.get("pitch", 0),
                    fov=a_data.get("fov", 90),
                    streetview_image_url=a_data.get("streetview_image_url"),
                    image_path=a_data.get("image_path"),
                    urban_morphology=a_data.get("urban_morphology"),
                    vegetation=a_data.get("vegetation"),
                    surface_and_flood=a_data.get("surface_and_flood"),
                    health_livability=a_data.get("health_livability"),
                    scene_description=a_data.get("scene_description"),
                    observed_features=a_data.get("observed_features"),
                    reference_objects=a_data.get("reference_objects"),
                    evidence=a_data.get("evidence"),
                    confidence_scores=a_data.get("confidence_scores")
                )
                if a_data.get("created_at"):
                    analysis.created_at = datetime.fromisoformat(a_data["created_at"])
                if a_data.get("updated_at"):
                    analysis.updated_at = datetime.fromisoformat(a_data["updated_at"])
                db.add(analysis)
            else:
                analysis.route_id = a_data.get("route_id")
                analysis.order_index = a_data.get("order_index", 0)
                analysis.geom = geom
                analysis.heading = a_data.get("heading")
                analysis.pitch = a_data.get("pitch", 0)
                analysis.fov = a_data.get("fov", 90)
                analysis.streetview_image_url = a_data.get("streetview_image_url")
                analysis.image_path = a_data.get("image_path")
                analysis.urban_morphology = a_data.get("urban_morphology")
                analysis.vegetation = a_data.get("vegetation")
                analysis.surface_and_flood = a_data.get("surface_and_flood")
                analysis.health_livability = a_data.get("health_livability")
                analysis.scene_description = a_data.get("scene_description")
                analysis.observed_features = a_data.get("observed_features")
                analysis.reference_objects = a_data.get("reference_objects")
                analysis.evidence = a_data.get("evidence")
                analysis.confidence_scores = a_data.get("confidence_scores")
                
        db.commit()
        print("✅ Restore complete!")
        
    except Exception as e:
        db.rollback()
        print(f"❌ Error during restore: {e}")
    finally:
        db.close()


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python scripts/import_data.py <backup_dir>")
        print("Example: python scripts/import_data.py backups/backup_20260415_030648")
        sys.exit(1)
        
    backup_path = sys.argv[1]
    restore_backup(backup_path)
