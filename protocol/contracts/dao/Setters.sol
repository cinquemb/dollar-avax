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
import "./Getters.sol";

contract Setters is State, Getters {
    using SafeMath for uint256;

    event Transfer(address indexed from, address indexed to, uint256 value);

    /**
     * ERC20 Interface
     */

    function transfer(address recipient, uint256 amount) external pure returns (bool) {
        return false;
    }

    function approve(address spender, uint256 amount) external pure returns (bool) {
        return false;
    }

    function transferFrom(address sender, address recipient, uint256 amount) external pure returns (bool) {
        return false;
    }

    /**
     * Global
     */

    function incrementTotalBonded(uint256 amount) internal {
        _state.balance.bonded = _state.balance.bonded.add(amount);
    }

    function decrementTotalBonded(uint256 amount, string memory reason) internal {
        _state.balance.bonded = _state.balance.bonded.sub(amount, reason);
    }

    function incrementTotalRedeemable(uint256 amount) internal {
        _state.balance.redeemable = _state.balance.redeemable.add(amount);
    }

    function decrementTotalRedeemable(uint256 amount, string memory reason) internal {
        _state.balance.redeemable = _state.balance.redeemable.sub(amount, reason);
    }

    /**
     * Account
     */

    function incrementBalanceOf(address account, uint256 amount) internal {
        _state.accounts[account].balance = _state.accounts[account].balance.add(amount);
        _state.balance.supply = _state.balance.supply.add(amount);

        emit Transfer(address(0), account, amount);
    }

    function decrementBalanceOf(address account, uint256 amount, string memory reason) internal {
        _state.accounts[account].balance = _state.accounts[account].balance.sub(amount, reason);
        _state.balance.supply = _state.balance.supply.sub(amount, reason);

        emit Transfer(account, address(0), amount);
    }

    function incrementBalanceOfStaged(address account, uint256 amount) internal {
        _state.accounts[account].staged = _state.accounts[account].staged.add(amount);
        _state.balance.staged = _state.balance.staged.add(amount);
    }

    function decrementBalanceOfStaged(address account, uint256 amount, string memory reason) internal {
        _state.accounts[account].staged = _state.accounts[account].staged.sub(amount, reason);
        _state.balance.staged = _state.balance.staged.sub(amount, reason);
    }

    function incrementBalanceOfCoupons(address account, uint256 epoch, uint256 amount) internal {
        _state.accounts[account].coupons[epoch] = _state.accounts[account].coupons[epoch].add(amount);
        _state.epochs[epoch].coupons.outstanding = _state.epochs[epoch].coupons.outstanding.add(amount);
        _state.balance.coupons = _state.balance.coupons.add(amount);
        _state.accounts[account].outstanding_coupons = _state.accounts[account].outstanding_coupons.add(amount);
        setCouponsAssignedAtEpoch(account, epoch);
    }

    function decrementBalanceOfCoupons(address account, uint256 epoch, uint256 amount, string memory reason) internal {
        _state.accounts[account].coupons[epoch] = _state.accounts[account].coupons[epoch].sub(amount, reason);
        _state.epochs[epoch].coupons.outstanding = _state.epochs[epoch].coupons.outstanding.sub(amount, reason);
        _state.balance.coupons = _state.balance.coupons.sub(amount, reason);
        _state.accounts[account].outstanding_coupons = _state.accounts[account].outstanding_coupons.sub(amount);
    }

    function incrementCouponsAssignedIndex(address account) internal {
        _state.accounts[account].couponAssginedIndex++;
    }

    function setCouponsAssignedAtEpoch(address account, uint256 epoch) internal {
        uint256 couponAssignedIndex = getCouponsCurrentAssignedIndex(account);
        _state.accounts[account].couponAssignedIndexAtEpoch[couponAssignedIndex] = epoch;
        incrementCouponsAssignedIndex(account);
    }

    function unfreeze(address account) internal {
        _state.accounts[account].fluidUntil = epoch().add(Constants.getDAOExitLockupEpochs());
    }

    function updateAllowanceCoupons(address owner, address spender, uint256 amount) internal {
        _state.accounts[owner].couponAllowances[spender] = amount;
    }

    function decrementAllowanceCoupons(address owner, address spender, uint256 amount, string memory reason) internal {
        _state.accounts[owner].couponAllowances[spender] =
            _state.accounts[owner].couponAllowances[spender].sub(amount, reason);
    }

    /**
     * Epoch
     */
    
    function setRecievedAdvanceIncentive(address advancer) internal {
        _state.hasIncentivized[advancer] = true;
    }

    function incrementEpoch() internal {
        _state.epoch.current = _state.epoch.current.add(1);
        _state.epochs[_state.epoch.current].start = blockTimestamp();
        _state.epochs[_state.epoch.current].period = epochPeriod();
    }

    function snapshotTotalBonded() internal {
        _state.epochs[epoch()].bonded = totalSupply();
    }

    function eliminateOutstandingCoupons(uint256 epoch) internal {
        uint256 outstandingCouponsForEpoch = outstandingCoupons(epoch);
        if(outstandingCouponsForEpoch == 0) {
            return;
        }
        _state.balance.coupons = _state.balance.coupons.sub(outstandingCouponsForEpoch);
        _state.epochs[epoch].coupons.outstanding = 0;
    }

    /**
     * Coupon Auction
     */

    function initCouponAuction(Decimal.D256 memory initPrice) internal  {
        if (_state.epochs[epoch()].auction.isInit == false) {
            _state.epochs[epoch()].auction._totalBids = 0;
            _state.epochs[epoch()].auction.initPrice = initPrice;
            _state.epochs[epoch()].auction.minExpiry = 2**256 -1;
            _state.epochs[epoch()].auction.maxExpiry = 0;
            _state.epochs[epoch()].auction.minYield = 2**256 -1;
            _state.epochs[epoch()].auction.maxYield = 0;
            _state.epochs[epoch()].auction.minDollarAmount = 2**256 -1;
            _state.epochs[epoch()].auction.maxDollarAmount = 0;
            _state.epochs[epoch()].auction.isInit = true;
            _state.epochs[epoch()].auction.latestRedeemedSelectedBidderIndex = 0;
        }
    }

    function finishCouponAuctionAtEpoch(uint256 epoch) internal {
         _state.epochs[epoch].auction.finished = true;
    }

    function setCouponBidderState(uint256 epoch, uint256 index, address bidder, uint256 couponEpochExpiry, uint256 dollarAmount, uint256 maxCouponAmount) internal {
        Epoch.CouponBidderState storage bidderState = _state.epochs[epoch].auction.couponBidderState[bidder];

        bidderState.couponExpiryEpoch = couponEpochExpiry;
        bidderState.dollarAmount = dollarAmount;
        bidderState.couponAmount = maxCouponAmount;
        bidderState.bidder = bidder;

        _state.epochs[epoch].auction.couponBidder[index] = bidder;
    }

    function setCouponBidderStateDistance(uint256 epoch, address bidder, Decimal.D256 memory distance) internal {
        _state.epochs[epoch].auction.couponBidderState[bidder].distance = distance;
    }

    function setCouponBidderStateSelected(uint256 epoch, address bidder, uint256 index) internal {
        _state.epochs[epoch].auction.couponBidderState[bidder].selected = true;
        _state.epochs[epoch].auction.seletedCouponBidder[index] = bidder;
    }
    
    function setCouponBidderStateRedeemed(uint256 epoch, address bidder) internal {
        _state.epochs[epoch].auction.couponBidderState[bidder].redeemed = true;
    }

    function incrementCouponAuctionBids() internal {
        _state.epochs[epoch()].auction._totalBids++;
        _state.epochs[epoch()].actionCount++;
    }
    
    function setCouponAuctionRel(uint256 yield, uint256 couponEpochExpiry, uint256 couponDollarAmount) internal {

        if (yield > _state.epochs[epoch()].auction.maxYield) {
            _state.epochs[epoch()].auction.maxYield = yield;
        }

        if (_state.epochs[epoch()].auction.minYield > yield) {
            _state.epochs[epoch()].auction.minYield = yield;
        }

        if (couponEpochExpiry > _state.epochs[epoch()].auction.maxExpiry) {
            _state.epochs[epoch()].auction.maxExpiry = couponEpochExpiry;
        } 

        if (couponEpochExpiry < _state.epochs[epoch()].auction.minExpiry) {
            _state.epochs[epoch()].auction.minExpiry = couponEpochExpiry;
        }

        if (couponDollarAmount > _state.epochs[epoch()].auction.maxDollarAmount) {
            _state.epochs[epoch()].auction.maxDollarAmount = couponDollarAmount;
        }

        if (couponDollarAmount < _state.epochs[epoch()].auction.minDollarAmount) {
            _state.epochs[epoch()].auction.minDollarAmount = couponDollarAmount;
        }
    }

    function setAuctionStatsFilled(uint256 epoch, uint256 minExpiryFilled, uint256 maxExpiryFilled, Decimal.D256 memory avgExpiryFilled, Decimal.D256 memory minYieldFilled, Decimal.D256 memory maxYieldFilled, Decimal.D256 memory avgYieldFilled) internal {
        _state.epochs[epoch].auction.minExpiryFilled = minExpiryFilled;
        _state.epochs[epoch].auction.maxExpiryFilled = maxExpiryFilled;
        _state.epochs[epoch].auction.avgExpiryFilled = avgExpiryFilled;
        _state.epochs[epoch].auction.minYieldFilled = minYieldFilled;
        _state.epochs[epoch].auction.maxYieldFilled = maxYieldFilled;
        _state.epochs[epoch].auction.avgYieldFilled = avgYieldFilled;
    }

    function setAuctionInternals(uint256 epoch, Decimal.D256 memory bidToCover, uint256 totalFilled, uint256 totalAuctioned, uint256 totalBurned) internal {
        _state.epochs[epoch].auction.bidToCover = bidToCover;
        _state.epochs[epoch].auction.totalFilled = totalFilled;
        _state.epochs[epoch].auction.totalAuctioned = totalAuctioned;
        _state.epochs[epoch].auction.totalBurned = totalBurned;
    }

    function setEarliestActiveAuctionEpoch(uint256 epoch) internal {
        _state.epoch.earliestActiveAuction = epoch;
    }

    function setLatestCouponAuctionRedeemedSelectedBidderIndex(uint256 epoch, uint256 index) internal {
        _state.epochs[epoch].auction.latestRedeemedSelectedBidderIndex = index;
    }
        

    /**
     * Governance
     */

    function createCandidate(address candidate, uint256 period) internal {
        _state.candidates[candidate].start = epoch();
        _state.candidates[candidate].period = period;
    }

    function recordVote(address account, address candidate, Candidate.Vote vote) internal {
        _state.candidates[candidate].votes[account] = vote;
    }

    function incrementApproveFor(address candidate, uint256 amount) internal {
        _state.candidates[candidate].approve = _state.candidates[candidate].approve.add(amount);
    }

    function decrementApproveFor(address candidate, uint256 amount, string memory reason) internal {
        _state.candidates[candidate].approve = _state.candidates[candidate].approve.sub(amount, reason);
    }

    function incrementRejectFor(address candidate, uint256 amount) internal {
        _state.candidates[candidate].reject = _state.candidates[candidate].reject.add(amount);
    }

    function decrementRejectFor(address candidate, uint256 amount, string memory reason) internal {
        _state.candidates[candidate].reject = _state.candidates[candidate].reject.sub(amount, reason);
    }

    function placeLock(address account, address candidate) internal {
        uint256 currentLock = _state.accounts[account].lockedUntil;
        uint256 newLock = startFor(candidate).add(periodFor(candidate));
        if (newLock > currentLock) {
            _state.accounts[account].lockedUntil = newLock;
        }
    }

    function initialized(address candidate) internal {
        _state.candidates[candidate].initialized = true;
    }
}
