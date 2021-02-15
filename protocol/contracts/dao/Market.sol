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
import "./Curve.sol";
import "./Comptroller.sol";
import "../Constants.sol";

contract Market is Comptroller, Curve {
    using SafeMath for uint256;

    bytes32 private constant FILE = "Market";

    event CouponExpiration(uint256 indexed epoch, uint256 couponsExpired, uint256 lessRedeemable, uint256 lessDebt, uint256 newBonded);
    event CouponPurchase(address indexed account, uint256 indexed epoch, uint256 dollarAmount, uint256 couponAmount);
    event CouponRedemption(address indexed account, uint256 indexed epoch, uint256 couponAmount);
    event CouponBurn(address indexed account, uint256 indexed epoch, uint256 couponAmount);
    event CouponTransfer(address indexed from, address indexed to, uint256 indexed epoch, uint256 value);
    event CouponApproval(address indexed owner, address indexed spender, uint256 value);
    event CouponBidPlaced(address indexed account, uint256 indexed epoch, uint256 dollarAmount, uint256 maxCouponAmount);
    
    function step() internal {
        // Expire prior coupons
        for (uint256 i = 0; i < expiringCoupons(epoch()); i++) {
            expireCouponsForEpoch(expiringCouponsAtIndex(epoch(), i));
        }

        // Record expiry for current epoch's coupons
        uint256 expirationEpoch = epoch().add(Constants.getCouponExpiration());
        initializeCouponsExpiration(epoch(), expirationEpoch);
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

    function couponPremium(uint256 amount) public view returns (uint256) {
        return calculateCouponPremium(dollar().totalSupply(), totalDebt(), amount);
    }

    function couponRedemptionPenalty(uint256 couponEpoch, uint256 couponAmount) public view returns (uint256) {
        uint timeIntoEpoch = block.timestamp % Constants.getEpochStrategy().period;
        uint couponAge = epoch() - couponEpoch;

        uint couponEpochDecay = Constants.getCouponRedemptionPenaltyDecay() * (Constants.getCouponExpiration() - couponAge) / Constants.getCouponExpiration();

        if(timeIntoEpoch > couponEpochDecay) {
            return 0;
        }

        Decimal.D256 memory couponEpochInitialPenalty = Constants.getInitialCouponRedemptionPenalty().div(Decimal.D256({value: Constants.getCouponExpiration() })).mul(Decimal.D256({value: Constants.getCouponExpiration() - couponAge}));

        Decimal.D256 memory couponEpochDecayedPenalty = couponEpochInitialPenalty.div(Decimal.D256({value: couponEpochDecay})).mul(Decimal.D256({value: couponEpochDecay - timeIntoEpoch}));

        return Decimal.D256({value: couponAmount}).mul(couponEpochDecayedPenalty).value;
    }

    function purchaseCoupons(uint256 dollarAmount) external returns (uint256) {
        Require.that(
            dollarAmount > 0,
            FILE,
            "Must purchase non-zero amount"
        );

        Require.that(
            totalDebt() >= dollarAmount,
            FILE,
            "Not enough debt"
        );

        uint256 epoch = epoch();
        uint256 couponAmount = dollarAmount.add(couponPremium(dollarAmount));
        burnFromAccount(msg.sender, dollarAmount);
        incrementBalanceOfCoupons(msg.sender, epoch, couponAmount);

        emit CouponPurchase(msg.sender, epoch, dollarAmount, couponAmount);

        return couponAmount;
    }

    function redeemCoupons(uint256 couponEpoch, uint256 couponAmount) external {
        require(epoch().sub(couponEpoch) >= 2, "Market: Too early to redeem");
        decrementBalanceOfCoupons(msg.sender, couponEpoch, couponAmount, "Market: Insufficient coupon balance");
        
        uint burnAmount = couponRedemptionPenalty(couponEpoch, couponAmount);
        uint256 redeemAmount = couponAmount - burnAmount;
        
        redeemToAccount(msg.sender, redeemAmount);

        if(burnAmount > 0){
            setCouponBidderStateRedeemed(couponEpoch, msg.sender);
            emit CouponBurn(msg.sender, couponEpoch, burnAmount);
        }

        emit CouponRedemption(msg.sender, couponEpoch, redeemAmount);
    }

    function redeemCoupons(uint256 couponEpoch, uint256 couponAmount, uint256 minOutput) external {
        require(epoch().sub(couponEpoch) >= 2, "Market: Too early to redeem");
        decrementBalanceOfCoupons(msg.sender, couponEpoch, couponAmount, "Market: Insufficient coupon balance");
        
        uint burnAmount = couponRedemptionPenalty(couponEpoch, couponAmount);
        uint256 redeemAmount = couponAmount - burnAmount;

        Require.that(
            redeemAmount >= minOutput,
            FILE,
            "Insufficient output amount"
        );
        
        redeemToAccount(msg.sender, redeemAmount);

        if(burnAmount > 0){
            setCouponBidderStateRedeemed(couponEpoch, msg.sender);
            emit CouponBurn(msg.sender, couponEpoch, burnAmount);
        }

        emit CouponRedemption(msg.sender, couponEpoch, redeemAmount);
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
            epoch().add(couponEpochExpiry) > 0,
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
            couponEpochExpiry >= couponEpochExpiry,
            FILE,
            "Must be under maxExpiry"
        );

        // insert bid onto chain
        uint256 currentEpoch = uint256(epoch());
        uint256 totalBids = getCouponAuctionBids(currentEpoch);
        uint256 epochExpiry = currentEpoch.add(couponEpochExpiry);
        setCouponAuctionRelYield(maxCouponAmount.div(dollarAmount));
        setCouponAuctionRelDollarAmount(dollarAmount);
        setCouponAuctionRelExpiry(epochExpiry);
        setCouponBidderState(currentEpoch, msg.sender, couponEpochExpiry, dollarAmount, maxCouponAmount);
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
            uint256 yieldRelNorm = getCouponAuctionMaxYield(currentEpoch) - getCouponAuctionMinYield(currentEpoch);
            uint256 expiryRelNorm = getCouponAuctionMaxExpiry(currentEpoch) - getCouponAuctionMinExpiry(currentEpoch);    
            uint256 dollarRelNorm = getCouponAuctionMaxDollarAmount(currentEpoch) - getCouponAuctionMinDollarAmount(currentEpoch);

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
                    pnode = nodeBidder.bidder;
                    node = nodeBidder.leftBidder;
                } else if(nodeAddrDistance.lessThan(bidAddrDistance)) {
                    // if node distance is less than current bid distance
                    pnode = nodeBidder.bidder;
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
