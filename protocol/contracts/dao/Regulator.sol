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
import "./Comptroller.sol";
import "./Market.sol";
import "../external/Decimal.sol";
import "../Constants.sol";

contract Regulator is Comptroller {
    using SafeMath for uint256;
    using Decimal for Decimal.D256;

    bytes32 private constant FILE = "Regulator";

    uint256[7] private auctionInternals = [0, 0, 0, 0, 0, 0, 2**256 - 1];
    mapping(uint256 => Decimal.D256) private auctionYieldInternals;

    event SupplyIncrease(uint256 indexed epoch, uint256 price, uint256 newRedeemable, uint256 lessDebt, uint256 newBonded);
    event SupplyNeutral(uint256 indexed epoch);

    function step() internal {
        Decimal.D256 memory price = oracleCapture();

        //need to check previous epoch because by the time the Regulator.step function is fired, Bonding.step may have already incremented the epoch

        uint256 prev_epoch = epoch();
        if (prev_epoch > 0) {
            prev_epoch = epoch().sub(1);
        }
        
        Epoch.AuctionState storage auction = getCouponAuctionAtEpoch(prev_epoch);
        //check for outstanding auction, if exists settle it and start a new one, auctions below and above peg
        if (auction.isInit == true){
            // only settle/finish auctions that are not on the crossover boundary
            if ((price.greaterThan(Decimal.one()) && auction.initPrice.greaterThan(Decimal.one())) || (price.lessThan(Decimal.one()) && auction.initPrice.lessThan(Decimal.one()))) {
                settleCouponAuction(prev_epoch);
                finishCouponAuctionAtEpoch(prev_epoch);
            }
            
        }

        initCouponAuction(price);

        if (price.greaterThan(Decimal.one())) {
            growSupply(price);            
            autoRedeemEarlistBestBidder();
            return;
        }

        if (price.lessThan(Decimal.one())) {
            return;
        }

        emit SupplyNeutral(epoch());
    }

    function growSupply(Decimal.D256 memory price) private {
        // supply growth is purly a function sum of the best outstanding bids amounts across auctions at any given time untill they get redeemed
        uint256 newSupply = getSumofBestBidsAcrossCouponAuctions();
        uint256 earliestActiveAuctionEpoch = findEarliestActiveAuctionEpoch();
        setEarliestActiveAuctionEpoch(earliestActiveAuctionEpoch);
        (uint256 newRedeemable, uint256 newBonded) = increaseSupply(newSupply);
        emit SupplyIncrease(epoch(), price.value, newRedeemable, 0, newBonded);
    }

    function oracleCapture() private returns (Decimal.D256 memory) {
        (Decimal.D256 memory price, bool valid) = oracle().capture();

        if (!valid) {
            return Decimal.one();
        }

        return price;
    }
    
    function settleCouponAuction(uint256 settlementEpoch) internal returns (bool success) {
        if (!isCouponAuctionFinished(settlementEpoch)) {
            uint256 maxBidLen = getCouponAuctionBids(settlementEpoch);

            auctionYieldInternals[0] = Decimal.zero();
            auctionYieldInternals[1] = Decimal.zero();
            auctionYieldInternals[2] = Decimal.D256(2**256 - 1);
            
            settleCouponAuctionBidsInOrder(settlementEpoch, maxBidLen);

            // set auction internals
            if (auctionInternals[0] > 0) {
                Decimal.D256 memory avgYieldFilled = auctionYieldInternals[1].div(auctionInternals[0]);
                Decimal.D256 memory avgExpiryFilled = Decimal.ratio(
                    auctionInternals[5],
                    auctionInternals[0]
                );

                //mul(100) to avoid sub 0 results
                Decimal.D256 memory bidToCover = Decimal.ratio(
                    maxBidLen,
                    auctionInternals[0]
                ).mul(100);

                setAuctionStatsFilled(settlementEpoch, auctionInternals[6], auctionInternals[4], avgExpiryFilled, auctionYieldInternals[2], auctionYieldInternals[0], avgYieldFilled);                
                setAuctionInternals(settlementEpoch, bidToCover, auctionInternals[0], auctionInternals[3], auctionInternals[1]);
            }

            // reset contract vars
            auctionInternals = [0, 0, 0, 0, 0, 0, 2**256 - 1];
            auctionYieldInternals[0] = Decimal.zero();
            auctionYieldInternals[1] = Decimal.zero();
            auctionYieldInternals[2] = Decimal.D256(2**256 - 1);
            
            return true;
        } else {
            return false;
        }        
    }

    function settleCouponAuctionBidsInOrder(uint256 epoch, uint256 maxBidLen) internal returns (address) {
        Epoch.AuctionState storage auction = getCouponAuctionAtEpoch(epoch);
        Epoch.CouponBidderState storage bidder = getCouponBidderState(epoch, auction.initBidder);
        return settleCouponAuctionBidsInOrder(epoch, bidder.leftBidder, maxBidLen);
    }

    function settleCouponAuctionBidsInOrder(uint256 epoch, address curBidder, uint256 maxBidLen) internal returns (address) {
        if (curBidder == address(0))
            return address(0);

        Epoch.CouponBidderState storage bidder = getCouponBidderState(epoch, curBidder);


        // iter left
        settleCouponAuctionBidsInOrder(epoch, bidder.leftBidder, maxBidLen);
        
        /*
            current bidder
        */
        
        // reject bids implicit greater than the getCouponRejectBidPtile threshold
        if (Decimal.ratio(auctionInternals[2]+1, maxBidLen).lessThan(Constants.getCouponRejectBidPtile())) {
            // only assgin bids that have not been explicitly selected already? may not need this if settleCouponAuction can only be called once per epoch passed
            if (!getCouponBidderStateSelected(epoch, bidder.bidder)) {
                //must check again if account is able to be assigned
                if (acceptableBidCheck(bidder.bidder, bidder.dollarAmount)){
                    Decimal.D256 memory yield = Decimal.ratio(
                        bidder.couponAmount,
                        bidder.dollarAmount
                    );

                    if (yield.lessThan(auctionYieldInternals[2])) {
                        auctionYieldInternals[2] = yield;
                    } else if (yield.greaterThan(auctionYieldInternals[0])) {
                        auctionYieldInternals[0] = yield;
                    }

                    if (bidder.couponExpiryEpoch < auctionInternals[6]) {
                        auctionInternals[6] = bidder.couponExpiryEpoch;
                    } else if (bidder.couponExpiryEpoch > auctionInternals[4]) {
                        auctionInternals[4] = bidder.couponExpiryEpoch;
                    }
                    
                    auctionYieldInternals[1] = auctionYieldInternals[1].add(yield);
                    auctionInternals[5] += bidder.couponExpiryEpoch;
                    auctionInternals[3] += bidder.couponAmount;
                    auctionInternals[1] += bidder.dollarAmount;
                    
                    burnFromAccount(bidder.bidder, bidder.dollarAmount);
                    incrementBalanceOfCoupons(bidder.bidder, bidder.couponExpiryEpoch, bidder.couponAmount);
                    setCouponBidderStateSelected(epoch, bidder.bidder, auctionInternals[2]);
                    auctionInternals[0]++;
                }
            }
        } 

        //increment bidder index
        auctionInternals[2] += 1;
        
        // iter right
        settleCouponAuctionBidsInOrder(epoch, bidder.rightBidder, maxBidLen);
        
    }

    function autoRedeemEarlistBestBidder() internal returns (bool success) {
        uint256 cur_reedemable = totalRedeemable();
        if (cur_reedemable > 0) {
            uint256 tmp_epoch = findEarliestActiveAuctionPrimaryBidderEpoch();
            address baddr = getBestBidderFromEarliestActiveAuctionEpoch(tmp_epoch);
            uint256 cur_coupon_idx = getCouponsCurrentAssignedIndex(baddr);

            for (uint256 c_idx = 0; c_idx < cur_coupon_idx; c_idx++){
                uint256 exp_epoch = getCouponsAssignedAtEpoch(baddr, c_idx);
                uint256 bal_coupons = balanceOfCoupons(baddr, exp_epoch);

                if (bal_coupons == 0)
                    continue;

                if (cur_reedemable < bal_coupons){
                    bal_coupons = cur_reedemable;
                }
                
                redeemToAccount(baddr, bal_coupons);
                decrementBalanceOfCoupons(baddr, exp_epoch, bal_coupons, "Regulator: Insufficient coupon balance");
                setCouponBidderStateRedeemed(exp_epoch, baddr);
                return true;
            }
            
        } else {
            return false;
        }
    }
}
