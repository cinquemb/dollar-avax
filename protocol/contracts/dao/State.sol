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

import '@pangolindex/exchange-contracts/contracts/pangolin-core/interfaces/IPangolinPair.sol';
import "../token/IDollar.sol";
import "../oracle/IOracle.sol";
import "../external/Decimal.sol";

contract Account {
    enum Status {
        Fluid,
        Frozen,
        Locked
    }

    struct State {
        uint256 staged;
        uint256 balance;
        uint256 fluidUntil;
        uint256 lockedUntil;
        uint256 couponAssginedIndex;
        uint256 outstanding_coupons;
        mapping(uint256 => uint256) coupons;
        mapping(address => uint256) couponAllowances;
        mapping(uint256 => uint256) couponAssignedIndexAtEpoch;
    }
}

contract Epoch {
    struct Global {
        uint256 start;
        uint256 period;
        uint256 current;
        uint256 earliestDeadAuction;
    }

    struct Coupons {
        uint256 outstanding;
    }

    struct CouponBidderState {
        bool selected;
        bool redeemed;
        address bidder;
        address leftBidder;
        address rightBidder;
        uint256 dollarAmount;
        uint256 couponAmount;
        Decimal.D256 distance;
        uint256 couponExpiryEpoch;
        uint256 couponRedemptionIndex;
    }

    struct AuctionState {
        bool isInit;
        bool finished;
        uint256 minYield;
        uint256 maxYield;
        uint256 minExpiry;
        uint256 maxExpiry;
        address initBidder;
        uint256 _totalBids;
        uint256 totalFilled;
        uint256 totalBurned;
        Decimal.D256 initPrice;
        uint256 totalAuctioned;
        uint256 minExpiryFilled;
        uint256 maxExpiryFilled;
        Decimal.D256 bidToCover;
        Decimal.D256 minYieldFilled;
        Decimal.D256 maxYieldFilled;
        Decimal.D256 avgYieldFilled;
        Decimal.D256 avgExpiryFilled;
        uint256 minDollarAmount;
        uint256 maxDollarAmount;
        mapping(uint256 => address) couponBidder;
        uint256 latestRedeemedSelectedBidderIndex;
        mapping(uint256 => address) seletedCouponBidder;
        mapping(address => CouponBidderState) couponBidderState;
    }

    struct State {
        uint256 bonded;
        Coupons coupons;
        AuctionState auction;
    }    
}

contract Candidate {
    enum Vote {
        REJECT,
        APPROVE,
        UNDECIDED
    }

    struct State {
        uint256 start;
        uint256 period;
        uint256 reject;
        uint256 approve;
        bool initialized;
        mapping(address => Vote) votes;
    }
}

contract Storage {
    struct Provider {
        address pool;
        IDollar dollar;
        IOracle oracle;
    }

    struct Balance {
        uint256 supply;
        uint256 bonded;
        uint256 staged;
        uint256 coupons;
        uint256 redeemable;
    }

    struct State {
        Balance balance;
        Provider provider;
        Epoch.Global epoch;
        mapping(uint256 => Epoch.State) epochs;
        mapping(address => bool) hasIncentivized;
        mapping(address => Account.State) accounts;
        mapping(address => Candidate.State) candidates;

    }
}

contract State {
    Storage.State _state;
}
