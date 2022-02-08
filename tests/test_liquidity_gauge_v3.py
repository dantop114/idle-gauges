import pytest

from brownie import Contract
from random import random, randrange

MAX_UINT256 = 2 ** 256 - 1
WEEK = 7 * 86400
SIX_MONTHS = 86400 * 186
IDLE_WHALE = '0x107a369bc066c77ff061c7d2420618a6ce31b925'

def approx(a, b, precision=1e-10):
    if a == b == 0:
        return True
    return 2 * abs(a - b) / (a + b) <= precision

@pytest.fixture(scope="module")
def idle_token():
    yield Contract.from_explorer('0x875773784Af8135eA0ef43b5a374AaD105c5D39e')

@pytest.fixture(scope="module")
def mock_lp_token(ERC20LP, accounts):
    yield ERC20LP.deploy("Idle YTP token", "YTP-LP", 18, 10 ** 9, {'from': accounts[0]})

@pytest.fixture(scope="module")
def distributor(IdleDistributor, accounts):
    yield IdleDistributor.deploy({"from": accounts[0]})

@pytest.fixture(scope="module")
def voting_escrow():
    # stkIDLE
    yield Contract.from_explorer('0xaac13a116ea7016689993193fce4badc8038136f')

@pytest.fixture(scope="module")
def gauge_controller(GaugeController, accounts, voting_escrow):
    yield GaugeController.deploy(voting_escrow, {'from': accounts[0]})

@pytest.fixture(scope="module")
def distributor_proxy(DistributorProxy, accounts, gauge_controller, distributor):
    yield DistributorProxy.deploy(distributor, gauge_controller, {'from': accounts[0]})

@pytest.fixture(scope="function")
def gauge_v3(LiquidityGaugeV3, accounts, mock_lp_token, distributor_proxy):
    yield LiquidityGaugeV3.deploy(mock_lp_token, distributor_proxy, accounts[0], {"from": accounts[0]})


def test_gauge_integral(accounts, chain, mock_lp_token, distributor, gauge_v3, gauge_controller):
    alice, bob = accounts[:2]

    # Wire up Gauge to the controller to have proper rates and stuff
    gauge_controller.add_type(b"Liquidity", {"from": alice})
    gauge_controller.change_type_weight(0, 10 ** 18, {"from": alice})
    gauge_controller.add_gauge(gauge_v3.address, 0, 10 ** 18, {"from": alice})

    alice_staked = 0
    bob_staked = 0
    integral = 0  # ∫(balance * rate(t) / totalSupply(t) dt)
    checkpoint = chain[-1].timestamp
    checkpoint_rate = distributor.rate()
    checkpoint_supply = 0
    checkpoint_balance = 0

    # Let Alice and Bob have about the same token amount
    mock_lp_token.transfer(bob, mock_lp_token.balanceOf(alice) // 2, {"from": alice})

    def update_integral():
        nonlocal checkpoint, checkpoint_rate, integral, checkpoint_balance, checkpoint_supply

        t1 = chain[-1].timestamp
        rate1 = distributor.rate()
        t_epoch = distributor.startEpochTime()
        if checkpoint >= t_epoch:
            rate_x_time = (t1 - checkpoint) * rate1
        else:
            rate_x_time = (t_epoch - checkpoint) * checkpoint_rate + (t1 - t_epoch) * rate1
        if checkpoint_supply > 0:
            integral += rate_x_time * checkpoint_balance // checkpoint_supply
        checkpoint_rate = rate1
        checkpoint = t1
        checkpoint_supply = gauge_v3.totalSupply()
        checkpoint_balance = gauge_v3.balanceOf(alice)

    # Now let's have a loop where Bob always deposit or withdraws,
    # and Alice does so more rarely
    for i in range(40):
        is_alice = random() < 0.2
        dt = randrange(1, SIX_MONTHS // 5)
        chain.sleep(dt)
        chain.mine()

        # For Bob
        is_withdraw = (i > 0) * (random() < 0.5)
        print("Bob", "withdraws" if is_withdraw else "deposits")
        if is_withdraw:
            amount = randrange(1, gauge_v3.balanceOf(bob) + 1)
            gauge_v3.withdraw(amount, {"from": bob})
            update_integral()
            bob_staked -= amount
        else:
            amount = randrange(1, mock_lp_token.balanceOf(bob) // 10 + 1)
            mock_lp_token.approve(gauge_v3.address, amount, {"from": bob})
            gauge_v3.deposit(amount, {"from": bob})
            update_integral()
            bob_staked += amount

        if is_alice:
            # For Alice
            is_withdraw_alice = (gauge_v3.balanceOf(alice) > 0) * (random() < 0.5)
            print("Alice", "withdraws" if is_withdraw_alice else "deposits")

            if is_withdraw_alice:
                amount_alice = randrange(1, gauge_v3.balanceOf(alice) // 10 + 1)
                gauge_v3.withdraw(amount_alice, {"from": alice})
                update_integral()
                alice_staked -= amount_alice
            else:
                amount_alice = randrange(1, mock_lp_token.balanceOf(alice) + 1)
                mock_lp_token.approve(gauge_v3.address, amount_alice, {"from": alice})
                gauge_v3.deposit(amount_alice, {"from": alice})
                update_integral()
                alice_staked += amount_alice

        # Checking that updating the checkpoint in the same second does nothing
        # Also everyone can update: that should make no difference, too
        if random() < 0.5:
            gauge_v3.user_checkpoint(alice, {"from": alice})
        if random() < 0.5:
            gauge_v3.user_checkpoint(bob, {"from": bob})

        assert gauge_v3.balanceOf(alice) == alice_staked
        assert gauge_v3.balanceOf(bob) == bob_staked
        assert gauge_v3.totalSupply() == alice_staked + bob_staked

        dt = randrange(1, SIX_MONTHS // 20)
        chain.sleep(dt)
        chain.mine()

        gauge_v3.user_checkpoint(alice, {"from": alice})
        update_integral()
        print(i, dt / 86400, integral, gauge_v3.integrate_fraction(alice))
        assert approx(gauge_v3.integrate_fraction(alice), integral)


def test_mining_with_votelock(
    accounts,
    chain,
    mock_lp_token,
    idle_token,
    gauge_v3,
    gauge_controller,
    voting_escrow,
):
    alice, bob = accounts[:2]
    chain.mine(timedelta=2 * WEEK + 5)

    # Wire up Gauge to the controller to have proper rates and stuff
    gauge_controller.add_type(b"Liquidity", {"from": alice})
    gauge_controller.change_type_weight(0, 10 ** 18, {"from": alice})
    gauge_controller.add_gauge(gauge_v3.address, 0, 10 ** 18, {"from": alice})

    assert mock_lp_token.balanceOf(alice) > 0

    # Prepare tokens
    idle_token.transfer(alice, 10 ** 20, {"from": IDLE_WHALE})
    idle_token.transfer(bob, 10 ** 20, {"from": IDLE_WHALE})
    idle_token.approve(voting_escrow, MAX_UINT256, {"from": alice})
    idle_token.approve(voting_escrow, MAX_UINT256, {"from": bob})
    mock_lp_token.transfer(bob, mock_lp_token.balanceOf(alice) // 2, {"from": alice})
    mock_lp_token.approve(gauge_v3.address, MAX_UINT256, {"from": alice})
    mock_lp_token.approve(gauge_v3.address, MAX_UINT256, {"from": bob})

    # Alice deposits to escrow. She now has a BOOST
    t = chain[-1].timestamp
    voting_escrow.create_lock(10 ** 20, t + 2 * WEEK, {"from": alice})

    # Alice and Bob deposit some liquidity
    gauge_v3.deposit(10 ** 21, {"from": alice})
    gauge_v3.deposit(10 ** 21, {"from": bob})

    # Time travel and checkpoint
    chain.sleep(4 * WEEK)
    alice.transfer(alice, 1)
    while True:
        gauge_v3.user_checkpoint(alice, {"from": alice})
        gauge_v3.user_checkpoint(bob, {"from": bob})
        if chain[-1].timestamp != chain[-2].timestamp:
            chain.undo(2)
        else:
            break

    # 4 weeks down the road, balanceOf must be 0
    assert voting_escrow.balanceOf(alice) == 0
    assert voting_escrow.balanceOf(bob) == 0

    # Alice earned 2.5 times more CRV because she vote-locked her CRV
    rewards_alice = gauge_v3.integrate_fraction(alice)
    rewards_bob = gauge_v3.integrate_fraction(bob)
    assert approx(rewards_alice / rewards_bob, 2.5, 1e-5)

    # Time travel / checkpoint: no one has CRV vote-locked
    chain.sleep(4 * WEEK)
    alice.transfer(alice, 1)
    voting_escrow.withdraw({"from": alice})
    while True:
        gauge_v3.user_checkpoint(alice, {"from": alice})
        gauge_v3.user_checkpoint(bob, {"from": bob})
        if chain[-1].timestamp != chain[-2].timestamp:
            chain.undo(2)
        else:
            break
    old_rewards_alice = rewards_alice
    old_rewards_bob = rewards_bob

    # Alice earned the same as Bob now
    rewards_alice = gauge_v3.integrate_fraction(alice)
    rewards_bob = gauge_v3.integrate_fraction(bob)
    d_alice = rewards_alice - old_rewards_alice
    d_bob = rewards_bob - old_rewards_bob
    assert d_alice == d_bob

    # Both Alice and Bob votelock
    while True:
        t = chain[-1].timestamp
        voting_escrow.create_lock(10 ** 20, t + 2 * WEEK, {"from": alice})
        voting_escrow.create_lock(10 ** 20, t + 2 * WEEK, {"from": bob})
        if chain[-1].timestamp != chain[-2].timestamp:
            chain.undo(2)
        else:
            break

    # Time travel / checkpoint: no one has CRV vote-locked
    chain.sleep(4 * WEEK)
    alice.transfer(alice, 1)
    voting_escrow.withdraw({"from": alice})
    voting_escrow.withdraw({"from": bob})
    while True:
        gauge_v3.user_checkpoint(alice, {"from": alice})
        gauge_v3.user_checkpoint(bob, {"from": bob})
        if chain[-1].timestamp != chain[-2].timestamp:
            chain.undo(2)
        else:
            break
    old_rewards_alice = rewards_alice
    old_rewards_bob = rewards_bob

    # Alice earned the same as Bob now
    rewards_alice = gauge_v3.integrate_fraction(alice)
    rewards_bob = gauge_v3.integrate_fraction(bob)
    d_alice = rewards_alice - old_rewards_alice
    d_bob = rewards_bob - old_rewards_bob
    assert d_alice == d_bob