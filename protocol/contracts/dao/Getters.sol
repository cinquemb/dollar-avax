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

import "@openzeppelin/contracts/math/SafeMath.sol";
import "./State.sol";
import "../Constants.sol";

contract Getters is State {
    using SafeMath for uint256;
    using Decimal for Decimal.D256;

    bytes32 private constant IMPLEMENTATION_SLOT = 0x360894a13ba1a3210667c828492db98dca3e2076cc3735a920a3ca505d382bbc;

    /**
     * ERC20 Interface
     */

    function name() public view returns (string memory) {
        return "x Set Dollar Stake";
    }

    function symbol() public view returns (string memory) {
        return "xSDS";
    }

    function decimals() public view returns (uint8) {
        return 18;
    }

    function balanceOf(address account) public view returns (uint256) {
        return _state.accounts[account].balance;
    }

    function totalSupply() public view returns (uint256) {
        return _state.balance.supply;
    }

    function allowance(address owner, address spender) external view returns (uint256) {
        return 0;
    }

    /**
     * Global
     */

    function dollar() public view returns (IDollar) {
        return _state.provider.dollar;
    }

    function oracle() public view returns (IOracle) {
        return _state.provider.oracle;
    }

    function pool() public view returns (address) {
        return _state.provider.pool;
    }

    function totalBonded() public view returns (uint256) {
        return _state.balance.bonded;
    }

    function totalStaged() public view returns (uint256) {
        return _state.balance.staged;
    }

    function totalRedeemable() public view returns (uint256) {
        return _state.balance.redeemable;
    }

    function isRedeemable() public view returns (uint256) {
        return _state.balance.redeemable;
    }

    function totalCoupons() public view returns (uint256) {
        return _state.balance.coupons;
    }

    function totalNet() public view returns (uint256) {
        return dollar().totalSupply();
    }

    /**
     * Account
     */

    function balanceOfStaged(address account) public view returns (uint256) {
        return _state.accounts[account].staged;
    }

    function balanceOfBonded(address account) public view returns (uint256) {
        uint256 totalSupply = totalSupply();
        if (totalSupply == 0) {
            return 0;
        }
        return totalBonded().mul(balanceOf(account)).div(totalSupply);
    }

    function balanceOfCoupons(address account, uint256 epoch) public view returns (uint256) {
        if (outstandingCoupons(epoch) == 0) {
            return 0;
        }
        return _state.accounts[account].coupons[epoch];
    }

    function getCouponsAssignedAtEpoch(address account, uint256 couponAssignedIndex) public view returns (uint256) {
        return _state.accounts[account].couponAssignedIndexAtEpoch[couponAssignedIndex];
    }

    function getCouponsCurrentAssignedIndex(address account) public view returns (uint256) {
        return _state.accounts[account].couponAssginedIndex;
    }

    function statusOf(address account) public view returns (Account.Status) {
        if (_state.accounts[account].lockedUntil > epoch()) {
            return Account.Status.Locked;
        }

        return epoch() >= _state.accounts[account].fluidUntil ? Account.Status.Frozen : Account.Status.Fluid;
    }

    function fluidUntil(address account) public view returns (uint256) {
        return _state.accounts[account].fluidUntil;
    }

    function lockedUntil(address account) public view returns (uint256) {
        return _state.accounts[account].lockedUntil;
    }

    function allowanceCoupons(address owner, address spender) public view returns (uint256) {
        return _state.accounts[owner].couponAllowances[spender];
    }

    /**
     * Epoch
     */

    function hasRecievedAdvanceIncentive(address advancer) internal view returns (bool) {
        return _state.hasIncentivized[advancer];
    }
 
    function epoch() public view returns (uint256) {
        return _state.epoch.current;
    }

    function epochTime() public view returns (uint256) {
        Constants.EpochStrategy memory current = Constants.getEpochStrategy();

        return epochTimeWithStrategy(current);
    }

    function epochTimeWithStrategy(Constants.EpochStrategy memory strategy) private view returns (uint256) {
        return blockTimestamp()
            .sub(strategy.start)
            .div(strategy.period)
            .add(strategy.offset);
    }

    // Overridable for testing
    function blockTimestamp() internal view returns (uint256) {
        return block.timestamp;
    }

    function outstandingCoupons(uint256 epoch) public view returns (uint256) {
        return _state.epochs[epoch].coupons.outstanding;
    }

    function outstandingCouponsForAddress(address account) public view returns (uint256) {
        return _state.accounts[account].outstanding_coupons;
    }

    function totalBondedAt(uint256 epoch) public view returns (uint256) {
        return _state.epochs[epoch].bonded;
    }

    function getCouponAuctionAtEpoch(uint256 epoch) internal view returns (Epoch.AuctionState storage) {
        return _state.epochs[epoch].auction;
    }

    function getCouponAuctionStartPriceAtEpoch(uint256 epoch) internal view returns (Decimal.D256 memory) {
        return _state.epochs[epoch].auction.initPrice;
    }
    
    function getCouponAuctionBids(uint256 epoch) internal view returns (uint256) {
        return _state.epochs[epoch].auction._totalBids;
    }

    function getCouponBidderState(uint256 epoch, address bidder) internal view returns (Epoch.CouponBidderState storage) {
        return _state.epochs[epoch].auction.couponBidderState[bidder];
    }

    function getCouponBidderStateSelected(uint256 epoch, address bidder) internal view returns (bool) {
        return _state.epochs[epoch].auction.couponBidderState[bidder].selected;
    }

    function getCouponBidderStateAssginedAtIndex(uint256 epoch, uint256 index) internal view returns (address) {
        return _state.epochs[epoch].auction.seletedCouponBidder[index];
    }

    function getCouponBidderStateIndex(uint256 epoch, uint256 index) internal view returns (address) {
        return _state.epochs[epoch].auction.couponBidder[index];
    }

    function getCouponBidderStateIndexMap(uint256 epoch) internal view returns (mapping(uint256 => address) storage) {
        return _state.epochs[epoch].auction.couponBidder;
    }

    function isCouponAuctionFinished(uint256 epoch) internal view returns (bool){
        return _state.epochs[epoch].auction.finished;
    }

    function getCouponAuctionMinExpiry(uint256 epoch) internal view returns (uint256) {
        return _state.epochs[epoch].auction.minExpiry;
    }

    function getCouponAuctionMaxExpiry(uint256 epoch) internal view returns (uint256) {
        return _state.epochs[epoch].auction.maxExpiry;
    }

    function getCouponAuctionMinYield(uint256 epoch) internal view returns (uint256) {
        return _state.epochs[epoch].auction.minYield;
    }

    function getCouponAuctionMaxYield(uint256 epoch) internal view returns (uint256) {
        return _state.epochs[epoch].auction.maxYield;
    }

    function getCouponAuctionMinDollarAmount(uint256 epoch) internal view returns (uint256) {
        return _state.epochs[epoch].auction.minDollarAmount;
    }

    function getCouponAuctionMaxDollarAmount(uint256 epoch) internal view returns (uint256) {
        return _state.epochs[epoch].auction.maxDollarAmount;
    }

    function getMinExpiryFilled(uint256 epoch) public view returns (uint256) {
        return _state.epochs[epoch].auction.minExpiryFilled;
    }
    
    function getMaxExpiryFilled(uint256 epoch) public view returns (uint256) {
        return _state.epochs[epoch].auction.maxExpiryFilled;
    }
    
    function getAvgExpiryFilled(uint256 epoch) public view returns (uint256) {
        return _state.epochs[epoch].auction.avgExpiryFilled;
    }
    
    function getMinYieldFilled(uint256 epoch) public view returns (uint256) {
        return _state.epochs[epoch].auction.minYieldFilled;
    }
    
    function getMaxYieldFilled(uint256 epoch) public view returns (uint256) {
        return _state.epochs[epoch].auction.maxYieldFilled;
    }
    
    function getAvgYieldFilled(uint256 epoch) public view returns (uint256) {
        return _state.epochs[epoch].auction.avgYieldFilled;
    }
    
    function getBidToCover(uint256 epoch) public view returns (uint256) {
        return _state.epochs[epoch].auction.bidToCover;
    }
    
    function getTotalFilled(uint256 epoch) public view returns (uint256) {
        return _state.epochs[epoch].auction.totalFilled;
    }

    function getTotalAuctioned(uint256 epoch) public view returns (uint256) {
        return _state.epochs[epoch].auction.totalAuctioned;
    }

    function getTotalBurned(uint256 epoch) public view returns (uint256) {
        return _state.epochs[epoch].auction.totalBurned;
    }

    function getEarliestDeadAuctionEpoch() public view returns (uint256) {
        return _state.epoch.earliestDeadAuction;
    }

    function getLatestCouponAuctionRedeemedSelectedBidderIndex(uint256 epoch) public view returns (uint256) {
        return _state.epochs[epoch].auction.latestRedeemedSelectedBidderIndex;
    }

    function getSumofBestBidsAcrossCouponAuctions() public view returns (uint256) {
        // loop over past epochs from the latest `dead` epoch to the current
        /*
            TODO: NEED TO SPLIT THIS INTO RANGES THAT GET COMPUTED BY COUPON BIDDERS AND REDEEMERS?
                - find min and max, chunk by reasonable amount
                - need to figure out how to cache the chuncks
                    - running sum with global state var?
        */
        uint256 sumCoupons = 0;
        uint256 earlist_epoch = getEarliestDeadAuctionEpoch();
        uint256 current_epoch = (epoch().sub(earlist_epoch) > Constants.getCouponAuctionMaxEpochsBestBidderSelection()) ? earlist_epoch.add(Constants.getCouponAuctionMaxEpochsBestBidderSelection()) : epoch();
        //uint256 current_epoch = epoch();
        for (uint256 d_idx = earlist_epoch; d_idx < current_epoch; d_idx++) {
            uint256 temp_coupon_auction_epoch = d_idx;
            Epoch.AuctionState storage auction = getCouponAuctionAtEpoch(temp_coupon_auction_epoch);
            
            if (auction.finished) {
                uint256 max_assigned_bidders = getTotalFilled(temp_coupon_auction_epoch);
                for (uint256 b_idx = 0; b_idx < max_assigned_bidders; b_idx++) {
                    address bidderAddress = getCouponBidderStateAssginedAtIndex(temp_coupon_auction_epoch, b_idx);
                    Epoch.CouponBidderState storage bidder = getCouponBidderState(temp_coupon_auction_epoch, bidderAddress);
                    
                    // skip over those bids that have already been redeemed at least partially
                    // skip over bids that are expired
                    // skip over if balance of coupons for address is zero at epoch
                    if (bidder.redeemed || (temp_coupon_auction_epoch > bidder.couponExpiryEpoch) || (balanceOfCoupons(bidderAddress, bidder.couponExpiryEpoch) < bidder.couponAmount)) {
                        continue;
                    } else {
                        sumCoupons += bidder.couponAmount;
                        break;
                    }
                }
            }
        }

        return sumCoupons;
    }

    function findEarliestActiveAuctionEpoch() internal view returns (uint256) {
        // loop over past epochs from the latest `dead` epoch to the current
        uint256 earliest_non_dead_auction_epoch = 1;
        uint256 earlist_epoch = getEarliestDeadAuctionEpoch();
        uint256 current_epoch = (epoch().sub(earlist_epoch) > Constants.getCouponAuctionMaxEpochsBestBidderSelection()) ? earlist_epoch.add(Constants.getCouponAuctionMaxEpochsBestBidderSelection()) : epoch();
        //uint256 current_epoch = epoch();
        for (uint256 d_idx = earlist_epoch; d_idx < current_epoch; d_idx++) {
            uint256 temp_coupon_auction_epoch = d_idx;
            Epoch.AuctionState storage auction = getCouponAuctionAtEpoch(temp_coupon_auction_epoch);
            earliest_non_dead_auction_epoch = d_idx;
            
            if (auction.finished) {
                uint256 sumCoupons = 0;
                uint256 max_assigned_bidders = getTotalFilled(temp_coupon_auction_epoch);

                for (uint256 b_idx = 0; b_idx < max_assigned_bidders; b_idx++) {
                    address bidderAddress = getCouponBidderStateAssginedAtIndex(temp_coupon_auction_epoch, b_idx);
                    Epoch.CouponBidderState storage bidder = getCouponBidderState(temp_coupon_auction_epoch, bidderAddress);
                    
                    // skip over those bids that have already been redeemed at least partially
                    // skip over bids that are expired
                    // skip over if balance of coupons for address is zero at epoch
                    uint256 currBalanceOfCoupons = balanceOfCoupons(bidderAddress, bidder.couponExpiryEpoch);
                    if (bidder.redeemed || (temp_coupon_auction_epoch > bidder.couponExpiryEpoch) || (currBalanceOfCoupons < bidder.couponAmount)) {
                        continue;
                    } else {
                        sumCoupons += currBalanceOfCoupons;
                        break;
                    }
                }

                if (sumCoupons > 0) {
                    return earliest_non_dead_auction_epoch; 
                }
            }
        }

        return earliest_non_dead_auction_epoch;
    }

    function getBestBidderFromEarliestActiveAuctionEpoch(uint256 epoch) public view returns (address) {
        Epoch.AuctionState storage auction = getCouponAuctionAtEpoch(epoch);    
        if (auction.finished) {
            uint256 max_assigned_bidders = getTotalFilled(epoch);

            for (uint256 b_idx = 0; b_idx < max_assigned_bidders; b_idx++) {
                address bidderAddress = getCouponBidderStateAssginedAtIndex(epoch, b_idx);
                Epoch.CouponBidderState storage bidder = getCouponBidderState(epoch, bidderAddress);
                
                // skip over those bids that have already been redeemed at least partially
                // skip over bids that are expired
                // skip over if balance of coupons for address is zero at epoch
                if (bidder.redeemed || (epoch > bidder.couponExpiryEpoch) || (balanceOfCoupons(bidderAddress, bidder.couponExpiryEpoch) < bidder.couponAmount)) {
                    continue;
                }
                
                return bidderAddress;
            }
        } else {
            return address(0);
        }
    }

    /**
     * Governance
     */

    function recordedVote(address account, address candidate) public view returns (Candidate.Vote) {
        return _state.candidates[candidate].votes[account];
    }

    function startFor(address candidate) public view returns (uint256) {
        return _state.candidates[candidate].start;
    }

    function periodFor(address candidate) public view returns (uint256) {
        return _state.candidates[candidate].period;
    }

    function approveFor(address candidate) public view returns (uint256) {
        return _state.candidates[candidate].approve;
    }

    function rejectFor(address candidate) public view returns (uint256) {
        return _state.candidates[candidate].reject;
    }

    function votesFor(address candidate) public view returns (uint256) {
        return approveFor(candidate).add(rejectFor(candidate));
    }

    function isNominated(address candidate) public view returns (bool) {
        return _state.candidates[candidate].start > 0;
    }

    function isInitialized(address candidate) public view returns (bool) {
        return _state.candidates[candidate].initialized;
    }

    function implementation() public view returns (address impl) {
        bytes32 slot = IMPLEMENTATION_SLOT;
        assembly {
            impl := sload(slot)
        }
    }
}
