from typing import List, Optional
from sqlalchemy.orm import Session
from app.models import SurveyRoute

class RouteDAO:
    @staticmethod
    def create_route(db: Session, name: str, description: Optional[str] = None) -> SurveyRoute:
        route = SurveyRoute(name=name, description=description)
        db.add(route)
        db.commit()
        db.refresh(route)
        return route

    @staticmethod
    def get_by_id(db: Session, route_id: int) -> Optional[SurveyRoute]:
        return db.query(SurveyRoute).filter(SurveyRoute.id == route_id).first()

    @staticmethod
    def list_routes(db: Session, skip: int = 0, limit: int = 100) -> List[SurveyRoute]:
        return db.query(SurveyRoute).order_by(SurveyRoute.created_at.desc()).offset(skip).limit(limit).all()

    @staticmethod
    def delete_route(db: Session, route_id: int) -> bool:
        route = db.query(SurveyRoute).filter(SurveyRoute.id == route_id).first()
        if route:
            db.delete(route)
            db.commit()
            return True
        return False
