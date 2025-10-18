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
        click.echo(f"[INFO] Reading CSV file: {csv}")
        if category:
            click.echo(f"[TARGET] Filtering category: {category}")

        # Import and validate CSV
        players = import_players_csv(csv, category_filter=category)

        if not players:
            click.echo("[WARNING]  No players to import (check category filter)")
            return

        # Initialize database
        db = DatabaseManager()
        db.create_tables()
        session = db.get_session()
        player_repo = PlayerRepository(session)

        # Save players to database
        click.echo(f"\n[SAVE] Saving {len(players)} players to database...")
        imported_count = 0
        for player in players:
            try:
                player_repo.create(player)
                imported_count += 1
            except Exception as e:
                click.echo(f"[ERROR] Error saving {player.full_name}: {e}")

        click.echo(f"[SUCCESS] Imported {imported_count} players successfully")

        # Assign seeds if requested
        if assign_seeds:
            categories = set(p.categoria for p in players)
            click.echo(f"\n  Assigning seeds for {len(categories)} categories...")
            for cat in categories:
                player_repo.assign_seeds(cat)
                count = len(player_repo.get_by_category_sorted_by_seed(cat))
                click.echo(f"     {cat}: {count} players seeded")

        click.echo("\n[DONE] Import complete!")

    except CSVImportError as e:
        click.echo(f"[ERROR] CSV Import Error: {e}", err=True)
        raise click.Abort()
    except Exception as e:
        click.echo(f"[ERROR] Unexpected error: {e}", err=True)
        raise


@cli.command()
@click.option("--config", required=True, help="Path to config YAML file")
@click.option("--category", required=True, help="Category to build groups for (e.g., U13)")
@click.option("--out", required=False, help="Output directory for CSV exports")
def build_groups(config: str, category: str, out: str):
    """Build groups from imported players.

    Example:
        ettem build-groups --config config/sample_config.yaml --category U13
    """
    from pathlib import Path
    from ettem.config_loader import load_and_validate_config, ConfigError
    from ettem.group_builder import create_groups
    from ettem.storage import DatabaseManager, PlayerRepository, GroupRepository, MatchRepository
    from ettem.models import Player

    try:
        # Load configuration
        click.echo(f"[INFO] Loading config from: {config}")
        cfg = load_and_validate_config(config)

        # Initialize database
        db = DatabaseManager()
        session = db.get_session()
        player_repo = PlayerRepository(session)
        group_repo = GroupRepository(session)
        match_repo = MatchRepository(session)

        # Get players for this category
        click.echo(f"[TARGET] Loading players for category: {category}")
        player_orms = player_repo.get_by_category_sorted_by_seed(category)

        if not player_orms:
            click.echo(f"[ERROR] No players found for category {category}", err=True)
            click.echo("   Run 'ettem import-players' first", err=True)
            raise click.Abort()

        # Convert ORM to domain models
        players = []
        for p_orm in player_orms:
            player = Player(
                id=p_orm.id,
                nombre=p_orm.nombre,
                apellido=p_orm.apellido,
                genero=p_orm.genero,
                pais_cd=p_orm.pais_cd,
                ranking_pts=p_orm.ranking_pts,
                categoria=p_orm.categoria,
                seed=p_orm.seed,
                original_id=p_orm.original_id,
                tournament_number=p_orm.tournament_number,
                group_id=p_orm.group_id,
                group_number=p_orm.group_number,
                checked_in=p_orm.checked_in,
                notes=p_orm.notes,
            )
            players.append(player)

        click.echo(f"[SUCCESS] Found {len(players)} seeded players")

        # Create groups
        click.echo(f"[BUILD]  Creating groups (preference: {cfg['group_size_preference']} players)...")
        groups, matches = create_groups(
            players=players,
            category=category,
            group_size_preference=cfg['group_size_preference'],
            random_seed=cfg['random_seed'],
        )

        click.echo(f"[SUCCESS] Created {len(groups)} groups with {len(matches)} matches")

        # Save to database
        click.echo("[SAVE] Saving to database...")
        for group, group_matches in zip(groups, [matches[i::len(groups)] for i in range(len(groups))]):
            # Save group
            group_orm = group_repo.create(group)

            # Update players' group assignment
            for player_id in group.player_ids:
                player_orm = player_repo.get_by_id(player_id)
                if player_orm:
                    player_orm.group_id = group_orm.id
                    # Find group_number from players list
                    for p in players:
                        if p.id == player_id:
                            player_orm.group_number = p.group_number
                            break
            player_repo.session.commit()

            # Save matches for this group
            for match in matches:
                if match.player1_id in group.player_ids and match.player2_id in group.player_ids:
                    match.group_id = group_orm.id
                    match_repo.create(match)

        click.echo("[SUCCESS] Groups and fixtures saved to database")

        # Display summary
        click.echo("\n[STATS] Group Summary:")
        for group in groups:
            click.echo(f"  Group {group.name}: {len(group.player_ids)} players")

        click.echo("\n[DONE] Groups created successfully!")

    except ConfigError as e:
        click.echo(f"[ERROR] Configuration Error: {e}", err=True)
        raise click.Abort()
    except Exception as e:
        click.echo(f"[ERROR] Unexpected error: {e}", err=True)
        raise


@cli.command()
@click.option("--host", default="127.0.0.1", help="Host to bind to")
@click.option("--port", default=8000, help="Port to bind to")
def open_panel(host: str, port: int):
    """Launch web panel for result entry.

    Example:
        ettem open-panel
        ettem open-panel --host 0.0.0.0 --port 8080
    """
    import uvicorn
    from ettem.webapp.app import app

    click.echo(f"[INFO] Starting web panel at http://{host}:{port}")
    click.echo(f"[INFO] Press CTRL+C to stop")

    try:
        uvicorn.run(app, host=host, port=port, log_level="info")
    except KeyboardInterrupt:
        click.echo("\n[INFO] Shutting down...")


@cli.command()
@click.option("--category", required=True, help="Category to compute standings for")
def compute_standings(category: str):
    """Compute standings from match results.

    Example:
        ettem compute-standings --category U13
    """
    from ettem.standings import calculate_standings
    from ettem.storage import (
        DatabaseManager,
        GroupRepository,
        MatchRepository,
        StandingRepository,
        PlayerRepository,
    )
    from ettem.models import Match, Set

    try:
        # Initialize database
        db = DatabaseManager()
        session = db.get_session()
        group_repo = GroupRepository(session)
        match_repo = MatchRepository(session)
        standing_repo = StandingRepository(session)
        player_repo = PlayerRepository(session)

        # Get all groups for this category
        click.echo(f"[TARGET] Loading groups for category: {category}")
        group_orms = group_repo.get_by_category(category)

        if not group_orms:
            click.echo(f"[ERROR] No groups found for category {category}", err=True)
            click.echo("   Run 'ettem build-groups' first", err=True)
            raise click.Abort()

        click.echo(f"[SUCCESS] Found {len(group_orms)} groups")

        # Compute standings for each group
        total_standings = 0
        for group_orm in group_orms:
            click.echo(f"\n[STATS] Computing standings for Group {group_orm.name}...")

            # Get matches for this group
            match_orms = match_repo.get_by_group(group_orm.id)

            # Convert to domain models
            matches = []
            for m_orm in match_orms:
                sets = [
                    Set(
                        set_number=s["set_number"],
                        player1_points=s["player1_points"],
                        player2_points=s["player2_points"],
                    )
                    for s in m_orm.sets
                ]
                match = Match(
                    id=m_orm.id,
                    player1_id=m_orm.player1_id,
                    player2_id=m_orm.player2_id,
                    group_id=m_orm.group_id,
                    round_type=m_orm.round_type,
                    round_name=m_orm.round_name,
                    match_number=m_orm.match_number,
                    status=m_orm.status,
                    sets=sets,
                    winner_id=m_orm.winner_id,
                )
                matches.append(match)

            # Calculate standings
            standings = calculate_standings(matches, group_orm.id, player_repo)

            # Delete old standings for this group
            standing_repo.delete_by_group(group_orm.id)

            # Save new standings
            for standing in standings:
                standing_repo.create(standing)

            total_standings += len(standings)

            # Display standings
            for standing in standings:
                player_orm = player_repo.get_by_id(standing.player_id)
                if player_orm:
                    click.echo(
                        f"  {standing.position}. {player_orm.nombre} {player_orm.apellido} - "
                        f"{standing.points_total}pts ({standing.wins}W-{standing.losses}L)"
                    )

        click.echo(f"\n[SUCCESS] Computed {total_standings} standings")
        click.echo("[DONE] Standings calculation complete!")

    except Exception as e:
        click.echo(f"[ERROR] Unexpected error: {e}", err=True)
        raise


@cli.command()
@click.option("--category", required=True, help="Category to build bracket for")
@click.option("--config", required=True, help="Path to config YAML file")
def build_bracket(category: str, config: str):
    """Build knockout bracket from standings.

    Example:
        ettem build-bracket --category U13 --config config/sample_config.yaml
    """
    from ettem.bracket import build_bracket as create_bracket
    from ettem.config_loader import load_and_validate_config
    from ettem.storage import DatabaseManager, StandingRepository, PlayerRepository
    from ettem.models import Player, GroupStanding

    try:
        # Load configuration
        click.echo(f"[INFO] Loading config from: {config}")
        cfg = load_and_validate_config(config)

        # Initialize database
        db = DatabaseManager()
        session = db.get_session()
        standing_repo = StandingRepository(session)
        player_repo = PlayerRepository(session)

        # Get all standings for this category
        click.echo(f"[TARGET] Loading standings for category: {category}")
        all_standings = standing_repo.get_all()

        # Filter by category and get top N per group
        category_standings = []
        advance_per_group = cfg.get("advance_per_group", 2)

        groups_processed = set()
        for standing_orm in all_standings:
            player_orm = player_repo.get_by_id(standing_orm.player_id)
            if not player_orm or player_orm.categoria != category:
                continue

            if standing_orm.group_id not in groups_processed:
                groups_processed.add(standing_orm.group_id)

            # Get qualifiers (top N positions)
            if standing_orm.position and standing_orm.position <= advance_per_group:
                category_standings.append(standing_orm)

        if not category_standings:
            click.echo(f"[ERROR] No standings found for category {category}", err=True)
            click.echo("   Run 'ettem compute-standings' first", err=True)
            raise click.Abort()

        click.echo(f"[SUCCESS] Found {len(category_standings)} qualifiers")

        # Convert to domain models with players
        qualifiers = []
        for standing_orm in category_standings:
            player_orm = player_repo.get_by_id(standing_orm.player_id)
            if player_orm:
                player = Player(
                    id=player_orm.id,
                    nombre=player_orm.nombre,
                    apellido=player_orm.apellido,
                    genero=player_orm.genero,
                    pais_cd=player_orm.pais_cd,
                    ranking_pts=player_orm.ranking_pts,
                    categoria=player_orm.categoria,
                    seed=player_orm.seed,
                )
                standing = GroupStanding(
                    player_id=standing_orm.player_id,
                    group_id=standing_orm.group_id,
                    points_total=standing_orm.points_total,
                    wins=standing_orm.wins,
                    losses=standing_orm.losses,
                    sets_w=standing_orm.sets_w,
                    sets_l=standing_orm.sets_l,
                    points_w=standing_orm.points_w,
                    points_l=standing_orm.points_l,
                    position=standing_orm.position,
                )
                qualifiers.append((player, standing))

        # Build bracket
        click.echo(f"[BUILD]  Building knockout bracket...")
        bracket = create_bracket(
            qualifiers=qualifiers,
            category=category,
            random_seed=cfg["random_seed"],
            player_repo=player_repo,
        )

        click.echo(f"[SUCCESS] Bracket created with {sum(len(slots) for slots in bracket.slots.values())} slots")

        # Display bracket summary
        click.echo("\n[STATS] Bracket Summary:")
        for round_type, slots in bracket.slots.items():
            non_bye_count = sum(1 for s in slots if not s.is_bye)
            bye_count = sum(1 for s in slots if s.is_bye)
            click.echo(f"  {round_type.value}: {non_bye_count} players, {bye_count} BYEs")

            # Check for same-country warnings
            warnings = [s for s in slots if s.same_country_warning]
            if warnings:
                click.echo(f"    [WARNING]  {len(warnings)} slots with same-country warnings")

        click.echo("\n[DONE] Bracket built successfully!")

    except Exception as e:
        click.echo(f"[ERROR] Unexpected error: {e}", err=True)
        raise


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
