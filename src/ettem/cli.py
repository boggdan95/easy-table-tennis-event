"""Command-line interface for ettem."""

import click


@click.group()
@click.version_option(version="0.1.0")
def cli():
    """Easy Table Tennis Event Manager - CLI tool for managing table tennis tournaments."""
    pass


@cli.command()
@click.option("--csv", required=True, help="Path to players CSV file")
@click.option("--category", required=False, help="Category to import (e.g., U13). If not specified, imports all categories.")
@click.option("--assign-seeds/--no-assign-seeds", default=True, help="Automatically assign seeds based on ranking")
def import_players(csv: str, category: str, assign_seeds: bool):
    """Import players from CSV file.

    CSV must have columns: id,nombre,apellido,genero,pais_cd,ranking_pts,categoria

    Example:
        ettem import-players --csv data/samples/players.csv --category U13
    """
    from ettem.io_csv import import_players_csv, CSVImportError
    from ettem.storage import DatabaseManager, PlayerRepository

    try:
        click.echo(f"📂 Reading CSV file: {csv}")
        if category:
            click.echo(f"🎯 Filtering category: {category}")

        # Import and validate CSV
        players = import_players_csv(csv, category_filter=category)

        if not players:
            click.echo("⚠️  No players to import (check category filter)")
            return

        # Initialize database
        db = DatabaseManager()
        db.create_tables()
        session = db.get_session()
        player_repo = PlayerRepository(session)

        # Save players to database
        click.echo(f"\n💾 Saving {len(players)} players to database...")
        imported_count = 0
        for player in players:
            try:
                player_repo.create(player)
                imported_count += 1
            except Exception as e:
                click.echo(f"❌ Error saving {player.full_name}: {e}")

        click.echo(f"✅ Imported {imported_count} players successfully")

        # Assign seeds if requested
        if assign_seeds:
            categories = set(p.categoria for p in players)
            click.echo(f"\n🎲 Assigning seeds for {len(categories)} categories...")
            for cat in categories:
                player_repo.assign_seeds(cat)
                count = len(player_repo.get_by_category_sorted_by_seed(cat))
                click.echo(f"   ✓ {cat}: {count} players seeded")

        click.echo("\n🎉 Import complete!")

    except CSVImportError as e:
        click.echo(f"❌ CSV Import Error: {e}", err=True)
        raise click.Abort()
    except Exception as e:
        click.echo(f"❌ Unexpected error: {e}", err=True)
        raise


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
