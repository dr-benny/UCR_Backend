import json
import os

backup_dir = 'backups/backup_20260415_030648'
json_path = os.path.join(backup_dir, 'database.json')
images_dir = os.path.join(backup_dir, 'images')

with open(json_path, 'r') as f:
    data = json.load(f)

json_images = set()
for analysis in data.get('analyses', []):
    img_path = analysis.get('image_path')
    if img_path:
        # image_path is "images/filename.jpg"
        filename = os.path.basename(img_path)
        json_images.add(filename)

dir_images = set(os.listdir(images_dir))
if '.DS_Store' in dir_images:
    dir_images.remove('.DS_Store')

print(f"Images in JSON: {len(json_images)}")
print(f"Images in directory: {len(dir_images)}")

extra_in_dir = dir_images - json_images
print(f"Extra images in directory: {len(extra_in_dir)}")

# Print some extra images to see if there's a pattern
print("First 10 extra images:")
for img in sorted(list(extra_in_dir))[:10]:
    print(img)
