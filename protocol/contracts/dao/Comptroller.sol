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
import "./Setters.sol";
import "../external/Require.sol";

contract Comptroller is Setters {
    using SafeMath for uint256;

    bytes32 private constant FILE = "Comptroller";

    function mintToAccount(address account, uint256 amount) internal {
        dollar().mint(account, amount);
        balanceCheck();
    }

    function burnFromAccountSansDebt(address account, uint256 amount) internal {
        dollar().transferFrom(account, address(this), amount);
        dollar().burn(amount);
        balanceCheck();
    }

    function burnFromAccount(address account, uint256 amount) internal {
        dollar().transferFrom(account, address(this), amount);
        dollar().burn(amount);
        balanceCheck();
    }

    function redeemToAccount(address account, uint256 amount) internal {
        dollar().transfer(account, amount);
        if (amount != 0) {
            decrementTotalRedeemable(amount, "Comptroller: not enough redeemable balance");
        }
        balanceCheck();
    }

    function burnRedeemable(uint256 amount) internal {
        dollar().burn(amount);
        decrementTotalRedeemable(amount, "Comptroller: not enough redeemable balance");
        balanceCheck();
    }

    function increaseSupply(uint256 newSupply) internal returns (uint256, uint256) {
        /* 
            supply growth is purely a function of the best auction bids outstanding for coupons from below peg
            - lps collect fees for incentive (maybe lp pool can get a cut of total redeemable coupons? like 1%?)
            - people can vote and leave any time they want as fast as they want

        */
        uint256 newRedeemable = 0;
        uint256 totalRedeemable = totalRedeemable();
        uint256 totalBestCoupons = getSumofBestBidsAcrossCouponAuctions();
        if (totalRedeemable < totalBestCoupons) {
            newRedeemable = totalBestCoupons.sub(totalRedeemable);
            newRedeemable = newRedeemable > newSupply ? newSupply : newRedeemable;
            mintToRedeemable(newRedeemable);
        }
        balanceCheck();

        return (newRedeemable, 0);
    }

    function acceptableBidCheck(address account, uint256 dollarAmount) internal view returns (bool) {
        return (dollar().balanceOf(account) >= balanceOfBonded(account).add(dollarAmount));
    }

    function balanceCheck() private view {
        Require.that(
            dollar().balanceOf(address(this)) >= totalBonded().add(totalStaged()).add(totalRedeemable()),
            FILE,
            "Inconsistent balances"
        );
    }

    function mintToDAO(uint256 amount) private {
        if (amount > 0) {
            dollar().mint(address(this), amount);
            incrementTotalBonded(amount);
        }
    }

    function mintToPool(uint256 amount) private {
        if (amount > 0) {
            dollar().mint(pool(), amount);
        }
    }

    function mintToRedeemable(uint256 amount) private {
        dollar().mint(address(this), amount);
        incrementTotalRedeemable(amount);
        balanceCheck();
    }
}
