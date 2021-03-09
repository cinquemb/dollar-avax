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

import "@openzeppelin/contracts/token/ERC20/IERC20.sol";
import '@pangolindex/exchange-contracts/contracts/pangolin-core/interfaces/IPangolinPair.sol';

import '../external/PangolinLibrary.sol';
import "../Constants.sol";
import "./PoolGetters.sol";

contract Liquidity is PoolGetters {
    address private constant PANGOLIN_FACTORY = address(0xefa94DE7a4656D787667C749f7E1223D71E9FD88);

    function addLiquidity(uint256 dollarAmount) internal returns (uint256, uint256) {
        (address dollar, address usdc) = (address(dollar()), usdc());
        (uint reserveA, uint reserveB) = getReserves(dollar, usdc);

        uint256 usdcAmount = (reserveA == 0 && reserveB == 0) ?
             dollarAmount :
             PangolinLibrary.quote(dollarAmount, reserveA, reserveB);

        address pair = address(pangolin());
        IERC20(dollar).transfer(pair, dollarAmount);
        IERC20(usdc).transferFrom(msg.sender, pair, usdcAmount);
        return (usdcAmount, IPangolinPair(pair).mint(address(this)));
    }

    // overridable for testing
    function getReserves(address tokenA, address tokenB) internal view returns (uint reserveA, uint reserveB) {
        (address token0,) = PangolinLibrary.sortTokens(tokenA, tokenB);
        (uint reserve0, uint reserve1,) = IPangolinPair(PangolinLibrary.pairFor(PANGOLIN_FACTORY, tokenA, tokenB)).getReserves();
        (reserveA, reserveB) = tokenA == token0 ? (reserve0, reserve1) : (reserve1, reserve0);
    }
}
