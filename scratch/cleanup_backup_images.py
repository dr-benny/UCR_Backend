import json
import os

backup_dir = 'backups/backup_20260415_030648'
json_path = os.path.join(backup_dir, 'database.json')
images_dir = os.path.join(backup_dir, 'images')

if not os.path.exists(json_path):
    print(f"Error: {json_path} not found.")
    exit(1)

with open(json_path, 'r') as f:
    data = json.load(f)

json_images = set()
for analysis in data.get('analyses', []):
    img_path = analysis.get('image_path')
    if img_path:
        filename = os.path.basename(img_path)
        json_images.add(filename)

print(f"Total valid images in JSON: {len(json_images)}")

deleted_count = 0
for filename in os.listdir(images_dir):
    if filename == '.DS_Store':
        continue
    
    if filename not in json_images:
        file_path = os.path.join(images_dir, filename)
        try:
            os.remove(file_path)
            # print(f"Deleted: {filename}")
            deleted_count += 1
        except Exception as e:
            print(f"Failed to delete {filename}: {e}")

print(f"Cleanup complete. Deleted {deleted_count} orphan images.")
print(f"Remaining images in directory: {len(os.listdir(images_dir))}")
