"""Tests for cloud ID mapping schema additions (Fase 5).

Covers:
- New nullable cloud_*_id columns on TournamentORM, PlayerORM, PairORM, TeamORM
- New EventMappingORM table with (tournament_id, category, event_type) unique constraint
- migrate_cloud_id_mapping() idempotency
"""

import pytest


@pytest.fixture
def db_session(tmp_path):
    """Create a temp SQLite DB with full schema + cloud-mapping migration applied."""
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from ettem.storage import (
        Base,
        migrate_v24_doubles,
        migrate_v25_teams,
        migrate_cloud_id_mapping,
    )

    db_path = tmp_path / "test_cloud.db"
    engine = create_engine(f"sqlite:///{db_path}", echo=False)
    Base.metadata.create_all(engine)
    # Run prior migrations so pairs/teams tables exist for cloud_*_id columns
    migrate_v24_doubles(engine)
    migrate_v25_teams(engine)
    migrate_cloud_id_mapping(engine)
    # Run again to confirm idempotency (must not raise)
    migrate_cloud_id_mapping(engine)

    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()


def test_tournament_cloud_id_column_exists():
    """Importing the ORM should expose the new attribute."""
    from ettem.storage import TournamentORM
    assert hasattr(TournamentORM, "cloud_tournament_id")


def test_player_cloud_id_column_exists():
    from ettem.storage import PlayerORM
    assert hasattr(PlayerORM, "cloud_player_id")


def test_pair_cloud_id_column_exists():
    from ettem.storage import PairORM
    assert hasattr(PairORM, "cloud_pair_id")


def test_team_cloud_id_column_exists():
    from ettem.storage import TeamORM
    assert hasattr(TeamORM, "cloud_team_id")


def test_tournament_with_cloud_id_round_trip(db_session):
    """Create a tournament with a cloud UUID and read it back."""
    from ettem.storage import TournamentORM

    cloud_uuid = "9b3e1f64-0a4d-4d2a-9e2f-5a6c1d7e9b0a"
    t = TournamentORM(name="Open Nacional 2026", cloud_tournament_id=cloud_uuid)
    db_session.add(t)
    db_session.commit()
    db_session.refresh(t)

    fetched = (
        db_session.query(TournamentORM)
        .filter(TournamentORM.cloud_tournament_id == cloud_uuid)
        .first()
    )
    assert fetched is not None
    assert fetched.id == t.id
    assert fetched.cloud_tournament_id == cloud_uuid


def test_player_with_cloud_id_round_trip(db_session):
    """Create a player with cloud_player_id and read it back."""
    from ettem.storage import PlayerORM, TournamentORM

    t = TournamentORM(name="T")
    db_session.add(t)
    db_session.commit()
    db_session.refresh(t)

    player_uuid = "dada1111-dada-1111-dada-111111111111"
    p = PlayerORM(
        nombre="Boggdan",
        apellido="Barrientos",
        genero="M",
        pais_cd="GTM",
        ranking_pts=1200,
        categoria="U15BS",
        tournament_id=t.id,
        cloud_player_id=player_uuid,
    )
    db_session.add(p)
    db_session.commit()
    db_session.refresh(p)

    fetched = (
        db_session.query(PlayerORM)
        .filter(PlayerORM.cloud_player_id == player_uuid)
        .first()
    )
    assert fetched is not None
    assert fetched.cloud_player_id == player_uuid
    assert fetched.full_name == "Boggdan Barrientos"


def test_event_mapping_create_and_fetch(db_session):
    """Create an EventMappingORM row and fetch it by (tournament, category, event_type)."""
    from ettem.storage import EventMappingORM, TournamentORM

    t = TournamentORM(name="T")
    db_session.add(t)
    db_session.commit()
    db_session.refresh(t)

    mapping = EventMappingORM(
        tournament_id=t.id,
        category="U15BS",
        event_type="singles",
        cloud_event_id="eeee1111-eeee-1111-eeee-111111111111",
        cloud_category_id="aaaa1111-aaaa-1111-aaaa-111111111111",
        format="bo5",
    )
    db_session.add(mapping)
    db_session.commit()
    db_session.refresh(mapping)

    fetched = (
        db_session.query(EventMappingORM)
        .filter(
            EventMappingORM.tournament_id == t.id,
            EventMappingORM.category == "U15BS",
            EventMappingORM.event_type == "singles",
        )
        .first()
    )
    assert fetched is not None
    assert fetched.cloud_event_id == "eeee1111-eeee-1111-eeee-111111111111"
    assert fetched.cloud_category_id == "aaaa1111-aaaa-1111-aaaa-111111111111"
    assert fetched.format == "bo5"


def test_event_mapping_unique_constraint(db_session):
    """Duplicate (tournament_id, category, event_type) must be rejected."""
    from sqlalchemy.exc import IntegrityError
    from ettem.storage import EventMappingORM, TournamentORM

    t = TournamentORM(name="T")
    db_session.add(t)
    db_session.commit()
    db_session.refresh(t)

    m1 = EventMappingORM(
        tournament_id=t.id,
        category="U15BS",
        event_type="singles",
        cloud_event_id="eeee1111-eeee-1111-eeee-111111111111",
        cloud_category_id="aaaa1111-aaaa-1111-aaaa-111111111111",
        format="bo5",
    )
    db_session.add(m1)
    db_session.commit()

    m2 = EventMappingORM(
        tournament_id=t.id,
        category="U15BS",
        event_type="singles",
        cloud_event_id="eeee2222-eeee-2222-eeee-222222222222",
        cloud_category_id="aaaa1111-aaaa-1111-aaaa-111111111111",
        format="bo5",
    )
    db_session.add(m2)
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


def test_event_mapping_allows_different_event_types_same_category(db_session):
    """Same (tournament, category) but different event_type must be permitted."""
    from ettem.storage import EventMappingORM, TournamentORM

    t = TournamentORM(name="T")
    db_session.add(t)
    db_session.commit()
    db_session.refresh(t)

    db_session.add_all([
        EventMappingORM(
            tournament_id=t.id,
            category="U15B",
            event_type="singles",
            cloud_event_id="eeee1111-eeee-1111-eeee-111111111111",
            cloud_category_id="aaaa1111-aaaa-1111-aaaa-111111111111",
            format="bo5",
        ),
        EventMappingORM(
            tournament_id=t.id,
            category="U15B",
            event_type="doubles",
            cloud_event_id="eeee2222-eeee-2222-eeee-222222222222",
            cloud_category_id="aaaa1111-aaaa-1111-aaaa-111111111111",
            format="bo5",
        ),
    ])
    db_session.commit()

    rows = (
        db_session.query(EventMappingORM)
        .filter(EventMappingORM.tournament_id == t.id)
        .all()
    )
    assert len(rows) == 2
