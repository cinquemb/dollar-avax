/*
    Copyright 2021 xSD Contributors, based on the works of the Empty Set Squad

    Licensed under the Apache License, Version 2.0 (the "License");
    you may not use this file except in compliance with the License.
    You may obtain a copy of the License at

    http://www.apache.org/licenses/LICENSE-2.0

    Unless required by applicable law or agreed to in writing, software
    distributed under the License is distributed on an "AS IS" BASIS,
    WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
    See the License for the specific language governing permissions and
    limitations under the License.
*/

pragma solidity ^0.5.17;
pragma experimental ABIEncoderV2;

import "./external/Decimal.sol";

library Constants {
    /* Chain */
    uint256 private constant CHAIN_ID = 1; // Mainnet

    /* Oracle */
    address private constant USDC = address(0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48);
    uint256 private constant ORACLE_RESERVE_MINIMUM = 100e6;//100 USDC

    /* Epoch */
    struct EpochStrategy {
        uint256 offset;
        uint256 start;
        uint256 period;
    }

    uint256 private constant EPOCH_OFFSET = 0;
    uint256 private constant EPOCH_START = 1619900000;//1606348800;
    uint256 private constant EPOCH_PERIOD = 7200;

    /* Governance */
    uint256 private constant GOVERNANCE_PERIOD = 36;
    uint256 private constant GOVERNANCE_QUORUM = 20e16; // 20%
    uint256 private constant GOVERNANCE_PROPOSAL_THRESHOLD = 5e15; // 0.5%
    uint256 private constant GOVERNANCE_SUPER_MAJORITY = 66e16; // 66%
    uint256 private constant GOVERNANCE_EMERGENCY_DELAY = 6; // 6 epochs
    uint256 private constant INIT_GOVERNANCE_DELAY = 1080; // 1080 epochs before anyone can propose

    /* DAO */
    // need to use either a gase price oracle or make dynamic to always be pegged to USDC price
    uint256 private constant ADVANCE_INCENTIVE = 150e18; // 150 xSD
    uint256 private constant DAO_EXIT_LOCKUP_EPOCHS = 0; // 0 epochs fluid, can leave at any time

    /* Pool */
    uint256 private constant POOL_EXIT_LOCKUP_EPOCHS = 0; // 0 epochs fluid, can leave at any time

    /* Market */
    uint256 private constant MAX_COUPON_YIELD_MULT = 10; //100K coupouns per 1 dollar burn
    uint256 private constant MAX_COUPON_EXPIRATION_TIME = 946080000; //30 (years) * 365 (days)* 24 (hours) * 60 (min) * 60 (secs)
    uint256 private constant MAX_COUPON_AUCTION_EPOCHS_BEST_BIDDER_SELECTION = 200; //limit to past 200 auctions because of gas constraints on eth mainnet **EXPERIMENTAL** higher limits on avax c-chain
    uint256 private constant REJECT_COUPON_BID_PERCENTILE = 50;//85;//90; //reject the last 90% of bids

    /* Deployed */
    address private constant DAO_ADDRESS = address(0); //TODO: THIS NEEDS TO CHANGE AFTER DEPLOY
    address private constant DOLLAR_ADDRESS = address(0); //TODO: THIS NEEDS TO CHANGE AFTER DEPLOY
    address private constant PAIR_ADDRESS = address(0); //TODO: THIS NEEDS TO CHANGE AFTER DEPLOY

    /**
     * Getters
     */
    function getUsdcAddress() internal pure returns (address) {
        return USDC;
    }

    function getOracleReserveMinimum() internal pure returns (uint256) {
        return ORACLE_RESERVE_MINIMUM;
    }

    function getEpochStrategy() internal pure returns (EpochStrategy memory) {
        return EpochStrategy({
            offset: EPOCH_OFFSET,
            start: EPOCH_START,
            period: EPOCH_PERIOD
        });
    }

    function getGovernanceDelay() public view returns (uint256) {
        return INIT_GOVERNANCE_DELAY;
    }

    function getGovernancePeriod() internal pure returns (uint256) {
        return GOVERNANCE_PERIOD;
    }

    function getGovernanceQuorum() internal pure returns (Decimal.D256 memory) {
        return Decimal.D256({value: GOVERNANCE_QUORUM});
    }

    function getGovernanceProposalThreshold() internal pure returns (Decimal.D256 memory) {
        return Decimal.D256({value: GOVERNANCE_PROPOSAL_THRESHOLD});
    }

    function getGovernanceSuperMajority() internal pure returns (Decimal.D256 memory) {
        return Decimal.D256({value: GOVERNANCE_SUPER_MAJORITY});
    }

    function getGovernanceEmergencyDelay() internal pure returns (uint256) {
        return GOVERNANCE_EMERGENCY_DELAY;
    }

    function getAdvanceIncentive() internal pure returns (uint256) {
        return ADVANCE_INCENTIVE;
    }

    function getDAOExitLockupEpochs() internal pure returns (uint256) {
        return DAO_EXIT_LOCKUP_EPOCHS;
    }

    function getPoolExitLockupEpochs() internal pure returns (uint256) {
        return POOL_EXIT_LOCKUP_EPOCHS;
    }

    function getCouponMaxYieldToBurn() internal pure returns (uint256) {
        return MAX_COUPON_YIELD_MULT;
    }

    function getCouponMaxExpiryTime() internal pure returns (uint256) {
        return MAX_COUPON_EXPIRATION_TIME;
    }

    function getCouponAuctionMaxEpochsBestBidderSelection() internal pure returns (uint256) {
        return MAX_COUPON_AUCTION_EPOCHS_BEST_BIDDER_SELECTION;
    }

    function getCouponRejectBidPtile() internal pure returns (Decimal.D256 memory) {
        return Decimal.ratio(100 - REJECT_COUPON_BID_PERCENTILE, 100);
    }

    function getChainId() internal pure returns (uint256) {
        return CHAIN_ID;
    }

    function getDaoAddress() internal pure returns (address) {
        return DAO_ADDRESS;
    }

    function getDollarAddress() internal pure returns (address) {
        return DOLLAR_ADDRESS;
    }

    function getPairAddress() internal pure returns (address) {
        return PAIR_ADDRESS;
    }
}
