"""Subprocess wrapper for SUMO netconvert command."""

from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

from loguru import logger


@dataclass
class NetconvertResult:
    """Result of a netconvert command execution."""

    success: bool
    command: list[str]
    stdout: str
    stderr: str
    returncode: int


class NetconvertNotFoundError(Exception):
    """Raised when netconvert is not available on the system."""


def find_netconvert() -> list[str]:
    """Find the netconvert command, trying system install first, then Flatpak.

    Returns:
        List of command parts to invoke netconvert.

    Raises:
        NetconvertNotFoundError: If netconvert is not found.
    """
    # Try system netconvert first
    if shutil.which("netconvert"):
        logger.debug("Found system netconvert")
        return ["netconvert"]

    # Try Flatpak
    if shutil.which("flatpak"):
        # Check if SUMO is installed via Flatpak
        result = subprocess.run(
            ["flatpak", "list", "--app"],
            capture_output=True,
            text=True,
            check=False,
        )
        if "org.eclipse.sumo" in result.stdout:
            logger.debug("Found Flatpak netconvert")
            return ["flatpak", "run", "--command=netconvert", "org.eclipse.sumo"]

    raise NetconvertNotFoundError(
        "netconvert not found. Please install SUMO:\n"
        "  - Linux (apt): sudo apt install sumo sumo-tools\n"
        "  - Linux (Flatpak): flatpak install flathub org.eclipse.sumo\n"
        "  - macOS: brew tap dlr-ts/sumo && brew install sumo\n"
        "  - Windows: Download from https://sumo.dlr.de/docs/Downloads.html"
    )


def run_netconvert(
    args: list[str],
    *,
    cwd: Path | None = None,
    timeout: int = 300,
) -> NetconvertResult:
    """Run netconvert with the given arguments.

    Args:
        args: Arguments to pass to netconvert.
        cwd: Working directory for the command.
        timeout: Timeout in seconds.

    Returns:
        NetconvertResult with command output and status.
    """
    cmd = find_netconvert()
    full_cmd = cmd + args

    logger.debug(f"Running: {' '.join(full_cmd)}")

    try:
        result = subprocess.run(
            full_cmd,
            capture_output=True,
            text=True,
            cwd=cwd,
            timeout=timeout,
            check=False,
        )

        return NetconvertResult(
            success=result.returncode == 0,
            command=full_cmd,
            stdout=result.stdout,
            stderr=result.stderr,
            returncode=result.returncode,
        )
    except subprocess.TimeoutExpired:
        logger.error(f"netconvert timed out after {timeout}s")
        return NetconvertResult(
            success=False,
            command=full_cmd,
            stdout="",
            stderr=f"Command timed out after {timeout} seconds",
            returncode=-1,
        )
    except (OSError, subprocess.SubprocessError) as e:
        logger.error(f"Failed to run netconvert: {e}")
        return NetconvertResult(
            success=False,
            command=full_cmd,
            stdout="",
            stderr=str(e),
            returncode=-1,
        )


def extract_traffic_signs(
    osm_file: Path,
    output_file: Path,
    *,
    verbose: bool = False,
    projection: str | None = None,
) -> NetconvertResult:
    """Extract traffic signs from OSM file to XML.

    This is the first pass of the conversion process.

    Args:
        osm_file: Input OSM file.
        output_file: Output XML file for traffic signs.
        verbose: Enable verbose output.
        projection: Optional projection string for netconvert.

    Returns:
        NetconvertResult with command output and status.
    """
    # Use absolute paths for Flatpak compatibility
    osm_file = osm_file.resolve()
    output_file = output_file.resolve()

    args = [
        "--osm-files",
        str(osm_file),
        "--street-sign-output",
        str(output_file),
        "--output-file",
        "/dev/null",
    ]

    # Projection
    if projection:
        args.extend(["--proj", projection])
        args.append("--offset.disable-normalization=true")
    else:
        args.append("--proj.utm")
        args.append("--offset.disable-normalization=false")

    if verbose:
        args.append("--verbose")

    return run_netconvert(args, cwd=osm_file.parent)


def generate_opendrive(
    osm_file: Path,
    signs_file: Path | None,
    output_file: Path,
    *,
    # Geometry & Projection
    lane_width: float = 3.5,
    sidewalk_width: float = 2.0,
    bikelane_width: float = 1.5,
    crossing_width: float = 4.0,
    shape_match_dist: float = 10.0,
    # Junction options
    junction_corner_detail: int = 5,
    junction_scurve_stretch: float = 1.0,
    junction_join_dist: float = 10.0,
    # Feature flags
    guess_roundabouts: bool = True,
    guess_ramps: bool = True,
    guess_tls_signals: bool = True,
    import_sidewalks: bool = True,
    import_crossings: bool = True,
    import_turn_lanes: bool = True,
    import_bike_access: bool = True,
    remove_geometry: bool = True,
    no_turnarounds: bool = True,
    # Logging
    verbose: bool = False,
    aggregate_warnings: int = 5,
    projection: str | None = None,
) -> NetconvertResult:
    """Generate OpenDRIVE file from OSM with traffic signs.

    This is the second pass of the conversion process.

    Args:
        osm_file: Input OSM file.
        signs_file: Traffic signs XML file (from extract_traffic_signs).
        output_file: Output OpenDRIVE (.xodr) file.
        lane_width: Default lane width in meters.
        sidewalk_width: Default sidewalk width in meters.
        bikelane_width: Default bike lane width in meters.
        crossing_width: Default pedestrian crossing width in meters.
        shape_match_dist: Distance for matching shapes to roads.
        junction_corner_detail: Number of points for smoothing junction corners.
        junction_scurve_stretch: S-curve stretch factor for lane changes.
        junction_join_dist: Distance threshold for joining junctions.
        guess_roundabouts: Enable roundabout guessing.
        guess_ramps: Enable ramp guessing.
        guess_tls_signals: Guess traffic light signal positions.
        import_sidewalks: Import sidewalks from OSM.
        import_crossings: Import crossings from OSM.
        import_turn_lanes: Import turn lanes from OSM.
        import_bike_access: Import bike lane access from OSM.
        remove_geometry: Simplify geometry by removing intermediate nodes.
        no_turnarounds: Disable turnaround connections.
        verbose: Enable verbose output.
        aggregate_warnings: Number of similar warnings to aggregate.

    Returns:
        NetconvertResult with command output and status.
    """
    # Use absolute paths for Flatpak compatibility
    osm_file = osm_file.resolve()
    output_file = output_file.resolve()
    if signs_file:
        signs_file = signs_file.resolve()

    args = [
        "--osm-files",
        str(osm_file),
        "--opendrive-output",
        str(output_file),
        # Output options
        f"--opendrive-output.shape-match-dist={shape_match_dist}",
        "--output.street-names=true",
        "--output.original-names=true",
    ]

    # Projection
    if projection:
        args.extend(["--proj", projection])
        args.append("--offset.disable-normalization=true")
    else:
        args.append("--proj.utm")
        args.append("--offset.disable-normalization=false")

    args.extend(
        [
            f"--aggregate-warnings={aggregate_warnings}",
            # Geometry
            f"--geometry.remove={'true' if remove_geometry else 'false'}",
            "--geometry.max-grade.fix=true",
            "--geometry.min-dist=0.5",
            # Junctions
            f"--roundabouts.guess={'true' if guess_roundabouts else 'false'}",
            f"--ramps.guess={'true' if guess_ramps else 'false'}",
            "--edges.join=true",
            "--junctions.join=false",
            f"--junctions.join-dist={junction_join_dist}",
            "--junctions.join-same=10",
            f"--junctions.corner-detail={junction_corner_detail}",
            f"--junctions.scurve-stretch={junction_scurve_stretch}",
            "--rectangular-lane-cut=true",
            f"--no-turnarounds={'true' if no_turnarounds else 'false'}",
            # OSM import settings
            "--osm.all-attributes=true",
            "--osm.layer-elevation=4",
            "--osm.layer-elevation.max-grade=5",
            f"--osm.turn-lanes={'true' if import_turn_lanes else 'false'}",
            "--osm.lane-access=true",
            f"--osm.sidewalks={'true' if import_sidewalks else 'false'}",
            f"--osm.bike-access={'true' if import_bike_access else 'false'}",
            f"--osm.crossings={'true' if import_crossings else 'false'}",
            # Traffic lights
            f"--tls.guess-signals={'true' if guess_tls_signals else 'false'}",
            "--tls.discard-simple=true",
            "--tls.join=true",
            "--tls.group-signals=true",
            "--tls.default-type=actuated",
            # Pedestrians & bicycles (don't guess, use OSM data)
            "--crossings.guess=false",
            "--sidewalks.guess=false",
            "--sidewalks.guess.from-permissions=false",
            "--bikelanes.guess=false",
            "--bikelanes.guess.from-permissions=false",
            # Defaults
            f"--default.lanewidth={lane_width}",
            f"--default.sidewalk-width={sidewalk_width}",
            f"--default.bikelane-width={bikelane_width}",
            f"--default.crossing-width={crossing_width}",
            # Cleanup
            "--remove-edges.isolated=true",
        ]
    )

    # Add polygon files if signs were extracted
    if signs_file and signs_file.exists():
        args.extend(["--polygon-files", str(signs_file)])

    if verbose:
        args.append("--verbose")

    return run_netconvert(args, cwd=osm_file.parent)


def check_netconvert_available() -> bool:
    """Check if netconvert is available on the system.

    Returns:
        True if netconvert is available, False otherwise.
    """
    try:
        find_netconvert()
        return True
    except NetconvertNotFoundError:
        return False


def get_netconvert_version() -> str | None:
    """Get the version of netconvert.

    Returns:
        Version string, or None if not available.
    """
    try:
        result = run_netconvert(["--version"])
        if result.success:
            # Parse version from output like "SUMO netconvert Version 1.x.x"
            for line in result.stdout.split("\n"):
                if "Version" in line:
                    return line.strip()
        return None
    except NetconvertNotFoundError:
        return None
