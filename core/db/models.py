"""
SQLAlchemy 2.x declarative models.
Схема идентична текущим CREATE_TABLES из core/db.py (aiosqlite).
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class UserSession(Base):
    __tablename__ = "user_sessions"

    user_id: Mapped[str] = mapped_column(String, primary_key=True)
    yandex_token: Mapped[str] = mapped_column(Text, nullable=False)
    soundcloud_token: Mapped[str] = mapped_column(Text, nullable=False)
    spotify_token: Mapped[str | None] = mapped_column(Text, nullable=True)
    spotify_refresh_token: Mapped[str | None] = mapped_column(Text, nullable=True)
    role: Mapped[str] = mapped_column(String, nullable=False, server_default="user")
    lang: Mapped[str] = mapped_column(String, nullable=False, server_default="ru")
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), onupdate=func.now())


class Migration(Base):
    __tablename__ = "migrations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(String, nullable=False)
    soundcloud_user_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    status: Mapped[str] = mapped_column(String, nullable=False, server_default="pending")

    tracks: Mapped[list[Track]] = relationship("Track", back_populates="migration")
    playlists: Mapped[list[Playlist]] = relationship("Playlist", back_populates="migration")
    artists: Mapped[list[Artist]] = relationship("Artist", back_populates="migration")


class Track(Base):
    __tablename__ = "tracks"
    __table_args__ = (UniqueConstraint("migration_id", "ym_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    migration_id: Mapped[int] = mapped_column(Integer, ForeignKey("migrations.id"), nullable=False)
    ym_id: Mapped[str] = mapped_column(String, nullable=False)
    ym_artist: Mapped[str] = mapped_column(String, nullable=False)
    ym_title: Mapped[str] = mapped_column(String, nullable=False)
    ym_album: Mapped[str] = mapped_column(String, nullable=False, server_default="")
    sc_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    sc_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    match_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    status: Mapped[str] = mapped_column(String, nullable=False, server_default="pending")

    migration: Mapped[Migration] = relationship("Migration", back_populates="tracks")


class Playlist(Base):
    __tablename__ = "playlists"
    __table_args__ = (UniqueConstraint("migration_id", "ym_kind"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    migration_id: Mapped[int] = mapped_column(Integer, ForeignKey("migrations.id"), nullable=False)
    ym_kind: Mapped[int] = mapped_column(Integer, nullable=False)
    ym_title: Mapped[str] = mapped_column(String, nullable=False)
    sc_playlist_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    status: Mapped[str] = mapped_column(String, nullable=False, server_default="pending")

    migration: Mapped[Migration] = relationship("Migration", back_populates="playlists")
    playlist_tracks: Mapped[list[PlaylistTrack]] = relationship(
        "PlaylistTrack", back_populates="playlist"
    )


class PlaylistTrack(Base):
    __tablename__ = "playlist_tracks"

    playlist_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("playlists.id"), primary_key=True
    )
    ym_track_id: Mapped[str] = mapped_column(String, primary_key=True)
    sc_track_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)

    playlist: Mapped[Playlist] = relationship("Playlist", back_populates="playlist_tracks")


class Artist(Base):
    __tablename__ = "artists"
    __table_args__ = (UniqueConstraint("migration_id", "ym_name"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    migration_id: Mapped[int] = mapped_column(Integer, ForeignKey("migrations.id"), nullable=False)
    ym_name: Mapped[str] = mapped_column(String, nullable=False)
    sc_user_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    sc_username: Mapped[str | None] = mapped_column(String, nullable=True)
    match_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    status: Mapped[str] = mapped_column(String, nullable=False, server_default="pending")

    migration: Mapped[Migration] = relationship("Migration", back_populates="artists")
