import math
from typing import List
from app.models.analysis import StreetAnalysis

class KMLService:
    @staticmethod
    def generate_street_width_kml(analyses: List[StreetAnalysis], route_name: str = "Exported Route") -> str:
        """
        Generates a comprehensive KML file with all AI-analyzed urban indicators.
        """
        kml_header = f"""<?xml version="1.0" encoding="UTF-8"?>
<kml xmlns="http://www.opengis.net/kml/2.2">
  <Document>
    <name>{route_name}</name>
    
    <Style id="pointStyle">
      <IconStyle>
        <color>ff00ff00</color> <!-- Green -->
        <scale>1.0</scale>
      </IconStyle>
      <LabelStyle>
        <scale>0.8</scale>
      </LabelStyle>
      <BalloonStyle>
        <text>$[description]</text>
      </BalloonStyle>
    </Style>

    <Style id="pathStyle">
      <LineStyle>
        <color>ff00ffff</color> <!-- Yellow -->
        <width>3</width>
      </LineStyle>
    </Style>

    <Style id="widthLine">
      <LineStyle>
        <color>ff0000ff</color> <!-- Red -->
        <width>5</width>
      </LineStyle>
    </Style>
"""
        kml_footer = """  </Document>
</kml>"""
        
        placemarks = []
        path_coords = []
        WIDTH_SCALE = 3.0 
        
        for analysis in analyses:
            lat = analysis.latitude
            lon = analysis.longitude
            width = analysis.walkway_width_m
            heading = analysis.heading if analysis.heading is not None else 0
            
            path_coords.append(f"{lon},{lat},0")
            
            # Helper to safely get data from JSON fields
            def get_val(obj, key, default="N/A"):
                if not obj: return default
                val = obj.get(key)
                return val if val not in [None, "unknown", ""] else default

            # Extraction of all categories
            morph = analysis.urban_morphology or {}
            veg = analysis.vegetation or {}
            flood = analysis.surface_and_flood or {}
            health = analysis.health_livability or {}
            
            # Building the ExtendedData and HTML rows
            fields = [
                ("Street Width", f"{width if width else 'Unknown'} m"),
                ("Building Height", f"{get_val(morph, 'building_height_est_m')} m"),
                ("H/W Ratio", get_val(morph, "height_width_ratio")),
                ("Sky View Factor", get_val(morph, "sky_view_factor")),
                ("Road Slope", get_val(morph, "road_slope")),
                ("Sidewalk Height", get_val(morph, "sidewalk_height")),
                ("Green View Index", get_val(veg, "green_view_index")),
                ("Tree Canopy", get_val(veg, "tree_canopy_coverage")),
                ("Shade Fraction", get_val(veg, "shade_fraction")),
                ("Surface Material", get_val(flood, "surface_material")),
                ("Impervious Ratio", get_val(flood, "impervious_surface_ratio")),
                ("Drainage Presence", get_val(flood, "drainage_infrastructure_presence")),
                ("Waste Accumulation", get_val(health, "waste_accumulation")),
                ("Walkability Obstruction", get_val(health, "walkability_obstruction")),
                ("Lighting Info", get_val(health, "lighting_infrastructure")),
                ("Trash Bins", get_val(health, "trash_bin_presence")),
            ]

            data_elements = "".join([f'<Data name="{n}"><value>{v}</value></Data>' for n, v in fields])
            extended_data = f"<ExtendedData>{data_elements}</ExtendedData>"

            table_rows = "".join([
                f'<tr style="background-color: {"#f1f3f4" if i%2==0 else "#ffffff"};">'
                f'<td style="padding: 6px; font-weight: bold; border-bottom: 1px solid #ddd;">{n}</td>'
                f'<td style="padding: 6px; border-bottom: 1px solid #ddd;">{v}</td></tr>'
                for i, (n, v) in enumerate(fields)
            ])

            image_html = ""
            if analysis.streetview_image_url and analysis.streetview_image_url.startswith("http"):
                image_html = f'<img src="{analysis.streetview_image_url}" style="width: 100%; border-radius: 8px; margin-bottom: 15px;" />'

            description_html = f"""<![CDATA[
                <div style="font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; min-width: 300px; max-width: 450px;">
                    <h2 style="color: #1a73e8; margin-bottom: 5px;">Urban Analysis Point #{analysis.id}</h2>
                    {image_html}
                    <div style="background-color: #e8f0fe; padding: 12px; border-radius: 8px; margin-bottom: 15px; line-height: 1.5; color: #3c4043;">
                        {analysis.scene_description or "Detailed scene description not available."}
                    </div>
                    <h4 style="color: #5f6368; margin-bottom: 8px; border-bottom: 1px solid #dadce0; padding-bottom: 4px;">Detected Indicators</h4>
                    <table style="width: 100%; border-collapse: collapse; font-size: 13px;">
                        {table_rows}
                    </table>
                    <div style="margin-top: 15px; font-size: 11px; color: #9aa0a6; text-align: right;">
                        Survey Location: {lat:.6f}, {lon:.6f}<br/>
                        Heading: {heading}&deg; | Pitch: {analysis.pitch}&deg;
                    </div>
                </div>
            ]]>"""

            placemarks.append(f"""    <Placemark>
      <name>Point {analysis.id}</name>
      <description>{description_html}</description>
{extended_data}
      <styleUrl>#pointStyle</styleUrl>
      <Point><coordinates>{lon},{lat},0</coordinates></Point>
    </Placemark>""")
            
            if width and width > 0:
                visual_width = width * WIDTH_SCALE
                p1 = KMLService._calculate_offset(lat, lon, (heading + 90) % 360, visual_width / 2)
                p2 = KMLService._calculate_offset(lat, lon, (heading - 90) % 360, visual_width / 2)
                placemarks.append(f"""    <Placemark>
      <name>{width}m (Width)</name>
      <styleUrl>#widthLine</styleUrl>
      <LineString><coordinates>{p1[1]},{p1[0]},0 {p2[1]},{p2[0]},0</coordinates></LineString>
    </Placemark>""")

        if path_coords:
            placemarks.insert(0, f"""    <Placemark>
      <name>Survey Path</name>
      <styleUrl>#pathStyle</styleUrl>
      <LineString><tessellate>1</tessellate><coordinates>{" ".join(path_coords)}</coordinates></LineString>
    </Placemark>""")

        return kml_header + "\n".join(placemarks) + kml_footer

    @staticmethod
    def _calculate_offset(lat, lon, bearing_deg, distance_m):
        R = 6378137
        bearing, lat_rad, lon_rad = math.radians(bearing_deg), math.radians(lat), math.radians(lon)
        angular_dist = distance_m / R
        new_lat_rad = math.asin(math.sin(lat_rad) * math.cos(angular_dist) + math.cos(lat_rad) * math.sin(angular_dist) * math.cos(bearing))
        new_lon_rad = lon_rad + math.atan2(math.sin(bearing) * math.sin(angular_dist) * math.cos(lat_rad), math.cos(angular_dist) - math.sin(lat_rad) * math.sin(new_lat_rad))
        return (math.degrees(new_lat_rad), math.degrees(new_lon_rad))
