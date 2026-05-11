"""Main converter orchestration module."""

from __future__ import annotations

import tempfile
from dataclasses import dataclass
from pathlib import Path

from loguru import logger

from osm_to_xodr.config import AppSettings, NetconvertSettings
from osm_to_xodr.netconvert import (
    NetconvertNotFoundError,
    check_netconvert_available,
    extract_traffic_signs,
    generate_opendrive,
    get_netconvert_version,
)
from osm_to_xodr.osm_extractor import OSMSignalExtractor, merge_poi_files
from osm_to_xodr.postprocess import (
    clear_generated_junction_connector_lane_marks,
    convert_objects_to_signals,
    detect_divided_road_path_prune_rules,
    detect_split_junction_prune_rules,
    fix_dangling_junction_refs,
    fix_georeference_for_carla,
    prune_generated_junction_connections,
    strip_all_road_marks,
)


@dataclass
class ConversionResult:
    """Result of a complete OSM to XODR conversion."""

    success: bool
    output_file: Path | None
    signs_file: Path | None
    signals_converted: int
    error: str | None = None


def convert_osm_to_xodr(
    input_file: Path,
    output_file: Path | None = None,
    *,
    netconvert_settings: NetconvertSettings | None = None,
    app_settings: AppSettings | None = None,
    verbose: bool | None = None,
    keep_intermediate: bool | None = None,
    projection: str | None = None,
) -> ConversionResult:
    """Convert an OpenStreetMap file to OpenDRIVE format.

    This function orchestrates the full conversion process:
    1. Extract traffic signs from OSM
    2. Generate OpenDRIVE network
    3. Post-process to convert objects to signals

    Args:
        input_file: Path to input .osm file.
        output_file: Path to output .xodr file. If None, uses input name with .xodr extension.
        netconvert_settings: Netconvert parameter settings. Uses defaults if None.
        app_settings: Application settings. Uses defaults if None.
        verbose: Override verbose setting from app_settings.
        keep_intermediate: Override keep_intermediate setting from app_settings.

    Returns:
        ConversionResult with output file path and conversion status.
    """
    # Load settings
    if netconvert_settings is None:
        netconvert_settings = NetconvertSettings()
    if app_settings is None:
        app_settings = AppSettings()

    # Override settings with explicit arguments
    if verbose is not None:
        app_settings.verbose = verbose
    if keep_intermediate is not None:
        app_settings.keep_intermediate = keep_intermediate

    # Validate input
    if not input_file.exists():
        return ConversionResult(
            success=False,
            output_file=None,
            signs_file=None,
            signals_converted=0,
            error=f"Input file not found: {input_file}",
        )

    if input_file.suffix.lower() != ".osm":
        logger.warning(f"Input file does not have .osm extension: {input_file}")

    # Check netconvert availability
    if not check_netconvert_available():
        return ConversionResult(
            success=False,
            output_file=None,
            signs_file=None,
            signals_converted=0,
            error="netconvert not available. Please install SUMO.",
        )

    version = get_netconvert_version()
    if version:
        logger.info(f"Using {version}")

    # Determine output file
    if output_file is None:
        output_file = app_settings.output_dir / input_file.with_suffix(".xodr").name

    # Ensure output directory exists
    output_file.parent.mkdir(parents=True, exist_ok=True)

    # Determine temp directory for intermediate files
    # Use output directory for temp files to ensure Flatpak can access them
    if app_settings.keep_intermediate:
        app_settings.tmp_dir.mkdir(parents=True, exist_ok=True)
        signs_file = app_settings.tmp_dir / f"{input_file.stem}_signs.xml"
        temp_context = None
    else:
        # Use output directory parent for temp files (Flatpak compatible)
        temp_context = tempfile.TemporaryDirectory(dir=output_file.parent)
        signs_file = Path(temp_context.name) / f"{input_file.stem}_signs.xml"

    try:
        # Step 1: Extract traffic signs
        logger.info("Step 1: Extracting traffic signs from OSM...")

        # Always use custom OSMSignalExtractor (matches OSM exactly)
        custom_signs_file = signs_file.with_suffix(".custom.xml")
        extractor = OSMSignalExtractor(input_file)
        extractor.extract(custom_signs_file)

        # Use signs_file for netconvert output
        actual_signs_file: Path | None = None

        if netconvert_settings.import_netconvert_signs:
            logger.info("Extracting additional signs using netconvert...")
            # We skip netconvert's sign extraction because it generates many implicit yield/priority
            # signs at junctions that do not exist as explicit nodes in OSM.
            # But we allow it if the user wants it.
            extract_traffic_signs(
                input_file, signs_file, verbose=app_settings.verbose, projection=projection
            )

            # Merge results from both extractors if they both exist
            if custom_signs_file.exists() and signs_file.exists():
                logger.info(
                    f"Merging custom signs ({custom_signs_file.name}) and netconvert signs ({signs_file.name})"
                )
                actual_signs_file = signs_file.with_suffix(".merged.xml")
                merge_poi_files(custom_signs_file, signs_file, actual_signs_file)
            elif custom_signs_file.exists():
                actual_signs_file = custom_signs_file
            elif signs_file.exists():
                actual_signs_file = signs_file
        else:
            # Use only custom extracted signs to match OSM exactly
            if custom_signs_file.exists():
                logger.debug("Using signs from custom extractor")
                actual_signs_file = custom_signs_file

        if actual_signs_file is None:
            logger.debug("No signs extracted")

        # Step 2: Generate OpenDRIVE

        logger.info("Step 2: Generating OpenDRIVE network...")
        result = generate_opendrive(
            input_file,
            actual_signs_file,
            output_file,
            lane_width=netconvert_settings.lane_width,
            sidewalk_width=netconvert_settings.sidewalk_width,
            bikelane_width=netconvert_settings.bikelane_width,
            crossing_width=netconvert_settings.crossing_width,
            shape_match_dist=netconvert_settings.shape_match_dist,
            junction_corner_detail=netconvert_settings.junction_corner_detail,
            junction_scurve_stretch=netconvert_settings.junction_scurve_stretch,
            junction_join_dist=netconvert_settings.junction_join_dist,
            guess_roundabouts=netconvert_settings.guess_roundabouts,
            guess_ramps=netconvert_settings.guess_ramps,
            guess_tls_signals=netconvert_settings.guess_tls_signals,
            import_sidewalks=netconvert_settings.import_sidewalks,
            import_crossings=netconvert_settings.import_crossings,
            import_turn_lanes=netconvert_settings.import_turn_lanes,
            import_bike_access=netconvert_settings.import_bike_access,
            remove_geometry=netconvert_settings.remove_geometry,
            no_turnarounds=netconvert_settings.no_turnarounds,
            verbose=app_settings.verbose,
            aggregate_warnings=netconvert_settings.aggregate_warnings,
            projection=projection,
        )

        if not result.success:
            return ConversionResult(
                success=False,
                output_file=None,
                signs_file=actual_signs_file if app_settings.keep_intermediate else None,
                signals_converted=0,
                error=f"OpenDRIVE generation failed: {result.stderr}",
            )

        if not output_file.exists():
            return ConversionResult(
                success=False,
                output_file=None,
                signs_file=actual_signs_file if app_settings.keep_intermediate else None,
                signals_converted=0,
                error="OpenDRIVE file was not created",
            )

        logger.info(f"OpenDRIVE network generated: {output_file}")

        # Step 3: Post-process signals
        logger.info("Step 3: Post-processing (Objects -> Signals)...")
        postprocess_result = convert_objects_to_signals(
            output_file,
            country=netconvert_settings.country,
            poi_file=actual_signs_file,
            osm_file=input_file,
            keep_netconvert_signals=netconvert_settings.import_netconvert_signs,
        )

        if not postprocess_result.success:
            logger.warning(f"Post-processing failed: {postprocess_result.error}")
            # Continue anyway - signals are optional enhancement

        # Step 4: Fix geoReference for CARLA compatibility
        logger.info("Step 4: Fixing geoReference for CARLA...")
        # Now uses internal offset calculation via utm library
        fix_georeference_for_carla(output_file)

        # Step 5: Fix roads with dangling (phantom) junction references
        logger.info("Step 5: Fixing dangling junction references...")
        fixes = fix_dangling_junction_refs(output_file)
        if fixes:
            logger.info(f"  Fixed {fixes} dangling junction connection(s)")

        # Step 6: Remove explicitly pruned generated junction connectors
        auto_rules = []
        if netconvert_settings.auto_prune_split_junctions:
            logger.info("Step 6: Detecting split/merge junction pruning candidates...")
            auto_rules = detect_split_junction_prune_rules(input_file)
            auto_rules.extend(detect_divided_road_path_prune_rules(output_file))
            auto_rules = list(dict.fromkeys(auto_rules))

        if auto_rules or netconvert_settings.prune_connection_rules:
            logger.info("Step 6: Pruning generated junction connections...")
            removed = prune_generated_junction_connections(
                output_file,
                netconvert_settings.prune_connection_rules,
                auto_rules=auto_rules,
            )
            if removed:
                logger.info(f"  Removed {removed} generated junction connection(s)")

        # Step 7: Remove ALL road marks — exterior marks are re-added geometrically
        # by OpenDriveRenderer.rewrite_exterior_road_marks at the ORE viewer layer.
        # This two-phase approach prevents spurious markings inside roundabout and
        # junction patch areas while retaining the correct exterior road boundary.
        logger.info("Step 7: Stripping all generated road marks (will be recomputed geometrically)...")
        cleared = strip_all_road_marks(output_file)
        if cleared:
            logger.info(f"  Cleared road marks on {cleared} road(s)")

        logger.info(f"Conversion complete: {output_file}")

        return ConversionResult(
            success=True,
            output_file=output_file,
            signs_file=actual_signs_file if app_settings.keep_intermediate else None,
            signals_converted=postprocess_result.signals_converted,
        )

    except NetconvertNotFoundError as e:
        return ConversionResult(
            success=False,
            output_file=None,
            signs_file=None,
            signals_converted=0,
            error=str(e),
        )
    except Exception as e:
        logger.exception(f"Conversion failed: {e}")
        return ConversionResult(
            success=False,
            output_file=None,
            signs_file=None,
            signals_converted=0,
            error=str(e),
        )
    finally:
        if temp_context is not None:
            temp_context.cleanup()
