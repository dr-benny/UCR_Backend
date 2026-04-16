import json
import os
import sys
import requests

# Add project root to sys.path
sys.path.insert(0, os.path.realpath(os.path.join(os.path.dirname(__file__), '..')))

from app.db.database import SessionLocal
from app.models import StreetAnalysis

def run_upload():
    # Cleanup previously inserted records without analysis (the ones directly inserted)
    db = SessionLocal()
    try:
        # We delete rows where urban_morphology is None (since direct insert didn't generate AI analysis)
        deleted = db.query(StreetAnalysis).filter(StreetAnalysis.urban_morphology == None).delete(synchronize_session=False)
        db.commit()
        print(f"Cleaned up {deleted} manually inserted records without AI analysis.")
    except Exception as e:
        print(f"Cleanup error: {e}")
        db.rollback()
    finally:
        db.close()
        
    json_path = 'insertData/image_map.json'
    if not os.path.exists(json_path):
        print(f"File not found: {json_path}")
        return

    with open(json_path, 'r') as f:
        data = json.load(f)

    import time
    
    # API Endpoint (Single upload instead of batch)
    url = "http://localhost:8000/api/analyze/upload"
    
    # Process valid items
    valid_items = []
    for item in data:
        base_name, _ = os.path.splitext(item['image'])
        png_path = f"insertData/iben/{base_name}.png"
        jpg_path = f"insertData/iben/{base_name}.jpg"
        
        source_path = None
        if os.path.exists(png_path):
            source_path = png_path
        elif os.path.exists(jpg_path):
            source_path = jpg_path
        elif os.path.exists(f"insertData/{item['image']}"):
            source_path = f"insertData/{item['image']}"
        
        if source_path:
            item['_source_path'] = source_path
            valid_items.append(item)
        else:
            print(f"Warning: Image {item['image']} not found. Skipping.")

    print(f"Starting single upload for {len(valid_items)} images with rate limiting (4s delay)...")
    
    for idx, item in enumerate(valid_items):
        print(f"--- Sending Image {idx+1}/{len(valid_items)}: {item['image']} ---")
        
        mime = 'image/png' if item['_source_path'].endswith('.png') else 'image/jpeg'
        
        with open(item['_source_path'], 'rb') as f:
            files = {
                "file": (os.path.basename(item['_source_path']), f, mime)
            }
            
            payload = {
                "latitude": item['lat'],
                "longitude": item['lon'],
                "route_id": item.get('route_id', 1),
                "order_index": item.get('order', 0),
            }
            
            # Retry logic for Rate Limit
            max_retries = 3
            retries = 0
            success = False
            
            while retries < max_retries and not success:
                try:
                    response = requests.post(url, data=payload, files=files)
                    if response.status_code in [200, 201]:
                        print(f"✅ Image {idx+1} uploaded successfully!")
                        success = True
                    elif response.status_code == 502 and "429" in response.text:
                        print(f"⚠️ Rate limit hit. Waiting 60 seconds before retrying...")
                        time.sleep(60)
                        retries += 1
                        # We need to seek back to start of file for the retry
                        f.seek(0)
                    else:
                        print(f"❌ Image {idx+1} failed ({response.status_code}): {response.text}")
                        break
                except Exception as e:
                    print(f"❌ Image {idx+1} request failed: {e}")
                    break
                
        # To avoid Gemini API Free Tier rate limit (15 requests per minute)
        if idx < len(valid_items) - 1 and success:
            print("Waiting 5 seconds to respect API rate limits...")
            time.sleep(5)
            
    print("All API calls finished.")

if __name__ == '__main__':
    run_upload()
