"""CLI interface for OSM to OpenDRIVE converter."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Annotated

import typer
from loguru import logger
from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn

from osm_to_xodr import __version__
from osm_to_xodr.config import (
    AppSettings,
    NetconvertSettings,
    generate_env_template,
)
from osm_to_xodr.converter import convert_osm_to_xodr
from osm_to_xodr.netconvert import (
    check_netconvert_available,
    get_netconvert_version,
)

app = typer.Typer(
    name="osm-to-xodr",
    help="Convert OpenStreetMap (.osm) files to OpenDRIVE (.xodr) using SUMO netconvert.",
    add_completion=False,
    rich_markup_mode="rich",
)
console = Console()


def version_callback(value: bool) -> None:
    """Print version and exit."""
    if value:
        console.print(f"osm-to-xodr version {__version__}")
        raise typer.Exit()


def setup_logging(verbose: bool) -> None:
    """Configure loguru logging."""
    logger.remove()  # Remove default handler
    if verbose:
        logger.add(
            sys.stderr,
            format="<green>{time:HH:mm:ss}</green> | <level>{level: <8}</level> | {message}",
            level="DEBUG",
        )
    else:
        logger.add(
            sys.stderr,
            format="<level>{level: <8}</level> | {message}",
            level="INFO",
        )


@app.command()
def convert(
    input_file: Annotated[
        Path,
        typer.Argument(
            help="Input OpenStreetMap (.osm) file",
            exists=True,
            dir_okay=False,
            readable=True,
        ),
    ],
    output_file: Annotated[
        Path | None,
        typer.Option(
            "--output",
            "-o",
            help="Output OpenDRIVE (.xodr) file. Defaults to <input>.xodr in output dir.",
        ),
    ] = None,
    output_dir: Annotated[
        Path,
        typer.Option(
            "--output-dir",
            "-d",
            help="Output directory for generated files.",
        ),
    ] = Path("output"),
    # Lane dimensions
    lane_width: Annotated[
        float,
        typer.Option("--lane-width", help="Default lane width in meters."),
    ] = 3.5,
    sidewalk_width: Annotated[
        float,
        typer.Option("--sidewalk-width", help="Default sidewalk width in meters."),
    ] = 2.0,
    bikelane_width: Annotated[
        float,
        typer.Option("--bikelane-width", help="Default bike lane width in meters."),
    ] = 1.5,
    crossing_width: Annotated[
        float,
        typer.Option("--crossing-width", help="Default pedestrian crossing width in meters."),
    ] = 4.0,
    # Junction options
    junction_corner_detail: Annotated[
        int,
        typer.Option("--junction-corner-detail", help="Number of points for smoothing corners."),
    ] = 5,
    junction_join_dist: Annotated[
        float,
        typer.Option("--junction-join-dist", help="Distance threshold for joining junctions."),
    ] = 2.0,
    # Feature flags
    no_roundabouts: Annotated[
        bool,
        typer.Option("--no-roundabouts", help="Disable roundabout guessing."),
    ] = False,
    no_ramps: Annotated[
        bool,
        typer.Option("--no-ramps", help="Disable ramp guessing."),
    ] = False,
    no_tls: Annotated[
        bool,
        typer.Option("--no-tls", help="Disable traffic light signal guessing."),
    ] = False,
    no_sidewalks: Annotated[
        bool,
        typer.Option("--no-sidewalks", help="Don't import sidewalks from OSM."),
    ] = False,
    no_crossings: Annotated[
        bool,
        typer.Option("--no-crossings", help="Don't import crossings from OSM."),
    ] = False,
    no_turn_lanes: Annotated[
        bool,
        typer.Option("--no-turn-lanes", help="Don't import turn lanes from OSM."),
    ] = False,
    no_bike_access: Annotated[
        bool,
        typer.Option("--no-bike-access", help="Don't import bike lane access from OSM."),
    ] = False,
    import_netconvert_signs: Annotated[
        bool,
        typer.Option("--import-netconvert-signs", help="Import signs inferred by netconvert."),
    ] = False,
    keep_geometry: Annotated[
        bool,
        typer.Option("--keep-geometry", help="Don't simplify geometry."),
    ] = False,
    turnarounds: Annotated[
        bool,
        typer.Option("--turnarounds", help="Enable turnaround connections."),
    ] = False,
    # App options
    keep_intermediate: Annotated[
        bool,
        typer.Option("--keep-intermediate", "-k", help="Keep intermediate files after conversion."),
    ] = False,
    verbose: Annotated[
        bool,
        typer.Option("--verbose", "-v", help="Enable verbose output."),
    ] = False,
    # Signal options
    country: Annotated[
        str,
        typer.Option(
            "--country", "-c", help="Country code for traffic signal mapping (e.g., SE, DE)."
        ),
    ] = "SE",
    _version: Annotated[
        bool | None,
        typer.Option("--version", "-V", callback=version_callback, is_eager=True),
    ] = None,
) -> None:
    """Convert an OpenStreetMap file to OpenDRIVE format.

    This command runs SUMO's netconvert with optimized defaults for
    generating OpenDRIVE files suitable for driving simulators like CARLA.

    [bold]Examples:[/bold]

        osm-to-xodr convert map.osm

        osm-to-xodr convert map.osm -o custom_output.xodr

        osm-to-xodr convert map.osm --lane-width 3.0 --verbose
    """
    setup_logging(verbose)

    # Build settings from CLI arguments (these override .env)
    netconvert_settings = NetconvertSettings(
        lane_width=lane_width,
        sidewalk_width=sidewalk_width,
        bikelane_width=bikelane_width,
        crossing_width=crossing_width,
        junction_corner_detail=junction_corner_detail,
        junction_join_dist=junction_join_dist,
        guess_roundabouts=not no_roundabouts,
        guess_ramps=not no_ramps,
        guess_tls_signals=not no_tls,
        import_sidewalks=not no_sidewalks,
        import_crossings=not no_crossings,
        import_turn_lanes=not no_turn_lanes,
        import_bike_access=not no_bike_access,
        import_netconvert_signs=import_netconvert_signs,
        remove_geometry=not keep_geometry,
        no_turnarounds=not turnarounds,
        country=country,
    )

    app_settings = AppSettings(
        output_dir=output_dir,
        keep_intermediate=keep_intermediate,
        verbose=verbose,
    )

    console.print(
        Panel(
            f"[bold blue]OSM to OpenDRIVE Converter[/bold blue]\n"
            f"Input: [green]{input_file}[/green]",
            title="osm-to-xodr",
        )
    )

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        task = progress.add_task("Converting...", total=None)

        result = convert_osm_to_xodr(
            input_file,
            output_file,
            netconvert_settings=netconvert_settings,
            app_settings=app_settings,
        )

        progress.update(task, completed=True)

    if result.success:
        console.print("\n[green]✓[/green] Conversion successful!")
        console.print(f"  Output: [bold]{result.output_file}[/bold]")
        if result.signals_converted > 0:
            console.print(f"  Signals converted: {result.signals_converted}")
        if result.signs_file:
            console.print(f"  Signs file: {result.signs_file}")
    else:
        console.print("\n[red]✗[/red] Conversion failed!")
        console.print(f"  Error: {result.error}")
        raise typer.Exit(1)


@app.command()
def check() -> None:
    """Check if netconvert is available and show version information."""
    console.print("[bold]Checking netconvert availability...[/bold]\n")

    if check_netconvert_available():
        version = get_netconvert_version()
        console.print("[green]✓[/green] netconvert is available")
        if version:
            console.print(f"  {version}")
    else:
        console.print("[red]✗[/red] netconvert is NOT available")
        console.print("\n[bold]Installation options:[/bold]")
        console.print("  • Linux (apt): [cyan]sudo apt install sumo sumo-tools[/cyan]")
        console.print("  • Linux (Flatpak): [cyan]flatpak install flathub org.eclipse.sumo[/cyan]")
        console.print("  • macOS: [cyan]brew tap dlr-ts/sumo && brew install sumo[/cyan]")
        console.print("  • Windows: Download from https://sumo.dlr.de/docs/Downloads.html")
        raise typer.Exit(1)


@app.command("init-config")
def init_config(
    output: Annotated[
        Path,
        typer.Option("--output", "-o", help="Output file for .env template."),
    ] = Path(".env.example"),
) -> None:
    """Generate a template .env configuration file."""
    content = generate_env_template()
    output.write_text(content)
    console.print(f"[green]✓[/green] Configuration template written to: {output}")
    console.print("\nTo use, copy to .env and uncomment/modify desired settings:")
    console.print(f"  [cyan]cp {output} .env[/cyan]")


if __name__ == "__main__":
    app()
