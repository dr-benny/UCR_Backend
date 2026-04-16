import os
import re

ROOT = "."

# 1. Create directory structure
dirs_to_create = [
    "app",
    "app/core",
    "app/db",
    "app/api",
    "app/api/v1"
]
for d in dirs_to_create:
    os.makedirs(os.path.join(ROOT, d), exist_ok=True)
    init_file = os.path.join(ROOT, d, "__init__.py")
    if not os.path.exists(init_file):
        open(init_file, "a").close()

# 2. Move directories / files
moves = [
    ("config.py", "app/core/config.py"),
    ("database.py", "app/db/database.py"),
    ("main.py", "app/main.py"),
    ("models", "app/models"),
    ("schemas", "app/schemas"),
    ("services", "app/services"),
    ("dao", "app/dao"),
]

for src, dst in moves:
    src_path = os.path.join(ROOT, src)
    dst_path = os.path.join(ROOT, dst)
    if os.path.exists(src_path):
        os.rename(src_path, dst_path)

# Move routers to app/api/v1
routers_src = os.path.join(ROOT, "routers")
if os.path.exists(routers_src):
    for item in os.listdir(routers_src):
        src_path = os.path.join(routers_src, item)
        dst_path = os.path.join(ROOT, "app/api/v1", item)
        os.rename(src_path, dst_path)
    os.rmdir(routers_src)

# 3. Text replacements
replacements = [
    (r"from app.core.config import", r"from app.core.config import"),
    (r"from app.core.config\b", r"from app.core.config"),
    (r"from app.db.database import", r"from app.db.database import"),
    (r"from app.db.database\b", r"from app.db.database"),
    (r"from app.models import", r"from app.models import"),
    (r"from app.models\b", r"from app.models"),
    (r"from app.schemas import", r"from app.schemas import"),
    (r"from app.schemas\b", r"from app.schemas"),
    (r"from app.services", r"from app.services"),
    (r"import app.services", r"import app.services"),
    (r"from app.dao", r"from app.dao"),
    (r"from app.api.v1 ", r"from app.api.v1 "),
    (r"from routers\.", r"from app.api.v1."),
    # run.py special update
    (r'"app.main:app"', r'"app.main:app"'),
]

def process_file(filepath):
    if not filepath.endswith(".py"):
        return
    with open(filepath, "r", encoding="utf-8") as f:
        content = f.read()
    
    new_content = content
    for pattern, repl in replacements:
        new_content = re.sub(pattern, repl, new_content)
    
    if new_content != content:
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(new_content)

# Process all .py files in app/, scripts/, alembic/ and run.py
for folder in ["app", "scripts", "alembic"]:
    folder_path = os.path.join(ROOT, folder)
    if os.path.exists(folder_path):
        for root, dirs, files in os.walk(folder_path):
            for file in files:
                process_file(os.path.join(root, file))

if os.path.exists(os.path.join(ROOT, "run.py")):
    process_file(os.path.join(ROOT, "run.py"))

print("Refactoring complete.")
