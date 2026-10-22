import pytest

from uuma.commerce_store import CommerceStore
from uuma.domain_ownership import require_local_owner
from uuma.forge_journal import ForgeJournalStore
from uuma.knowledge_store import KnowledgeStore
from uuma.lab_inventory import InventoryStore
from uuma.lab_procurement import ProcurementStore


@pytest.mark.parametrize("factory", [KnowledgeStore, InventoryStore, ProcurementStore,
                                      ForgeJournalStore, CommerceStore])
def test_archived_remote_owned_database_cannot_be_bootstrapped(tmp_path, factory):
    database = tmp_path / "domain.db"
    database.with_name(database.name + ".remote-owner.json").write_text("{}")
    with pytest.raises(RuntimeError, match="archived workstation"):
        factory(database)
    assert not database.exists()


def test_unmarked_domain_remains_local(tmp_path):
    require_local_owner(tmp_path / "local.db")
