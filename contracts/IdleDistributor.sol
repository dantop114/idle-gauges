// SPDX-License-Identifier: MIT
pragma solidity ^0.8.10;

import {Ownable} from "@openzeppelin/access/Ownable.sol";
import {IERC20} from "@openzeppelin/token/ERC20/IERC20.sol";

/// @title IdleDistributor
/// @author dantop114
/// @notice Distribution contract that handles IDLE distribution for Idle Liquidity Gauges.
contract IdleDistributor is Ownable {

    /*///////////////////////////////////////////////////////////////
                        IMMUTABLES AND CONSTANTS
    ///////////////////////////////////////////////////////////////*/

    /// @notice The IDLE token (the token to distribute).
    IERC20 immutable IDLE = IERC20(0x875773784Af8135eA0ef43b5a374AaD105c5D39e);

    /// @notice 6 months in seconds.
    uint256 public constant SIX_MONTHS = 86400 * 186;

    /// @notice Initial distribution rate (as per IIP-*).
    /// @dev 178_200 IDLEs in 6 months.
    uint256 public constant INITIAL_RATE = (178_200 * 10 ** 18) / SIX_MONTHS;

    /// @notice Distribution epoch duration.
    /// @dev 6 months epoch duration.
    uint256 public constant EPOCH_DURATION = SIX_MONTHS;

    /// @notice Initial distribution epoch delay.
    /// @dev This needs to be updated when deploying if 1 day is not enough.
    uint256 public constant INITIAL_DISTRIBUTION_DELAY = 86400;

    /*///////////////////////////////////////////////////////////////
                                STORAGE
    //////////////////////////////////////////////////////////////*/

    /// @notice Distributed IDLEs so far.
    uint256 public distributedIdle;

    /// @notice Running distribution epoch rate.
    uint256 public rate;

    /// @notice Running distribution epoch starting epoch time
    uint256 public startEpochTime = block.timestamp + INITIAL_DISTRIBUTION_DELAY - EPOCH_DURATION;

    /// @notice Total distributed IDLEs when current epoch starts
    uint256 public epochStartingDistributed;

    /// @notice Distribution rate pending for upcoming epoch
    uint256 public pendingRate = INITIAL_RATE;

    /// @notice The DistributorProxy contract
    address public distributorProxy;

    /*///////////////////////////////////////////////////////////////
                                EVENTS
    //////////////////////////////////////////////////////////////*/

    /// @notice Event emitted when distributor proxy is updated
    event UpdateDistributorProxy(address oldProxy, address newProxy);

    /// @notice Event emitted when distribution parameters are updated for upcoming distribution epoch
    event UpdatePendingRate(uint256 rate);

    /// @notice Event emitted when distribution parameters are updated
    event UpdateDistributionParameters(uint256 time, uint256 rate);


    /// @notice Update the DistributorProxy contract
    /// @dev Only owner can call this method
    /// @param proxy New DistributorProxy contract
    function setDistributorProxy(address proxy) external onlyOwner {
        address distributorProxy_ = distributorProxy;
        distributorProxy = proxy;

        emit UpdateDistributorProxy(distributorProxy_, proxy);
    }

    /// @notice Update rate for next epoch
    /// @dev Only owner can call this method
    /// @param newRate Rate for upcoming epoch
    function setPendingRate(uint256 newRate) external onlyOwner {
        pendingRate = newRate;
        emit UpdatePendingRate(newRate);
    }

    /// @dev Updates internal state to match current epoch distribution parameters.
    function _updateDistributionParameters() internal {
        uint256 _pendingRate = pendingRate;

        startEpochTime += EPOCH_DURATION; // set start epoch timestamp
        epochStartingDistributed += (rate * EPOCH_DURATION);


        // note that pending rate is 0 after each distribution epoch end, so we need to
        // set the pending rate each time we plan to extend the gauge program
        rate = _pendingRate; // set new distribution rate
        pendingRate = 0; // reset pending rate
        
        emit UpdateDistributionParameters(startEpochTime, rate);
    }

    /// @notice Updates distribution rate and start timestamp of the epoch.
    /// @dev Callable by anyone if pending epoch should start.
    function updateDistributionParameters() external {
        require(block.timestamp >= startEpochTime + EPOCH_DURATION, "epoch still running");
        _updateDistributionParameters();
    }

    /// @notice Get timestamp of the current distribution epoch start.
    /// @return _startEpochTime Timestamp of the current epoch start.
    function startEpochTimeWrite() external returns (uint256 _startEpochTime) {
        _startEpochTime = startEpochTime;

        if (block.timestamp >= _startEpochTime + EPOCH_DURATION) {
            _updateDistributionParameters();
            _startEpochTime = startEpochTime;
        }
    }

    /// @notice Get timestamp of the next distribution epoch start.
    /// @return _futureEpochTime Timestamp of the next epoch start.
    function futureEpochTimeWrite() external returns (uint256 _futureEpochTime) {
        _futureEpochTime = startEpochTime + EPOCH_DURATION;

        if (block.timestamp >= _futureEpochTime) {
            _updateDistributionParameters();
            _futureEpochTime = startEpochTime + EPOCH_DURATION;
        }
    }

    /// @dev Returns max available IDLEs to distribute.
    /// @dev This will revert until initial distribution begins.
    function _availableToDistribute() internal view returns (uint256) {
        return epochStartingDistributed + (block.timestamp - startEpochTime) * rate;
    }

    /// @notice Returns max available IDLEs for current distribution epoch.
    /// @return Available IDLEs to distribute.
    function availableToDistribute() external view returns (uint256) {
        return _availableToDistribute();
    }

    /// @notice Distribute `amount` IDLE to address `to`.
    /// @param to The account that will receive IDLEs.
    /// @param amount The amount of IDLEs to distribute.
    function distribute(address to, uint256 amount) external {
        require(msg.sender == distributorProxy, "not proxy");
        require(to != address(0), "address zero");

        if (block.timestamp >= startEpochTime + EPOCH_DURATION) {
            _updateDistributionParameters();
        }

        uint256 _distributedIdle = distributedIdle + amount;
        require(_distributedIdle <= _availableToDistribute(), "amount too high");

        distributedIdle = _distributedIdle;
        IDLE.transfer(to, amount);
    }

    /// @notice Emergency method to withdraw funds.
    /// @param to The account that will receive IDLEs.
    /// @param amount The amount of IDLEs to withdraw from contract.
    function emergencyWithdraw(address to, uint256 amount) external onlyOwner {
        IDLE.transfer(to, amount);
    }
}
