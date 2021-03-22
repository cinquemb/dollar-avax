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
import "../Constants.sol";
import "./Implementation.sol";

contract Market is Comptroller {
    using SafeMath for uint256;

    bytes32 private constant FILE = "Market";

    event CouponExpiration(uint256 indexed epoch, uint256 couponsExpired, uint256 lessRedeemable, uint256 lessDebt, uint256 newBonded);
    event CouponRedemption(address indexed account, uint256 indexed epoch, uint256 couponAmount);
    event CouponTransfer(address indexed from, address indexed to, uint256 indexed epoch, uint256 value);
    event CouponApproval(address indexed owner, address indexed spender, uint256 value);
    event CouponBidPlaced(address indexed account, uint256 indexed epoch, uint256 dollarAmount, uint256 maxCouponAmount);
    
    function step() internal {
        // Expire prior epoch coupons
        expireCouponsForEpoch(epoch().sub(1));
    }

    function expireCouponsForEpoch(uint256 epoch) private {
        uint256 couponsForEpoch = outstandingCoupons(epoch);
        (uint256 lessRedeemable, uint256 newBonded) = (0, 0);

        eliminateOutstandingCoupons(epoch);

        uint256 totalRedeemable = totalRedeemable();
        uint256 totalCoupons = totalCoupons();
        if (totalRedeemable > totalCoupons) {
            lessRedeemable = totalRedeemable.sub(totalCoupons);
            burnRedeemable(lessRedeemable);
            (, newBonded) = increaseSupply(lessRedeemable);
        }

        emit CouponExpiration(epoch, couponsForEpoch, lessRedeemable, 0, newBonded);
    }

    function redeemCoupons(uint256 couponEpoch, uint256 couponAmount) external {
        /*
            TODO: this doesn't work, need a way to map bidding epoch to coupon epoch without looping?
        address bestBidderFromEpoch = getBestBidderFromEarliestActiveAuctionEpoch(couponEpoch);

        Require.that(
            bestBidderFromEpoch == msg.sender,
            FILE,
            "Must be current best bidder"
        );*/

        uint256 cur_reedemable = totalRedeemable();

        uint256 realCouponAmount = balanceOfCoupons(msg.sender, couponEpoch);

        Require.that(
            realCouponAmount > 0,
            FILE,
            "Must be greater than 0"
        );

        Require.that(
            couponAmount <= realCouponAmount,
            FILE,
            "Must be lte coupon balance"
        );

        Require.that(
            realCouponAmount <= cur_reedemable,
            FILE,
            "Must be lte total redeemable"
        );

        decrementBalanceOfCoupons(msg.sender, couponEpoch, realCouponAmount, "Market: Insufficient coupon balance");
        redeemToAccount(msg.sender, realCouponAmount);
        setCouponBidderStateRedeemed(couponEpoch, msg.sender);

        emit CouponRedemption(msg.sender, couponEpoch, realCouponAmount);
    }

    function redeemCouponsForAccount(uint256 couponEpoch, uint256 couponAmount, address bidderAddr) external {
        /*
            TODO: this doesn't work, need a way to map bidding epoch to coupon epoch without looping?
        address bestBidderFromEpoch = getBestBidderFromEarliestActiveAuctionEpoch(couponEpoch);

        Require.that(
            bestBidderFromEpoch == bidderAddr,
            FILE,
            "Must be current best bidder"
        );*/

        decrementBalanceOfCoupons(bidderAddr, couponEpoch, couponAmount, "Market: Insufficient coupon balance");
        redeemToAccount(bidderAddr, couponAmount);
        setCouponBidderStateRedeemed(couponEpoch, bidderAddr);

        emit CouponRedemption(bidderAddr, couponEpoch, couponAmount);
    }

    function approveCoupons(address spender, uint256 amount) external {
        require(spender != address(0), "Market: Coupon approve to the zero address");

        updateAllowanceCoupons(msg.sender, spender, amount);

        emit CouponApproval(msg.sender, spender, amount);
    }

    function transferCoupons(address sender, address recipient, uint256 epoch, uint256 amount) external {
        require(sender != address(0), "Market: Coupon transfer from the zero address");
        require(recipient != address(0), "Market: Coupon transfer to the zero address");

        decrementBalanceOfCoupons(sender, epoch, amount, "Market: Insufficient coupon balance");
        incrementBalanceOfCoupons(recipient, epoch, amount);

        if (msg.sender != sender && allowanceCoupons(sender, msg.sender) != uint256(-1)) {
            decrementAllowanceCoupons(sender, msg.sender, amount, "Market: Insufficient coupon approval");
        }

        emit CouponTransfer(sender, recipient, epoch, amount);
    }

    function placeCouponAuctionBid(uint256 couponEpochExpiry, uint256 dollarAmount, uint256 maxCouponAmount) external returns (bool) {
        Require.that(
            couponEpochExpiry > 0,
            FILE,
            "Must have non-zero expiry"
        );
        
        Require.that(
            dollarAmount > 0,
            FILE,
            "Must bid non-zero amount"
        );
        
        Require.that(
            maxCouponAmount > 0,
            FILE,
            "Must bid on non-zero amount"
        );

        Require.that(
            acceptableBidCheck(msg.sender, dollarAmount),
            FILE,
            "Must have enough in account"
        );

        uint256 yield = maxCouponAmount.div(dollarAmount);
        uint256 maxYield = Constants.getCouponMaxYieldToBurn();
        uint256 maxExpiry = Constants.getCouponMaxExpiryTime().div(Constants.getEpochStrategy().period);

        Require.that(
            maxYield >= yield,
            FILE,
            "Must be under maxYield"
        );

        Require.that(
            maxExpiry >= couponEpochExpiry,
            FILE,
            "Must be under maxExpiry"
        );

        if (epochTime() > epoch()) {
            // if currently below reference price, make bidder advance epoch
            Decimal.D256 memory price = oracle().latestPrice();
            if (price.lessThan(Decimal.one())) {
                Implementation(oracle().dao()).advanceNonIncentivized();
            }
        }
        
        Require.that(
            epoch().add(couponEpochExpiry) > 0,
            FILE,
            "Must have non-zero expiry"
        );

        // insert bid onto chain
        uint256 currentEpoch = epoch();
        uint256 totalBids = getCouponAuctionBids(currentEpoch);
        // this is the only time this addition operation should happen when adding current epoch to bid epoch
        uint256 epochExpiry = currentEpoch.add(couponEpochExpiry);
        setCouponAuctionRelYield(maxCouponAmount.div(dollarAmount));
        setCouponAuctionRelDollarAmount(dollarAmount);
        setCouponAuctionRelExpiry(epochExpiry);
        setCouponBidderState(currentEpoch, msg.sender, epochExpiry, dollarAmount, maxCouponAmount);
        setCouponBidderStateIndex(currentEpoch, totalBids, msg.sender);

        // todo sort bid on chain via BST
        sortBidBST(msg.sender, totalBids, currentEpoch);

        incrementCouponAuctionBids();
        emit CouponBidPlaced(msg.sender, epochExpiry, dollarAmount, maxCouponAmount);
        return true;
    }

    function sortBidBST(address bidAddr, uint256 totalBids, uint256 currentEpoch) internal returns (bool) {
        Epoch.CouponBidderState storage bidder = getCouponBidderState(currentEpoch, bidAddr);
        Epoch.AuctionState storage auction = getCouponAuctionAtEpoch(currentEpoch);

        if (totalBids == 0) {
            // no need to sort, just set addr as best bidder
            auction.initBidder = bidAddr;
        } else {
            // need a away to compare, use available internals boundaries;
            uint256 yieldRelNorm = 1 + getCouponAuctionMaxYield(currentEpoch) - getCouponAuctionMinYield(currentEpoch);
            uint256 expiryRelNorm = 1 + getCouponAuctionMaxExpiry(currentEpoch) - getCouponAuctionMinExpiry(currentEpoch);    
            uint256 dollarRelNorm = 1 + getCouponAuctionMaxDollarAmount(currentEpoch) - getCouponAuctionMinDollarAmount(currentEpoch);

            // sort bid
            Epoch.CouponBidderState storage pnodeBidder = getCouponBidderState(currentEpoch, auction.initBidder);
            Decimal.D256 memory bidAddrDistance = computeRelBidDistance(bidder, yieldRelNorm, expiryRelNorm, dollarRelNorm);

            address pnode = pnodeBidder.bidder;
            address node = pnodeBidder.leftBidder;
            while(node != address(0)) {
                //left or right subtree
                Epoch.CouponBidderState storage nodeBidder = getCouponBidderState(currentEpoch, node);
                Decimal.D256 memory nodeAddrDistance = computeRelBidDistance(nodeBidder, yieldRelNorm, expiryRelNorm, dollarRelNorm);
                

                if(nodeAddrDistance.greaterThan(bidAddrDistance)) {
                    // if node distance is greater than current bid distance
                    //pnode = nodeBidder.bidder;
                    node = nodeBidder.leftBidder;
                } else if(nodeAddrDistance.lessThan(bidAddrDistance)) {
                    // if node distance is less than current bid distance
                    //pnode = nodeBidder.bidder;
                    node = nodeBidder.rightBidder;
                } else if(nodeAddrDistance.equals(bidAddrDistance)) {
                    // duplicate values, sort not needed
                    return false;
                }
            }

            Epoch.CouponBidderState storage pNodeBidder = getCouponBidderState(currentEpoch, pnode);
            Decimal.D256 memory pNodeAddrDistance = computeRelBidDistance(pNodeBidder, yieldRelNorm, expiryRelNorm, dollarRelNorm);
            
            if(pNodeAddrDistance.greaterThan(bidAddrDistance)) {
                // if current parent node distance is greater than current bid distance
                pNodeBidder.leftBidder = bidAddr;
            } else if(pNodeAddrDistance.lessThan(bidAddrDistance)) {
                // if current parent node distance is less than than current bid distance
                pNodeBidder.rightBidder = bidAddr;
            } else if(pNodeAddrDistance.equals(bidAddrDistance)) {
                // duplicate values, sort not needed
                return false;
            }
            return true;
        }
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

    function computeRelBidDistance(Epoch.CouponBidderState memory bidder, uint256 yieldRelNorm, uint256 expiryRelNorm, uint256 dollarRelNorm) internal pure returns (Decimal.D256 memory) {
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

        return distance;
    }
}
