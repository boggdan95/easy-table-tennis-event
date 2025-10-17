"""Command-line interface for ettem."""

import click


@click.group()
@click.version_option(version="0.1.0")
def cli():
    """Easy Table Tennis Event Manager - CLI tool for managing table tennis tournaments."""
    pass


@cli.command()
@click.option("--csv", required=True, help="Path to players CSV file")
@click.option("--category", required=True, help="Category to import (e.g., U13)")
def import_players(csv: str, category: str):
    """Import players from CSV file."""
    click.echo(f"Importing players from {csv} for category {category}")
    # TODO: Implement


@cli.command()
@click.option("--config", required=True, help="Path to config YAML file")
@click.option("--out", required=True, help="Output directory")
def build_groups(config: str, out: str):
    """Build groups from imported players."""
    click.echo(f"Building groups with config {config}, output to {out}")
    # TODO: Implement


@cli.command()
def open_panel():
    """Launch web panel for result entry."""
    click.echo("Launching web panel at http://127.0.0.1:8000")
    # TODO: Implement


@cli.command()
@click.option("--out", required=True, help="Output directory")
def compute_standings(out: str):
    """Compute standings from match results."""
    click.echo(f"Computing standings, output to {out}")
    # TODO: Implement


@cli.command()
@click.option("--out", required=True, help="Output directory")
def build_bracket(out: str):
    """Build knockout bracket from standings."""
    click.echo(f"Building bracket, output to {out}")
    # TODO: Implement


@cli.command()
@click.option("--what", type=click.Choice(["groups", "standings", "bracket"]), required=True)
@click.option("--format", type=click.Choice(["csv"]), default="csv")
@click.option("--out", required=True, help="Output directory")
def export(what: str, format: str, out: str):
    """Export data to files."""
    click.echo(f"Exporting {what} as {format} to {out}")
    # TODO: Implement


if __name__ == "__main__":
    cli()
