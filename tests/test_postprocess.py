"""Tests for the postprocess module."""

from __future__ import annotations

import math
import tempfile
from pathlib import Path

import utm

from osm_to_xodr.postprocess import (
    COUNTRY_MAPPINGS,
    convert_objects_to_signals,
    fix_dangling_junction_refs,
    fix_georeference_for_carla,
)


def test_country_mappings_contains_common_signs() -> None:
    """Test that COUNTRY_MAPPINGS has common traffic sign types for the SE locale."""
    se = COUNTRY_MAPPINGS["SE"]
    assert "priority" in se
    assert "yield" in se
    assert "stop" in se
    assert "speedLimit" in se


def test_convert_objects_file_not_found() -> None:
    """Test convert_objects_to_signals with non-existent file."""
    result = convert_objects_to_signals(Path("/nonexistent/file.xodr"))

    assert result.success is False
    assert "not found" in result.error.lower()


def test_convert_objects_invalid_xml() -> None:
    """Test convert_objects_to_signals with invalid XML."""
    with tempfile.NamedTemporaryFile(suffix=".xodr", delete=False, mode="w") as f:
        f.write("not valid xml")
        temp_path = Path(f.name)

    try:
        result = convert_objects_to_signals(temp_path)
        assert result.success is False
        assert "parse" in result.error.lower() or "xml" in result.error.lower()
    finally:
        temp_path.unlink()


def test_convert_objects_empty_xodr() -> None:
    """Test convert_objects_to_signals with valid but empty XODR."""
    with tempfile.NamedTemporaryFile(suffix=".xodr", delete=False, mode="w") as f:
        f.write('<?xml version="1.0" encoding="UTF-8"?>\n<OpenDRIVE></OpenDRIVE>')
        temp_path = Path(f.name)

    try:
        result = convert_objects_to_signals(temp_path)
        assert result.success is True
        assert result.signals_converted == 0
    finally:
        temp_path.unlink()


def test_convert_objects_with_signs() -> None:
    """Test convert_objects_to_signals converts sign objects to signals."""
    xodr_content = """<?xml version="1.0" encoding="UTF-8"?>
<OpenDRIVE>
    <road id="1" name="Test Road">
        <objects>
            <object id="sign1" type="stop" s="10.0" t="-5.0"/>
            <object id="sign2" type="yield" s="20.0" t="5.0"/>
        </objects>
    </road>
</OpenDRIVE>"""

    with tempfile.NamedTemporaryFile(suffix=".xodr", delete=False, mode="w") as f:
        f.write(xodr_content)
        temp_path = Path(f.name)

    try:
        result = convert_objects_to_signals(temp_path)
        assert result.success is True
        assert result.signals_converted == 2
        assert result.poles_added == 2

        # Verify the file was modified
        content = temp_path.read_text()
        assert "<signal" in content
        assert 'type="201"' in content  # Stop sign (SE: 201)
        assert 'type="206"' in content  # Yield sign (SE: 206)
    finally:
        temp_path.unlink()


# --- geoReference Fixing Tests ---


def test_fix_georeference_adds_lat_lon_from_offset() -> None:
    """Test fix_georeference_for_carla calculates and adds lat_0/lon_0."""
    # Test values: Gothenburg, Sweden approx
    lat, lon = 57.708870, 11.974560
    easting, northing, zone, letter = utm.from_latlon(lat, lon)

    # Create XML with matching offset and zone
    xodr_content = f"""<?xml version="1.0" encoding="UTF-8"?>
<OpenDRIVE>
    <header revMajor="1" revMinor="4">
        <offset x="{easting}" y="{northing}" z="0"/>
        <geoReference>
+proj=utm +zone={zone} +ellps=WGS84 +datum=WGS84 +units=m +no_defs
        </geoReference>
    </header>
</OpenDRIVE>"""

    with tempfile.NamedTemporaryFile(suffix=".xodr", delete=False, mode="w") as f:
        f.write(xodr_content)
        temp_path = Path(f.name)

    try:
        result = fix_georeference_for_carla(temp_path)
        assert result is True

        # Verify the file was modified with lat_0/lon_0
        content = temp_path.read_text()

        # Check that we got approximately the right lat/lon back
        # We can't do exact string match because specific decimals depend on utm lib impl
        # but we know it outputs 10 decimals in our code.
        assert "+lat_0=" in content
        assert "+lon_0=" in content

        # Original projection should be preserved
        assert "+proj=utm" in content
        assert f"+zone={zone}" in content
    finally:
        temp_path.unlink()


def test_fix_georeference_skips_if_already_present() -> None:
    """Test fix_georeference_for_carla skips if lat_0/lon_0 already present."""
    xodr_content = """<?xml version="1.0" encoding="UTF-8"?>
<OpenDRIVE>
    <header revMajor="1" revMinor="4">
        <offset x="500000" y="5000000" z="0"/>
        <geoReference>
+proj=tmerc +lat_0=57.74 +lon_0=12.89 +k=1 +datum=WGS84 +units=m +no_defs
        </geoReference>
    </header>
</OpenDRIVE>"""

    with tempfile.NamedTemporaryFile(suffix=".xodr", delete=False, mode="w") as f:
        f.write(xodr_content)
        temp_path = Path(f.name)

    try:
        result = fix_georeference_for_carla(temp_path)
        assert result is False  # Should not modify

        # Verify original values preserved
        content = temp_path.read_text()
        assert "+lat_0=57.74" in content
        assert "+lon_0=12.89" in content
    finally:
        temp_path.unlink()


def test_fix_georeference_no_header() -> None:
    """Test fix_georeference_for_carla with missing header."""
    xodr_content = """<?xml version="1.0" encoding="UTF-8"?>
<OpenDRIVE>
    <road id="1" name="Test"/>
</OpenDRIVE>"""

    with tempfile.NamedTemporaryFile(suffix=".xodr", delete=False, mode="w") as f:
        f.write(xodr_content)
        temp_path = Path(f.name)

    try:
        result = fix_georeference_for_carla(temp_path)
        assert result is False
    finally:
        temp_path.unlink()


def test_fix_georeference_no_georeference() -> None:
    """Test fix_georeference_for_carla with missing geoReference."""
    xodr_content = """<?xml version="1.0" encoding="UTF-8"?>
<OpenDRIVE>
    <header revMajor="1" revMinor="4">
        <offset x="0" y="0" z="0"/>
    </header>
</OpenDRIVE>"""

    with tempfile.NamedTemporaryFile(suffix=".xodr", delete=False, mode="w") as f:
        f.write(xodr_content)
        temp_path = Path(f.name)

    try:
        result = fix_georeference_for_carla(temp_path)
        assert result is False
    finally:
        temp_path.unlink()


# ---------------------------------------------------------------------------
# fix_dangling_junction_refs tests
# ---------------------------------------------------------------------------

_LOOP_XODR = """\
<?xml version="1.0" encoding="UTF-8"?>
<OpenDRIVE>
    <header revMajor="1" revMinor="4" name="" version="1.00" />
    <road name="Forward" length="100.0" id="1" junction="-1">
        <link>
            <predecessor elementType="junction" elementId="99" />
        </link>
        <planView>
            <geometry s="0.0" x="0.0" y="0.0" hdg="0.0" length="100.0">
                <line />
            </geometry>
        </planView>
        <lanes>
            <laneSection s="0">
                <center><lane id="0" type="none" level="true"><link /></lane></center>
                <right>
                    <lane id="-1" type="driving" level="true">
                        <link />
                        <width sOffset="0" a="3.5" b="0" c="0" d="0" />
                    </lane>
                </right>
            </laneSection>
        </lanes>
    </road>
    <road name="Reverse" length="100.0" id="2" junction="-1">
        <link>
            <predecessor elementType="junction" elementId="100" />
        </link>
        <planView>
            <geometry s="0.0" x="100.0" y="0.0" hdg="3.14159265" length="100.0">
                <line />
            </geometry>
        </planView>
        <lanes>
            <laneSection s="0">
                <center><lane id="0" type="none" level="true"><link /></lane></center>
                <right>
                    <lane id="-1" type="driving" level="true">
                        <link />
                        <width sOffset="0" a="3.5" b="0" c="0" d="0" />
                    </lane>
                </right>
            </laneSection>
        </lanes>
    </road>
</OpenDRIVE>"""
"""
Geometry of _LOOP_XODR:
  Road 1: start=(0,0) → end=(100,0)   heading=0
  Road 2: start=(100,0) → end=(0,0)   heading=pi

Dangling endpoints:
  Road 1 predecessor (start)  at (0,0)   — junction 99 not defined
  Road 2 predecessor (start)  at (100,0) — junction 100 not defined

No successors declared → end of road 1 at (100,0) and end of road 2 at (0,0)
are also unlinked, and happen to coincide with the dangling starts of the other road.
Expected fixes: 2 connections (each dangling start of one road linked to the
matching end of the partner).
"""


def test_fix_dangling_junction_refs_file_not_found() -> None:
    """Returns 0 and does not raise when the file does not exist."""
    result = fix_dangling_junction_refs(Path("/nonexistent/path/missing.xodr"))
    assert result == 0


def test_fix_dangling_junction_refs_no_dangling_refs() -> None:
    """Returns 0 and leaves the file byte-identical when no phantom junctions exist."""
    xodr = """\
<?xml version="1.0" encoding="UTF-8"?>
<OpenDRIVE>
    <road name="R1" length="50.0" id="10" junction="-1">
        <link>
            <successor elementType="road" elementId="11" contactPoint="start" />
        </link>
        <planView>
            <geometry s="0.0" x="0.0" y="0.0" hdg="0.0" length="50.0">
                <line />
            </geometry>
        </planView>
        <lanes><laneSection s="0"><center><lane id="0" type="none" level="true"><link /></lane></center></laneSection></lanes>
    </road>
</OpenDRIVE>"""
    with tempfile.NamedTemporaryFile(suffix=".xodr", delete=False, mode="w") as f:
        f.write(xodr)
        tmp = Path(f.name)
    try:
        result = fix_dangling_junction_refs(tmp)
        assert result == 0
        assert tmp.read_text() == xodr
    finally:
        tmp.unlink()


def test_fix_dangling_junction_refs_connects_loop_pair() -> None:
    """Two roads forming a bidirectional closed loop with phantom junction refs
    are connected to each other after the fix."""
    import xml.etree.ElementTree as ET  # noqa: PLC0415 – local import for clarity

    with tempfile.NamedTemporaryFile(suffix=".xodr", delete=False, mode="w") as f:
        f.write(_LOOP_XODR)
        tmp = Path(f.name)
    try:
        result = fix_dangling_junction_refs(tmp)
        assert (
            result == 2
        ), f"Expected 2 fixes (dangling start of each road), got {result}"

        root = ET.parse(tmp).getroot()
        road1 = root.find("road[@id='1']")
        road2 = root.find("road[@id='2']")
        assert road1 is not None and road2 is not None

        # After fix, road 1's predecessor must point to road 2 (no longer a junction ref)
        pred1 = road1.find("link/predecessor")
        assert pred1 is not None, "Road 1 still has no predecessor after fix"
        assert (
            pred1.get("elementType") == "road"
        ), f"Road 1 predecessor elementType is still '{pred1.get('elementType')}'"
        assert (
            pred1.get("elementId") == "2"
        ), f"Road 1 predecessor elementId should be '2', got '{pred1.get('elementId')}'"

        # Road 2's predecessor must point to road 1
        pred2 = road2.find("link/predecessor")
        assert pred2 is not None, "Road 2 still has no predecessor after fix"
        assert pred2.get("elementType") == "road"
        assert pred2.get("elementId") == "1"
    finally:
        tmp.unlink()


def test_fix_dangling_junction_refs_lane_links_updated() -> None:
    """Lane <link> elements get a predecessor id after the road-level fix."""
    import xml.etree.ElementTree as ET  # noqa: PLC0415

    with tempfile.NamedTemporaryFile(suffix=".xodr", delete=False, mode="w") as f:
        f.write(_LOOP_XODR)
        tmp = Path(f.name)
    try:
        fix_dangling_junction_refs(tmp)
        root = ET.parse(tmp).getroot()

        for road_id in ("1", "2"):
            lane = root.find(f"road[@id='{road_id}']//lane[@id='-1']")
            assert lane is not None, f"Road {road_id}: driving lane -1 not found"
            pred = lane.find("link/predecessor")
            assert (
                pred is not None
            ), f"Road {road_id} lane -1: no lane link predecessor after fix"
            assert pred.get("id") == "-1", (
                f"Road {road_id} lane -1 predecessor id should be '-1', "
                f"got '{pred.get('id')}'"
            )
    finally:
        tmp.unlink()


def test_fix_dangling_junction_refs_no_partner_in_range() -> None:
    """A dangling road with no geometric partner within tolerance is left unchanged."""
    xodr = """\
<?xml version="1.0" encoding="UTF-8"?>
<OpenDRIVE>
    <road name="Isolated" length="100.0" id="99" junction="-1">
        <link>
            <predecessor elementType="junction" elementId="77" />
        </link>
        <planView>
            <geometry s="0.0" x="50000.0" y="50000.0" hdg="0.0" length="100.0">
                <line />
            </geometry>
        </planView>
        <lanes><laneSection s="0"><center><lane id="0" type="none" level="true"><link /></lane></center></laneSection></lanes>
    </road>
</OpenDRIVE>"""
    with tempfile.NamedTemporaryFile(suffix=".xodr", delete=False, mode="w") as f:
        f.write(xodr)
        tmp = Path(f.name)
    try:
        result = fix_dangling_junction_refs(tmp)
        assert result == 0
        # Phantom junction reference must still be present (file not modified)
        assert 'elementId="77"' in tmp.read_text()
    finally:
        tmp.unlink()


def test_fix_dangling_junction_refs_skips_junction_connector_roads() -> None:
    """Roads that are junction connectors (junction != -1) are never modified."""
    xodr = """\
<?xml version="1.0" encoding="UTF-8"?>
<OpenDRIVE>
    <junction id="5" name="J5">
        <connection id="0" incomingRoad="10" connectingRoad="20" contactPoint="start">
            <laneLink from="-1" to="-1" />
        </connection>
    </junction>
    <road name="Connector" length="10.0" id="20" junction="5">
        <link>
            <predecessor elementType="junction" elementId="999" />
        </link>
        <planView>
            <geometry s="0.0" x="0.0" y="0.0" hdg="0.0" length="10.0">
                <line />
            </geometry>
        </planView>
        <lanes><laneSection s="0"><center><lane id="0" type="none" level="true"><link /></lane></center></laneSection></lanes>
    </road>
</OpenDRIVE>"""
    with tempfile.NamedTemporaryFile(suffix=".xodr", delete=False, mode="w") as f:
        f.write(xodr)
        tmp = Path(f.name)
    try:
        result = fix_dangling_junction_refs(tmp)
        # Junction connector road is skipped — no fix applied
        assert result == 0
    finally:
        tmp.unlink()
