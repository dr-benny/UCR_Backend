"""
Backup script — exports database + image files into a timestamped folder.

Usage:
    python scripts/backup.py

Output:
    backups/backup_YYYYMMDD_HHMMSS/
    ├── database.sql          ← Full PostgreSQL dump (schema + data)
    ├── database.json         ← All street_analyses as JSON (portable)
    └── images/               ← Copy of all uploaded images
"""

import json
import os
import shutil
import subprocess
from datetime import datetime

# ── Setup paths ──────────────────────────────────────────────
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
IMAGES_DIR = os.path.join(PROJECT_ROOT, "images")
BACKUPS_DIR = os.path.join(PROJECT_ROOT, "backups")

timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
backup_dir = os.path.join(BACKUPS_DIR, f"backup_{timestamp}")
os.makedirs(backup_dir, exist_ok=True)

print(f"📦 Creating backup at: {backup_dir}")

# ── 1. PostgreSQL dump (SQL file) ─────────────────────────────
sql_path = os.path.join(backup_dir, "database.sql")
print("1️⃣  Dumping PostgreSQL database...")

try:
    result = subprocess.run(
        ["pg_dump", "-U", "postgres", "-d", "architecture", "--no-owner", "--no-acl"],
        capture_output=True, text=True, timeout=60
    )
    if result.returncode == 0:
        with open(sql_path, "w") as f:
            f.write(result.stdout)
        size_mb = os.path.getsize(sql_path) / (1024 * 1024)
        print(f"   ✅ SQL dump saved ({size_mb:.2f} MB)")
    else:
        print(f"   ⚠️ pg_dump warning: {result.stderr.strip()}")
        # Still write what we got
        if result.stdout:
            with open(sql_path, "w") as f:
                f.write(result.stdout)
            print(f"   ✅ SQL dump saved (with warnings)")
        else:
            print(f"   ❌ pg_dump failed")
except FileNotFoundError:
    print("   ❌ pg_dump not found! Install PostgreSQL CLI tools.")
except Exception as e:
    print(f"   ❌ Error: {e}")

# ── 2. Export data as JSON (portable) ─────────────────────────
print("2️⃣  Exporting data as JSON...")

import sys
sys.path.insert(0, PROJECT_ROOT)

try:
    from app.db.database import SessionLocal
    from app.models import StreetAnalysis, SurveyRoute

    db = SessionLocal()

    # Export routes
    routes = db.query(SurveyRoute).all()
    routes_data = []
    for r in routes:
        routes_data.append({
            "id": r.id,
            "name": r.name,
            "description": r.description,
            "created_at": str(r.created_at),
            "updated_at": str(r.updated_at),
        })

    # Export analyses
    analyses = db.query(StreetAnalysis).order_by(StreetAnalysis.id).all()
    analyses_data = []
    for a in analyses:
        analyses_data.append({
            "id": a.id,
            "route_id": a.route_id,
            "order_index": a.order_index,
            "latitude": a.latitude,
            "longitude": a.longitude,
            "heading": a.heading,
            "pitch": a.pitch,
            "fov": a.fov,
            "streetview_image_url": a.streetview_image_url,
            "image_path": a.image_path,
            "urban_morphology": a.urban_morphology,
            "vegetation": a.vegetation,
            "surface_and_flood": a.surface_and_flood,
            "health_livability": a.health_livability,
            "scene_description": a.scene_description,
            "observed_features": a.observed_features,
            "reference_objects": a.reference_objects,
            "evidence": a.evidence,
            "confidence_scores": a.confidence_scores,
            "created_at": str(a.created_at),
            "updated_at": str(a.updated_at),
        })

    db.close()

    json_path = os.path.join(backup_dir, "database.json")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump({
            "backup_timestamp": timestamp,
            "routes": routes_data,
            "analyses": analyses_data,
        }, f, ensure_ascii=False, indent=2)

    print(f"   ✅ JSON export saved ({len(routes_data)} routes, {len(analyses_data)} analyses)")

except Exception as e:
    print(f"   ❌ JSON export failed: {e}")

# ── 3. Copy images ────────────────────────────────────────────
print("3️⃣  Copying image files...")

if os.path.exists(IMAGES_DIR):
    img_backup_dir = os.path.join(backup_dir, "images")
    image_files = [f for f in os.listdir(IMAGES_DIR) if f.lower().endswith(('.jpg', '.jpeg', '.png', '.webp'))]

    if image_files:
        shutil.copytree(IMAGES_DIR, img_backup_dir, dirs_exist_ok=True)
        total_size = sum(os.path.getsize(os.path.join(img_backup_dir, f)) for f in image_files)
        size_mb = total_size / (1024 * 1024)
        print(f"   ✅ {len(image_files)} images copied ({size_mb:.2f} MB)")
    else:
        print("   ⚠️ No image files found in images/")
else:
    print("   ⚠️ images/ directory not found")

# ── Summary ───────────────────────────────────────────────────
print("\n" + "=" * 50)
print(f"🎉 Backup complete!")
print(f"📁 Location: {backup_dir}")
print("=" * 50)

# List backup contents
for item in sorted(os.listdir(backup_dir)):
    item_path = os.path.join(backup_dir, item)
    if os.path.isdir(item_path):
        count = len(os.listdir(item_path))
        print(f"   📂 {item}/ ({count} files)")
    else:
        size = os.path.getsize(item_path)
        if size > 1024 * 1024:
            print(f"   📄 {item} ({size / (1024*1024):.2f} MB)")
        else:
            print(f"   📄 {item} ({size / 1024:.1f} KB)")

print(f"\n💡 To restore from SQL:  psql -U postgres -d architecture < {sql_path}")
print(f"💡 To restore from JSON: python scripts/restore.py {backup_dir}")
