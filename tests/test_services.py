"""Unit tests for ServiceRegistry and Capability flags."""
import pytest

from core.services.base import Capability, MusicServiceAdapter
from core.services.registry import ServiceRegistry


# ---------------------------------------------------------------------------
# Test adapters
# ---------------------------------------------------------------------------

class _ReadAdapter(MusicServiceAdapter):
    id = "test_read"
    name = "Test Read"
    capabilities = Capability.READ_LIKED_TRACKS | Capability.READ_PLAYLISTS | Capability.READ_LIKED_ARTISTS


class _WriteAdapter(MusicServiceAdapter):
    id = "test_write"
    name = "Test Write"
    capabilities = Capability.WRITE_LIKED_TRACKS | Capability.WRITE_PLAYLISTS | Capability.WRITE_LIKED_ARTISTS


class _FileAdapter(MusicServiceAdapter):
    id = "test_file"
    name = "Test File"
    capabilities = Capability.EXPORT_FILE | Capability.IMPORT_FILE


# ---------------------------------------------------------------------------
# Fixture: isolate registry state per test
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def isolated_registry():
    original = dict(ServiceRegistry._adapters)
    ServiceRegistry._adapters.clear()
    yield
    ServiceRegistry._adapters.clear()
    ServiceRegistry._adapters.update(original)


# ---------------------------------------------------------------------------
# Registry operations
# ---------------------------------------------------------------------------

def test_register_and_get():
    adapter = _ReadAdapter()
    ServiceRegistry.register(adapter)
    assert ServiceRegistry.get("test_read") is adapter


def test_get_unknown_raises_key_error():
    with pytest.raises(KeyError, match="nonexistent"):
        ServiceRegistry.get("nonexistent")


def test_all_returns_all_registered():
    r = _ReadAdapter()
    w = _WriteAdapter()
    ServiceRegistry.register(r)
    ServiceRegistry.register(w)
    ids = {a.id for a in ServiceRegistry.all()}
    assert ids == {"test_read", "test_write"}


def test_all_empty_registry():
    assert ServiceRegistry.all() == []


def test_register_overwrites_same_id():
    a1 = _ReadAdapter()
    a2 = _ReadAdapter()
    ServiceRegistry.register(a1)
    ServiceRegistry.register(a2)
    assert ServiceRegistry.get("test_read") is a2
    assert len(ServiceRegistry.all()) == 1


# ---------------------------------------------------------------------------
# Capability.can()
# ---------------------------------------------------------------------------

def test_can_returns_true_for_present_capability():
    adapter = _ReadAdapter()
    assert adapter.can(Capability.READ_LIKED_TRACKS) is True
    assert adapter.can(Capability.READ_PLAYLISTS) is True


def test_can_returns_false_for_absent_capability():
    adapter = _ReadAdapter()
    assert adapter.can(Capability.WRITE_LIKED_TRACKS) is False
    assert adapter.can(Capability.EXPORT_FILE) is False


def test_capability_flag_combination():
    combined = Capability.READ_LIKED_TRACKS | Capability.WRITE_LIKED_TRACKS
    assert bool(combined & Capability.READ_LIKED_TRACKS)
    assert bool(combined & Capability.WRITE_LIKED_TRACKS)
    assert not bool(combined & Capability.READ_PLAYLISTS)


# ---------------------------------------------------------------------------
# get_matrix()
# ---------------------------------------------------------------------------

def test_matrix_empty_registry():
    assert ServiceRegistry.get_matrix() == []


def test_matrix_single_adapter_no_pairs():
    ServiceRegistry.register(_ReadAdapter())
    assert ServiceRegistry.get_matrix() == []


def test_matrix_read_write_pair():
    ServiceRegistry.register(_ReadAdapter())
    ServiceRegistry.register(_WriteAdapter())
    matrix = ServiceRegistry.get_matrix()
    assert len(matrix) == 1
    entry = matrix[0]
    assert entry["from"] == "test_read"
    assert entry["to"] == "test_write"
    assert set(entry["capabilities"]) == {
        "READ_LIKED_TRACKS", "READ_PLAYLISTS", "READ_LIKED_ARTISTS"
    }


def test_matrix_excludes_self_pair():
    ServiceRegistry.register(_ReadAdapter())
    ServiceRegistry.register(_WriteAdapter())
    matrix = ServiceRegistry.get_matrix()
    for entry in matrix:
        assert entry["from"] != entry["to"]


def test_matrix_no_entry_for_file_adapter_only():
    """File adapter has no READ_LIKED_TRACKS / WRITE_LIKED_TRACKS → no matrix entry."""
    ServiceRegistry.register(_FileAdapter())
    ServiceRegistry.register(_ReadAdapter())
    # Read can't write to File (file has EXPORT, not WRITE_LIKED_TRACKS)
    # File can't read from anything (no READ_*)
    matrix = ServiceRegistry.get_matrix()
    assert matrix == []


def test_matrix_multiple_compatible_adapters():
    class _AnotherWrite(MusicServiceAdapter):
        id = "test_write2"
        name = "Test Write 2"
        capabilities = Capability.WRITE_LIKED_TRACKS

    ServiceRegistry.register(_ReadAdapter())
    ServiceRegistry.register(_WriteAdapter())
    ServiceRegistry.register(_AnotherWrite())

    matrix = ServiceRegistry.get_matrix()
    from_read = [e for e in matrix if e["from"] == "test_read"]
    # test_read can go to both test_write and test_write2 (for WRITE_LIKED_TRACKS)
    to_ids = {e["to"] for e in from_read}
    assert "test_write" in to_ids
    assert "test_write2" in to_ids


# ---------------------------------------------------------------------------
# Capability enum completeness
# ---------------------------------------------------------------------------

def test_all_capabilities_are_flags():
    for cap in Capability:
        assert isinstance(cap, Capability)
        assert cap.value > 0


def test_capability_names():
    names = {c.name for c in Capability}
    assert "READ_LIKED_TRACKS" in names
    assert "WRITE_LIKED_TRACKS" in names
    assert "READ_PLAYLISTS" in names
    assert "WRITE_PLAYLISTS" in names
    assert "EXPORT_FILE" in names
    assert "IMPORT_FILE" in names
