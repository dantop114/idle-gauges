import pytest
import brownie

WEEK = 86400 * 7
SIX_MONTHS = 86400 * 186


@pytest.fixture(scope="function")
def distributor(IdleDistributor, accounts):
    yield IdleDistributor.deploy({"from": accounts[0]})


# test epoch time distribution


def test_start_epoch_time_write(distributor, chain, accounts):
    creation_time = distributor.startEpochTime()
    chain.sleep(SIX_MONTHS)
    chain.mine()

    # the constant function should not report a changed value
    assert distributor.startEpochTime() == creation_time

    # the state-changing function should show the changed value
    assert distributor.startEpochTimeWrite().return_value == creation_time + SIX_MONTHS

    # after calling the state-changing function, the view function is changed
    assert distributor.startEpochTime() == creation_time + SIX_MONTHS


def test_start_epoch_time_write_same_epoch(distributor, chain, accounts):
    # calling `start_epoch_token_write` within the same epoch should not raise
    distributor.startEpochTimeWrite()
    distributor.startEpochTimeWrite()


def test_update_mining_parameters(distributor, chain, accounts):
    creation_time = distributor.startEpochTime()
    new_epoch = creation_time + SIX_MONTHS - chain.time()
    chain.sleep(new_epoch)
    distributor.updateDistributionParameters({"from": accounts[0]})


def test_update_mining_parameters_same_epoch(distributor, chain, accounts):
    creation_time = distributor.startEpochTime()
    new_epoch = creation_time + SIX_MONTHS - chain.time()
    chain.sleep(new_epoch - 3)
    with brownie.reverts("epoch still running"):
        distributor.updateDistributionParameters({"from": accounts[0]})


# test setters


def test_set_distributor_proxy_only_owner(accounts, distributor):
    with brownie.reverts("Ownable: caller is not the owner"):
        distributor.setDistributorProxy(accounts[2], {"from": accounts[1]})


def test_set_pending_rate_only_admin(accounts, distributor):
    with brownie.reverts("Ownable: caller is not the owner"):
        distributor.setPendingRate(1, {"from": accounts[1]})


# distribution delay


def test_rate(accounts, chain, distributor):
    assert distributor.rate() == 0

    chain.sleep(86401)
    distributor.updateDistributionParameters({"from": accounts[0]})

    assert distributor.rate() > 0


def test_start_epoch_time(accounts, chain, distributor):
    creation_time = distributor.startEpochTime()
    assert creation_time == distributor.tx.timestamp + 86400 - SIX_MONTHS

    chain.sleep(86401)
    distributor.updateDistributionParameters({"from": accounts[0]})

    assert distributor.startEpochTime() == creation_time + SIX_MONTHS


def test_available_to_distribute(accounts, chain, distributor):
    assert distributor.availableToDistribute() == 0

    chain.sleep(86401)

    distributor.updateDistributionParameters({"from": accounts[0]})
    chain.mine(timedelta=SIX_MONTHS)

    # this is not a precise comparison because `availableToDistribute`
    # depends on block.timestamp

    assert distributor.availableToDistribute() > 0
    assert distributor.epochStartingDistributed() == 0    

# test pending rate

def test_pending_rate(accounts, chain, distributor):
    chain.sleep(86401)
    distributor.updateDistributionParameters({"from": accounts[0]})
    distributor.setPendingRate(100, {"from": accounts[0]})
    
    assert distributor.rate() > 0

    chain.mine(timedelta=SIX_MONTHS)
    distributor.updateDistributionParameters({"from": accounts[0]})
    assert distributor.rate() == 100