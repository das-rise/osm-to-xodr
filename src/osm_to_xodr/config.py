"""Configuration management using pydantic-settings."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class NetconvertSettings(BaseSettings):
    """Settings for netconvert parameters.

    These can be configured via:
    - Environment variables with OSM_TO_XODR_ prefix
    - .env file in the current directory
    - CLI arguments (which override environment variables)
    """

    model_config = SettingsConfigDict(
        env_prefix="OSM_TO_XODR_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Lane dimensions
    lane_width: Annotated[
        float,
        Field(default=3.5, description="Default lane width in meters"),
    ]
    sidewalk_width: Annotated[
        float,
        Field(default=2.0, description="Default sidewalk width in meters"),
    ]
    bikelane_width: Annotated[
        float,
        Field(default=1.5, description="Default bike lane width in meters"),
    ]
    crossing_width: Annotated[
        float,
        Field(default=4.0, description="Default pedestrian crossing width in meters"),
    ]

    # Shape matching
    shape_match_dist: Annotated[
        float,
        Field(default=10.0, description="Distance for matching shapes to roads"),
    ]

    # Junction options
    junction_corner_detail: Annotated[
        int,
        Field(default=5, description="Number of points for smoothing junction corners"),
    ]
    junction_scurve_stretch: Annotated[
        float,
        Field(default=1.0, description="S-curve stretch factor for lane changes"),
    ]
    junction_join_dist: Annotated[
        float,
        Field(default=10.0, description="Distance threshold for joining junctions"),
    ]

    # Feature flags
    guess_roundabouts: Annotated[
        bool,
        Field(default=True, description="Enable roundabout guessing"),
    ]
    guess_ramps: Annotated[
        bool,
        Field(default=True, description="Enable ramp guessing"),
    ]
    guess_tls_signals: Annotated[
        bool,
        Field(default=True, description="Guess traffic light signal positions"),
    ]
    import_sidewalks: Annotated[
        bool,
        Field(default=True, description="Import sidewalks from OSM"),
    ]
    import_crossings: Annotated[
        bool,
        Field(default=True, description="Import crossings from OSM"),
    ]
    import_turn_lanes: Annotated[
        bool,
        Field(default=True, description="Import turn lanes from OSM"),
    ]
    import_bike_access: Annotated[
        bool,
        Field(default=True, description="Import bike lane access from OSM"),
    ]
    import_netconvert_signs: Annotated[
        bool,
        Field(
            default=False,
            description="Import signs inferred by netconvert (may include implicit signs)",
        ),
    ]
    remove_geometry: Annotated[
        bool,
        Field(default=True, description="Simplify geometry by removing intermediate nodes"),
    ]
    no_turnarounds: Annotated[
        bool,
        Field(default=True, description="Disable turnaround connections"),
    ]

    # Signal options
    country: Annotated[
        str,
        Field(default="SE", description="Country code for traffic signal mapping (e.g., SE, DE)"),
    ]

    # Logging
    aggregate_warnings: Annotated[
        int,
        Field(default=5, description="Number of similar warnings to aggregate"),
    ]


class AppSettings(BaseSettings):
    """Application-level settings."""

    model_config = SettingsConfigDict(
        env_prefix="OSM_TO_XODR_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Directories
    output_dir: Annotated[
        Path,
        Field(default=Path("output"), description="Directory for output XODR files"),
    ]
    tmp_dir: Annotated[
        Path,
        Field(default=Path("tmp"), description="Directory for intermediate files"),
    ]

    # Behavior
    keep_intermediate: Annotated[
        bool,
        Field(default=False, description="Keep intermediate files after conversion"),
    ]
    verbose: Annotated[
        bool,
        Field(default=False, description="Enable verbose output"),
    ]
    timeout: Annotated[
        int,
        Field(default=300, description="Timeout for netconvert in seconds"),
    ]


def get_netconvert_settings() -> NetconvertSettings:
    """Get netconvert settings from environment/.env file."""
    return NetconvertSettings()


def get_app_settings() -> AppSettings:
    """Get application settings from environment/.env file."""
    return AppSettings()


def generate_env_template() -> str:
    """Generate a template .env file with all settings and their defaults.

    Returns:
        String content for a .env template file.
    """
    lines = [
        "# OSM to OpenDRIVE Converter Configuration",
        "# Environment variables (all optional - defaults shown)",
        "",
        "# === Lane Dimensions ===",
        "# OSM_TO_XODR_LANE_WIDTH=3.5",
        "# OSM_TO_XODR_SIDEWALK_WIDTH=2.0",
        "# OSM_TO_XODR_BIKELANE_WIDTH=1.5",
        "# OSM_TO_XODR_CROSSING_WIDTH=4.0",
        "",
        "# === Shape Matching ===",
        "# OSM_TO_XODR_SHAPE_MATCH_DIST=10.0",
        "",
        "# === Junction Options ===",
        "# OSM_TO_XODR_JUNCTION_CORNER_DETAIL=5",
        "# OSM_TO_XODR_JUNCTION_SCURVE_STRETCH=1.0",
        "# OSM_TO_XODR_JUNCTION_JOIN_DIST=10.0",
        "",
        "# === Feature Flags (true/false) ===",
        "# OSM_TO_XODR_GUESS_ROUNDABOUTS=true",
        "# OSM_TO_XODR_GUESS_RAMPS=true",
        "# OSM_TO_XODR_GUESS_TLS_SIGNALS=true",
        "# OSM_TO_XODR_IMPORT_SIDEWALKS=true",
        "# OSM_TO_XODR_IMPORT_CROSSINGS=true",
        "# OSM_TO_XODR_IMPORT_TURN_LANES=true",
        "# OSM_TO_XODR_IMPORT_BIKE_ACCESS=true",
        "# OSM_TO_XODR_REMOVE_GEOMETRY=true",
        "# OSM_TO_XODR_NO_TURNAROUNDS=true",
        "",
        "# === Logging ===",
        "# OSM_TO_XODR_AGGREGATE_WARNINGS=5",
        "",
        "# === Application Settings ===",
        "# OSM_TO_XODR_OUTPUT_DIR=output",
        "# OSM_TO_XODR_TMP_DIR=tmp",
        "# OSM_TO_XODR_KEEP_INTERMEDIATE=false",
        "# OSM_TO_XODR_VERBOSE=false",
        "# OSM_TO_XODR_TIMEOUT=300",
    ]
    return "\n".join(lines) + "\n"
