/*
    Copyright 2020 Dynamic Dollar Devs, based on the works of the Empty Set Squad

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

    uint256 private totalFilled = 0;
    uint256 private totalBurned = 0;
    uint256 private yieldRelNorm = 1;
    uint256 private expiryRelNorm = 1;
    uint256 private currentBidIdx = 0;
    uint256 private dollarRelNorm = 1;
    uint256 private totalAuctioned = 0;
    uint256 private maxExpiryFilled = 0;
    uint256 private sumExpiryFilled = 0;
    uint256 private sumYieldFilled = 0;
    //need to cap bids per epoch, this may not be  the best way
    //Epoch.CouponBidderState[20000] private bids;
    uint256 private minExpiryFilled = 2**256 - 1;
    Decimal.D256 private maxYieldFilled = Decimal.zero();
    Decimal.D256 private minYieldFilled = Decimal.D256(2**256 - 1);

    event SupplyIncrease(uint256 indexed epoch, uint256 price, uint256 newRedeemable, uint256 lessDebt, uint256 newBonded);
    event SupplyDecrease(uint256 indexed epoch, uint256 price, uint256 newDebt);
    event SupplyNeutral(uint256 indexed epoch);

    function step() internal {
        Decimal.D256 memory price = oracleCapture();

        //need to check previous epoch because by the time the Regulator.step function is fired, Bonding.step may have already incremented the epoch

        uint256 prev_epoch = epoch();
        if (epoch() > 0) {
            prev_epoch = epoch() - 1;
        }
        
        Epoch.AuctionState storage auction = getCouponAuctionAtEpoch(prev_epoch);

        if (price.greaterThan(Decimal.one())) {
            setDebtToZero();

            //check for outstanding auction, if exists cancel it
            if (auction.isInit == true){
                cancelCouponAuctionAtEpoch(prev_epoch);
            }

            /* gas costs error */
            // autoRedeemFromCouponAuctionNew();
            growSupply(price);
            return;
        }

        if (price.lessThan(Decimal.one())) {
            //check for outstanding auction, if exists settle it and start a new one
            if (auction.isInit == true){
                bool isAuctionSettled = settleCouponAuctionNew(prev_epoch);
                finishCouponAuctionAtEpoch(prev_epoch);
            }
            initCouponAuction();
            return;
        }

        emit SupplyNeutral(epoch());
    }

    function growSupply(Decimal.D256 memory price) private {
        // supply growth is purly a function sum of the best outstanding bids amounts across auctions at any given time untill they get redeemed, split between pools
        uint256 newSupply = getSumofBestBidsAcrossCouponAuctionsNew();
        (uint256 newRedeemable, uint256 newBonded) = increaseSupply(newSupply);
        emit SupplyIncrease(epoch(), price.value, newRedeemable, 0, newBonded);
    }

    function limit(Decimal.D256 memory delta, Decimal.D256 memory price) private view returns (Decimal.D256 memory) {
        Decimal.D256 memory supplyChangeLimit = Constants.getSupplyChangeLimit();
        
        uint256 totalRedeemable = totalRedeemable();
        uint256 totalCoupons = totalCoupons();
        if (price.greaterThan(Decimal.one()) && (totalRedeemable < totalCoupons)) {
            supplyChangeLimit = Constants.getCouponSupplyChangeLimit();
        }

        return delta.greaterThan(supplyChangeLimit) ? supplyChangeLimit : delta;
    }

    function oracleCapture() private returns (Decimal.D256 memory) {
        (Decimal.D256 memory price, bool valid) = oracle().capture();

        if (bootstrappingAt(epoch().sub(1))) {
            return Constants.getBootstrappingPrice();
        }
        if (!valid) {
            return Decimal.one();
        }

        return price;
    }
    
    function settleCouponAuctionNew(uint256 settlementEpoch) internal returns (bool success) {
        if (!isCouponAuctionFinished(settlementEpoch) && !isCouponAuctionCanceled(settlementEpoch)) {

            uint256 maxBidLen = getCouponAuctionBids(settlementEpoch);
            settleCouponAuctionBidsInOrder(settlementEpoch, maxBidLen);

            // set auction internals
            if (totalFilled > 0) {
                Decimal.D256 memory avgYieldFilled = Decimal.ratio(
                    sumYieldFilled,
                    totalFilled
                );
                Decimal.D256 memory avgExpiryFilled = Decimal.ratio(
                    sumExpiryFilled,
                    totalFilled
                );

                //mul(100) to avoid sub 0 results
                Decimal.D256 memory bidToCover = Decimal.ratio(
                    maxBidLen,
                    totalFilled
                ).mul(100);

                setMinExpiryFilled(settlementEpoch, minExpiryFilled);
                setMaxExpiryFilled(settlementEpoch, maxExpiryFilled);
                setAvgExpiryFilled(settlementEpoch, avgExpiryFilled.asUint256());
                setMinYieldFilled(settlementEpoch, minYieldFilled.asUint256());
                setMaxYieldFilled(settlementEpoch, maxYieldFilled.asUint256());
                setAvgYieldFilled(settlementEpoch, avgYieldFilled.asUint256());
                setBidToCover(settlementEpoch, bidToCover.asUint256());
                setTotalFilled(settlementEpoch, totalFilled);
                setTotalAuctioned(settlementEpoch, totalAuctioned);
                setTotalBurned(settlementEpoch, totalBurned);
            }

            //reset vars
            totalFilled = 0;
            totalBurned = 0;
            yieldRelNorm = 1;
            expiryRelNorm = 1;
            dollarRelNorm = 1;
            currentBidIdx = 0;
            totalAuctioned = 0;
            maxExpiryFilled = 0;
            sumExpiryFilled = 0;
            sumYieldFilled = 0;
            minExpiryFilled = 2**256 - 1;
            maxYieldFilled = Decimal.zero();
            minYieldFilled = Decimal.D256(2**256 - 1);

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
        //current bidder
        // reject bids implicit greater than the getCouponRejectBidPtile threshold
        if (Decimal.ratio(currentBidIdx+1, maxBidLen).lessThan(Constants.getCouponRejectBidPtile())) {
            // only assgin bids that have not been explicitly selected already? may not need this if settleCouponAuction can only be called once per epoch passed
            if (!getCouponBidderStateSelected(epoch, bidder.bidder)) {
                //must check again if account is able to be assigned
                if (acceptableBidCheck(bidder.bidder, bidder.dollarAmount)){
                    Decimal.D256 memory yield = Decimal.ratio(
                        bidder.couponAmount,
                        bidder.dollarAmount
                    );

                    if (yield.lessThan(minYieldFilled)) {
                        minYieldFilled = yield;
                    } else if (yield.greaterThan(maxYieldFilled)) {
                        maxYieldFilled = yield;
                    }

                    if (bidder.couponExpiryEpoch < minExpiryFilled) {
                        minExpiryFilled = bidder.couponExpiryEpoch;
                    } else if (bidder.couponExpiryEpoch > maxExpiryFilled) {
                        maxExpiryFilled = bidder.couponExpiryEpoch;
                    }
                    
                    sumYieldFilled += yield.asUint256();
                    sumExpiryFilled += bidder.couponExpiryEpoch;
                    totalAuctioned += bidder.couponAmount;
                    totalBurned += bidder.dollarAmount;
                    
                    burnFromAccountSansDebt(bidder.bidder, bidder.dollarAmount);
                    incrementBalanceOfCoupons(bidder.bidder, bidder.couponExpiryEpoch, bidder.couponAmount);
                    setCouponBidderStateSelected(epoch, bidder.bidder, currentBidIdx);
                    totalFilled++;
                }
            }
        } 

        //increment bidder index
        currentBidIdx += 1;
        
        // iter right
        settleCouponAuctionBidsInOrder(epoch, bidder.rightBidder, maxBidLen);
        
    }

    function autoRedeemFromCouponAuctionNew() internal returns (bool success) {
        /*
            WARNING: may need fundemental constraints in order to cap max run time as epocs grow? (i.e totalRedeemable needs to be a function of auction internals of non dead auctions when twap > 1)
            Redeem the best outstanding bidder at any given time
        */

        uint256 earliestDeadauction = 0;
        bool willRedeemableOverflow = false;

        // this will allow us to reloop over best bidders in each auction
        while (totalRedeemable() > 0) {
            // loop over past epochs from the latest `dead` epoch to the current
            for (uint256 d_idx = getEarliestDeadAuctionEpoch(); d_idx < uint256(epoch()); d_idx++) {
                uint256 temp_coupon_auction_epoch = d_idx;
                Epoch.AuctionState storage auction = getCouponAuctionAtEpoch(temp_coupon_auction_epoch);

                // only look at finished auctions
                if (auction.finished) {
                    uint256 totalCurrentlyTriedRedeemed = 0;
                    // loop over bidders in order of assigned per epoch and redeem automatically untill capp is filled for epoch, mark those bids as redeemed, 

                    uint256 latestRedeemedIndex = getLatestCouponAuctionRedeemedSelectedBidderIndex(temp_coupon_auction_epoch);

                    for (uint256 s_idx = latestRedeemedIndex; s_idx < getTotalFilled(temp_coupon_auction_epoch); s_idx++) {
                        address bidderAddress = getCouponBidderStateAssginedAtIndex(temp_coupon_auction_epoch, s_idx);
                        Epoch.CouponBidderState storage bidder = getCouponBidderState(temp_coupon_auction_epoch, bidderAddress);

                        // skip over those bids that have already been redeemed
                        if (bidder.redeemed) {
                            totalCurrentlyTriedRedeemed++;
                            continue;
                        }

                        uint256 totalRedeemable = totalRedeemable();

                        if (totalRedeemable > bidder.couponAmount) {  
                            /* TODO
                                - need to make sure this is "safe" (i.e. it should NOT revert and undo all the previous redemptions, just break and skip while still incrementing total redeemed tried count)
                            */

                            totalCurrentlyTriedRedeemed++;
                            setCouponBidderStateRedeemed(temp_coupon_auction_epoch, bidderAddress);
                            
                            if (bidder.couponExpiryEpoch > uint256(temp_coupon_auction_epoch)) {
                                //check if coupons for epoch are expired already
                                continue;
                            }

                            uint256 couponBalance = balanceOfCoupons(bidderAddress, bidder.couponExpiryEpoch);

                            // mark as redeemd
                            setCouponBidderStateRedeemed(temp_coupon_auction_epoch, bidderAddress);
                            latestRedeemedIndex++;

                            if (couponBalance > 0) {
                                uint256 minCouponAmount = checkMinCouponBalance(couponBalance, bidder.couponAmount);
                                decrementBalanceOfCoupons(bidderAddress, bidder.couponExpiryEpoch, minCouponAmount, "Regulator: Insufficient coupon balance");
                                redeemToAccount(bidderAddress, minCouponAmount);
                                // no point in trying to redeem more if quota for epoch is done
                                willRedeemableOverflow = true;
                            }

                            // time to jump into next auctions bidders
                            break;
                        } else {
                            // no point in trying to redeem more if quota for epoch is done
                            willRedeemableOverflow = true;
                            break;
                        }
                    } 

                    // if all have been tried to be redeemd or expired, mark auction as `dead`
                    if (totalCurrentlyTriedRedeemed == getTotalFilled(temp_coupon_auction_epoch)) {
                        earliestDeadauction = temp_coupon_auction_epoch;
                    }

                    // set the next bidder in line for the next iteration
                    setLatestCouponAuctionRedeemedSelectedBidderIndex(temp_coupon_auction_epoch, latestRedeemedIndex);

                    if (willRedeemableOverflow) {
                        // stop trying to redeem across auctions
                        break;
                    }
                } else {
                    earliestDeadauction = temp_coupon_auction_epoch;
                }
            }

            if (willRedeemableOverflow) {
                // stop trying to redeem across auctions
                break;
            }
        }

        setEarliestDeadAuctionEpoch(earliestDeadauction);
        setCouponAuctionStateDead(earliestDeadauction);

        return true;
    }

    function checkMinCouponBalance(uint256 couponBalance, uint256 couponAmount) internal pure returns (uint256) {
        uint256 minCouponAmount = 0;
        if (couponBalance >= couponAmount) {
            minCouponAmount = couponAmount;
        } else {
            minCouponAmount = couponBalance;
        }
        return minCouponAmount;
    }
}
