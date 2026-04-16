from typing import List, Optional
from sqlalchemy import func
from sqlalchemy.orm import Session
from geoalchemy2.functions import ST_DWithin, ST_SetSRID, ST_Point
from geoalchemy2.elements import WKTElement
from app.models import StreetAnalysis

class AnalysisDAO:
    @staticmethod
    def create_analysis(db: Session, analysis_data: dict, latitude: float, longitude: float, route_id: Optional[int] = None, order_index: int = 0) -> StreetAnalysis:
        """
        Creates a new StreetAnalysis record.
        """
        # --- Auto-increment order_index if not provided ---
        if route_id is not None and (order_index is None or order_index == 0):
            max_idx = db.query(func.max(StreetAnalysis.order_index)).filter(
                StreetAnalysis.route_id == route_id
            ).scalar()
            order_index = (max_idx or 0) + 1 if max_idx is not None else 0

        record = StreetAnalysis(
            geom=WKTElement(f"POINT({longitude} {latitude})", srid=4326),
            route_id=route_id,
            order_index=order_index,
            heading=analysis_data.get("heading"),
            pitch=analysis_data.get("pitch"),
            fov=analysis_data.get("fov"),
            streetview_image_url=analysis_data.get("image_url"),
            image_path=analysis_data.get("image_path"),
            # AI categories
            urban_morphology=analysis_data.get("urban_morphology"),
            vegetation=analysis_data.get("vegetation"),
            surface_and_flood=analysis_data.get("surface_and_flood"),
            health_livability=analysis_data.get("health_livability"),
            # Metadata
            scene_description=analysis_data.get("scene_description"),
            observed_features=analysis_data.get("observed_features"),
            reference_objects=analysis_data.get("reference_objects"),
            # Confidence & Evidence
            evidence=analysis_data.get("evidence"),
            confidence_scores=analysis_data.get("confidence_scores"),
            raw_ai_response=analysis_data.get("raw_ai_response")
        )
        db.add(record)
        db.commit()
        db.refresh(record)
        return record

    @staticmethod
    def get_by_id(db: Session, analysis_id: int) -> Optional[StreetAnalysis]:
        return db.query(StreetAnalysis).filter(StreetAnalysis.id == analysis_id).first()

    @staticmethod
    def list_analyses(db: Session, skip: int = 0, limit: int = 100, heat_risk: Optional[str] = None) -> List[StreetAnalysis]:
        query = db.query(StreetAnalysis).order_by(StreetAnalysis.created_at.desc())
        if heat_risk:
            # TODO: Implemented via application-side filter or move property evaluation logic into the database via hybrid_property
            pass 
        return query.offset(skip).limit(limit).all()

    @staticmethod
    def delete_analysis(db: Session, analysis_id: int) -> bool:
        record = db.query(StreetAnalysis).filter(StreetAnalysis.id == analysis_id).first()
        if record:
            db.delete(record)
            db.commit()
            return True
        return False

    @staticmethod
    def update_ai_result(db: Session, record: StreetAnalysis, ai_result: dict) -> StreetAnalysis:
        """Overwrite the AI analysis fields on an existing record."""
        record.urban_morphology = ai_result.get("urban_morphology")
        record.vegetation = ai_result.get("vegetation")
        record.surface_and_flood = ai_result.get("surface_and_flood")
        record.health_livability = ai_result.get("health_livability")
        record.scene_description = ai_result.get("scene_description")
        record.observed_features = ai_result.get("observed_features")
        record.reference_objects = ai_result.get("reference_objects")
        record.evidence = ai_result.get("evidence")
        record.confidence_scores = ai_result.get("confidence_scores")
        record.raw_ai_response = ai_result
        db.commit()
        db.refresh(record)
        return record

    @staticmethod
    def find_nearby_analysis(
        db: Session, 
        latitude: float, 
        longitude: float, 
        route_id: int, 
        radius_meters: float = 1.0
    ) -> Optional[StreetAnalysis]:
        """
        Find an existing analysis in the same route within a small radius.
        Uses PostGIS ST_DWithin for efficiency.
        """
        from sqlalchemy import cast
        from geoalchemy2.types import Geography

        # Create a point from the target lat/lng (PostGIS use long, lat)
        point = ST_SetSRID(ST_Point(longitude, latitude), 4326)
        
        return (
            db.query(StreetAnalysis)
            .filter(StreetAnalysis.route_id == route_id)
            .filter(ST_DWithin(cast(StreetAnalysis.geom, Geography), cast(point, Geography), radius_meters))
            .first()
        )

    @staticmethod
    def get_by_route(db: Session, route_id: int) -> List[StreetAnalysis]:
        """Return all analyses for a route, ordered by order_index."""
        return (
            db.query(StreetAnalysis)
            .filter(StreetAnalysis.route_id == route_id)
            .order_by(StreetAnalysis.order_index)
            .all()
        )



