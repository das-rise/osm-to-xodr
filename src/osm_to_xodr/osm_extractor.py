"""Custom OSM signal extraction module."""

from __future__ import annotations

import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path

from loguru import logger


@dataclass
class OSMNode:
    """Represents an OSM node."""

    id: int
    lat: float
    lon: float
    tags: dict[str, str] = field(default_factory=dict)


class OSMSignalExtractor:
    """Extracts traffic signals and signs from OSM files.

    This class complements SUMO netconvert's sign extraction by
    directly parsing the OSM for additional signal types and
    country-specific codes.
    """

    # Mapping of OSM tags to generic signal types used in postprocess.py
    OSM_TAG_MAPPING = {
        "stop": "stop",
        "give_way": "yield",
        "traffic_signals": "traffic_light",
        "speed_limit": "speed",
        "maxspeed": "speed",
        "no_entry": "no_entry",
    }

    def __init__(self, osm_file: Path):
        self.osm_file = osm_file
        self.nodes: dict[int, OSMNode] = {}

    def extract(self, output_file: Path) -> bool:
        """Extract signals and save to SUMO-style XML.

        Args:
            output_file: Path to save the extracted signs XML.

        Returns:
            True if successful, False otherwise.
        """
        try:
            logger.debug(f"Parsing OSM file: {self.osm_file}")
            self._parse_osm()

            signals = self._find_signals()
            logger.info(f"Extracted {len(signals)} signals from OSM")

            if not signals:
                return True  # No signals found is still success

            self._write_xml(signals, output_file)
            return True
        except (ET.ParseError, OSError, ValueError) as e:
            logger.error(f"Failed to extract signals from OSM: {e}")
            return False

    def _parse_osm(self):
        """Parse the OSM XML and collect nodes with tags."""
        tree = ET.parse(self.osm_file)
        root = tree.getroot()

        for node_elem in root.findall("node"):
            node_id = int(node_elem.get("id", 0))
            lat = float(node_elem.get("lat", 0.0))
            lon = float(node_elem.get("lon", 0.0))

            tags = {}
            for tag_elem in node_elem.findall("tag"):
                k = tag_elem.get("k")
                v = tag_elem.get("v")
                if k and v:
                    tags[k] = v

            self.nodes[node_id] = OSMNode(node_id, lat, lon, tags)

    def _find_signals(self) -> list[dict]:
        """Identify signals from parsed nodes."""
        signals = []
        for node in self.nodes.values():
            signal_type = self._get_signal_type(node.tags)
            if signal_type:
                # Store original lat/lon for netconvert to handle projection
                signals.append(
                    {
                        "id": str(node.id),
                        "type": signal_type,
                        "lat": node.lat,
                        "lon": node.lon,
                        "osm_id": node.id,
                        "tags": node.tags,
                    }
                )
        return signals

    def _get_signal_type(self, tags: dict[str, str]) -> str | None:
        """Determine signal type from OSM tags."""
        # 1. Check highway tag (international standard)
        highway = tags.get("highway")
        if highway in self.OSM_TAG_MAPPING:
            return self.OSM_TAG_MAPPING[highway]

        # 2. Check traffic_sign tag
        if "traffic_sign" in tags:
            sign_value = tags["traffic_sign"]
            # Common patterns in traffic_sign values
            for osm_tag, generic_type in self.OSM_TAG_MAPPING.items():
                if osm_tag in sign_value.lower():
                    return generic_type

            # If it contains country code (e.g., SE:B3), it's definitely a sign
            if ":" in sign_value:
                # Return the full sign value to be handled by country mappings in postprocess.py
                return sign_value

        # 3. Check for specific tags like maxspeed
        if "maxspeed" in tags:
            return "speed"

        return None

    def _write_xml(self, signals: list[dict], output_file: Path):
        """Write signals to SUMO-style POI XML."""
        root = ET.Element("additional")

        for sig in signals:
            poi = ET.SubElement(root, "poi")
            poi.set("id", sig["id"])
            poi.set("type", sig["type"])
            # Use lon/lat instead of x/y to let netconvert handle projection and offset
            poi.set("lon", f"{sig['lon']:.7f}")
            poi.set("lat", f"{sig['lat']:.7f}")
            poi.set("color", "red")  # Default SUMO POI color
            poi.set("layer", "100.00")

            # Store original tags as parameters for debugging/advanced matching
            # This is the standard SUMO way to store custom data that netconvert accepts.
            for k, v in sig["tags"].items():
                param = ET.SubElement(poi, "param")
                param.set("key", f"osm.{k}")
                param.set("value", str(v))

        tree = ET.ElementTree(root)

        # Format XML for readability
        ET.indent(tree, space="    ", level=0)

        output_file.parent.mkdir(parents=True, exist_ok=True)
        tree.write(output_file, encoding="utf-8", xml_declaration=True)
        logger.debug(f"Saved {len(signals)} signals to {output_file}")


def merge_poi_files(file1: Path, file2: Path, output_file: Path):
    """Merge two SUMO-style POI XML files into one.

    Args:
        file1: First POI file.
        file2: Second POI file.
        output_file: Path to save the merged POI XML.
    """
    try:
        tree1 = ET.parse(file1)
        root1 = tree1.getroot()

        tree2 = ET.parse(file2)
        root2 = tree2.getroot()

        # Check for existing IDs to avoid duplicates
        existing_ids = {poi.get("id") for poi in root1.findall("poi")}

        for poi in root2.findall("poi"):
            poi_id = poi.get("id")
            if poi_id not in existing_ids:
                root1.append(poi)
                existing_ids.add(poi_id)

        # Format XML for readability
        ET.indent(root1, space="    ", level=0)

        output_file.parent.mkdir(parents=True, exist_ok=True)
        tree1.write(output_file, encoding="utf-8", xml_declaration=True)
        logger.debug(f"Merged POI files saved to {output_file}")
    except (ET.ParseError, OSError) as e:
        logger.error(f"Failed to merge POI files: {e}")
        # If merging fails, we might want to return one of the files
        raise
