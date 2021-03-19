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
import "./Market.sol";
import "./Regulator.sol";
import "./Bonding.sol";
import "./Govern.sol";
import "../Constants.sol";

contract Implementation is State, Bonding, Market, Regulator, Govern {
    using SafeMath for uint256;

    event Advance(uint256 indexed epoch, uint256 block, uint256 timestamp);
    event Incentivization(address indexed account, uint256 amount);

    function initialize() initializer public { }

    function advance() external {
        /*
        uint256 prev_epoch = epoch();
        bool latestValid = oracle().latestValid();
        if ((prev_epoch > 0) && (latestValid == true)) {
            //can only incentivize advance above or at ref price
            Decimal.D256 memory price = oracle().latestPrice();
            require(
                price.greaterThanOrEqualTo(Decimal.one()),
                "DAO: Must coupon bid"
            );
        }*/

        // Mint advance reward to sender
        /*require(
            hasRecievedAdvanceIncentive(msg.sender) == false,
            "DAO: Already advanced"
        );*/

        Bonding.step();
        Regulator.step();
        Market.step();
        setAdvanceCalled(epoch());

        uint256 incentive = Constants.getAdvanceIncentive();
        mintToAccount(msg.sender, incentive);
        setRecievedAdvanceIncentive(msg.sender);
        
        emit Incentivization(msg.sender, incentive);
        emit Advance(epoch(), block.number, block.timestamp);
    }

    function advanceNonIncentivized() external {
        Bonding.step();
        Regulator.step();
        Market.step();
        setAdvanceCalled(epoch());
        emit Advance(epoch(), block.number, block.timestamp);
    }
}
