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
            // autoRedeemFromCouponAuction();
            growSupply(price);
            return;
        }

        if (price.lessThan(Decimal.one())) {
            //check for outstanding auction, if exists settle it and start a new one
            if (auction.isInit == true){
                bool isAuctionSettled = settleCouponAuction(prev_epoch);
                finishCouponAuctionAtEpoch(prev_epoch);
            }
            initCouponAuction();
            return;
        }

        emit SupplyNeutral(epoch());
    }

    function growSupply(Decimal.D256 memory price) private {
        // supply growth is purly a function sum of the best outstanding bids amounts across auctions at any given time untill they get redeemed, split between pools
        uint256 newSupply = getSumofBestBidsAcrossCouponAuctions();
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

    function sortBidsByDistance(mapping(uint256 => address) storage bids, uint256 maxBidsLen, uint256 epoch) internal {
       quickSort(bids, int(0), int(maxBidsLen- 1), epoch);
    }

    function quickSort(mapping(uint256 => address) storage map, int left, int right, uint256 epoch) internal {
        (int i, int j) = partitionQuickSort(map, left, right, epoch);
        if (left < j)
            quickSort(map, left, j, epoch);
        if (i < right)
            quickSort(map, i, right, epoch);
    }

    function partitionQuickSort (
        mapping(uint256 => address) storage map,
        int left,
        int right, 
        uint256 epoch
    ) internal returns (int, int) {
        // this swaps map values
        int i = left;
        int j = right;

        Decimal.D256 memory pivot = getCouponBidderState(epoch, map[uint256(left + (right - left) / 2)]).distance;
        while (i <= j) {
            Epoch.CouponBidderState storage bidder_i = getCouponBidderState(epoch, map[uint256(i)]);
            Epoch.CouponBidderState storage bidder_j = getCouponBidderState(epoch, map[uint256(j)]);
            while (pivot.lessThan(bidder_j.distance)) j--;
            while (bidder_i.distance.lessThan(pivot)) i++;
            if (i <= j) {
                address tmp = bidder_j.bidder;
                map[uint256(j)] = bidder_i.bidder;
                map[uint256(i)] = tmp;
                i++;
                j--;
            }
        }
        return (i , j);
    }

    function sqrt(Decimal.D256 memory x) internal pure returns (Decimal.D256 memory y) {
        Decimal.D256 memory z = x.add(1).div(2);
        y = x;
        while (z.lessThan(y)) {
            y = z;
            z = x.div(z.add(z)).div(2);
        }
        return y;
    }

    function settleCouponAuction(uint256 settlementEpoch) internal returns (bool success) {
        if (!isCouponAuctionFinished(settlementEpoch) && !isCouponAuctionCanceled(settlementEpoch)) {            
            yieldRelNorm = getCouponAuctionMaxYield(settlementEpoch) - getCouponAuctionMinYield(settlementEpoch);
            expiryRelNorm = getCouponAuctionMaxExpiry(settlementEpoch) - getCouponAuctionMinExpiry(settlementEpoch);    
            dollarRelNorm = getCouponAuctionMaxDollarAmount(settlementEpoch) - getCouponAuctionMinDollarAmount(settlementEpoch);

            mapping(uint256 => address) storage bidMap = getCouponBidderStateIndexMap(settlementEpoch);

            uint256 maxBidLen = getCouponAuctionBids(settlementEpoch);
            
            // loop over bids and compute distance
            for (uint256 i = 0; i < maxBidLen; i++) {
                address bidder_addr = getCouponBidderStateIndex(settlementEpoch, i);
                Epoch.CouponBidderState memory bidder = getCouponBidderState(settlementEpoch, bidder_addr);
                Decimal.D256 memory yieldRel = Decimal.ratio(
                    Decimal.ratio(
                        bidder.couponAmount,
                        bidder.dollarAmount
                    ).asUint256(),
                    yieldRelNorm
                );
                
                Decimal.D256 memory expiryRel = Decimal.ratio(
                    bidder.couponExpiryEpoch,
                    expiryRelNorm
                );
                
                Decimal.D256 memory dollarRelMax = Decimal.ratio(
                    bidder.dollarAmount,
                    dollarRelNorm
                );
                Decimal.D256 memory dollarRel = (Decimal.one().add(Decimal.one())).sub(dollarRelMax);

                Decimal.D256 memory yieldRelSquared = yieldRel.pow(2);
                Decimal.D256 memory expiryRelSquared = expiryRel.pow(2);
                Decimal.D256 memory dollarRelSquared = dollarRel.pow(2);

                Decimal.D256 memory sumOfSquared = yieldRelSquared.add(expiryRelSquared).add(dollarRelSquared);
                Decimal.D256 memory distance;
                if (sumOfSquared.greaterThan(Decimal.zero())) {
                    distance = sqrt(sumOfSquared);
                } else {
                    distance = Decimal.zero();
                }
                bidder.distance = distance;

                bidMap[i] = bidder_addr;
            }

            
            // sort bids
            sortBidsByDistance(bidMap, maxBidLen, settlementEpoch);

            // assign coupons in order of bid preference
            for (uint256 i = 0; i < maxBidLen; i++) {
                Epoch.CouponBidderState memory bidder = getCouponBidderState(settlementEpoch, bidMap[i]);

                // reject bids implicit greater than the getCouponRejectBidPtile threshold
                if (Decimal.ratio(i, maxBidLen).lessThan(Constants.getCouponRejectBidPtile())) {
                    // only assgin bids that have not been explicitly selected already? may not need this if settleCouponAuction can only be called once per epoch passed
                    if (!getCouponBidderStateSelected(settlementEpoch, bidder.bidder)) {
                        Decimal.D256 memory yield = Decimal.ratio(
                            bidder.couponAmount,
                            bidder.dollarAmount
                        );

                        //must check again if account is able to be assigned
                        if (acceptableBidCheck(bidder.bidder, bidder.dollarAmount)){
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
                            
                            uint256 epochExpiry = epoch().add(bidder.couponExpiryEpoch);
                            burnFromAccountSansDebt(bidder.bidder, bidder.dollarAmount);
                            incrementBalanceOfCoupons(bidder.bidder, epochExpiry, bidder.couponAmount);
                            setCouponBidderStateSelected(settlementEpoch, bidder.bidder, i);
                            totalFilled++;
                        }
                    }
                } else {
                    break;
                }
            }

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

    function autoRedeemFromCouponAuction() internal returns (bool success) {
        /*
            WARNING: may need fundemental constraints in order to cap max run time as epocs grow? (i.e totalRedeemable needs to be a function of auction internals of non dead auctions when twap > 1)
        */

        // this will allow us to reloop over best bidders in each auction
        while (totalRedeemable() > 0) {
            bool willRedeemableOverflow = false;
            // loop over past epochs from the latest `dead` epoch to the current
            for (uint256 d_idx = getEarliestDeadAuctionEpoch(); d_idx < uint256(epoch()); d_idx++) {
                uint256 temp_coupon_auction_epoch = d_idx;
                Epoch.AuctionState storage auction = getCouponAuctionAtEpoch(temp_coupon_auction_epoch);

                // skip auctions that have been canceled and or dead or no auction present?
                if (!auction.canceled && !auction.dead && auction.isInit) {
                    if (auction.finished) {

                        uint256 totalCurrentlyTriedRedeemed = 0;
                        // loop over bidders in order of assigned per epoch and redeem automatically untill capp is filled for epoch, mark those bids as redeemed, 

                        for (uint256 s_idx = getLatestCouponAuctionRedeemedSelectedBidderIndex(temp_coupon_auction_epoch); s_idx < getTotalFilled(temp_coupon_auction_epoch); s_idx++) {
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
                                uint256 couponExpiryEpoch = temp_coupon_auction_epoch.add(bidder.couponExpiryEpoch);

                                if (couponExpiryEpoch > uint256(couponExpiryEpoch)) {
                                    //check if coupons for epoch are expired already
                                    totalCurrentlyTriedRedeemed++;
                                    setCouponBidderStateRedeemed(couponExpiryEpoch, bidderAddress);
                                    continue;
                                }

                                uint256 couponBalance = balanceOfCoupons(bidderAddress, couponExpiryEpoch);

                                if (couponBalance > 0) {
                                    uint256 minCouponAmount = 0;
                                    if (couponBalance >= bidder.couponAmount) {
                                        minCouponAmount = bidder.couponAmount;
                                    } else {
                                        minCouponAmount = couponBalance;
                                    }

                                    decrementBalanceOfCoupons(bidderAddress, couponExpiryEpoch, minCouponAmount, "Regulator: Insufficient coupon balance");
                                    
                                    redeemToAccount(bidderAddress, minCouponAmount);
                                    
                                    setCouponBidderStateRedeemed(couponExpiryEpoch, bidderAddress);
                                    // set the next bidder in line
                                    setLatestCouponAuctionRedeemedSelectedBidderIndex(temp_coupon_auction_epoch, s_idx + 1);
                                    totalCurrentlyTriedRedeemed++;

                                    // time to jump into next auctions bidders
                                    break;
                                } else {
                                    // mark as redeemd if couponBalance is zero
                                    setCouponBidderStateRedeemed(couponExpiryEpoch, bidderAddress);
                                    // set the next bidder in line
                                    setLatestCouponAuctionRedeemedSelectedBidderIndex(temp_coupon_auction_epoch, s_idx + 1);
                                    totalCurrentlyTriedRedeemed++;

                                    // time to jump into next auctions bidders
                                    break;
                                }
                            } else {
                                // no point in trying to redeem more if quota for epoch is done
                                willRedeemableOverflow = true;
                                break;
                            }
                        } 

                        // if all have been tried to be redeemd or expired, mark auction as `dead`
                    
                        if (totalCurrentlyTriedRedeemed == getTotalFilled(temp_coupon_auction_epoch)) {
                            setEarliestDeadAuctionEpoch(temp_coupon_auction_epoch);
                            setCouponAuctionStateDead(temp_coupon_auction_epoch);
                        }
                    }
                }
            }

            if (willRedeemableOverflow) {
                // stop trying to redeem across auctions
                break;
            }
        }
    }
}
