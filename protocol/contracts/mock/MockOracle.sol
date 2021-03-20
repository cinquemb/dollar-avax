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

import '@pangolindex/exchange-contracts/contracts/pangolin-core/interfaces/IPangolinPair.sol';
import "../oracle/Oracle.sol";
import "../external/Decimal.sol";

contract MockOracle is Oracle {
    Decimal.D256 private _latestPrice;
    bool private _latestValid;
    address private _usdc;

    constructor (address pair, address dollar, address usdc) Oracle(dollar) public {
        _pair = IPangolinPair(pair);
        _index = 0;
        _usdc = usdc;
    }

    function usdc() internal view returns (address) {
        return _usdc;
    }

    function set(address factory, address usdc) external {
        _usdc = usdc;
        _pair = IPangolinPair(IPangolinFactory(factory).createPair(_dollar, _usdc));

        (address token0, address token1) = (_pair.token0(), _pair.token1());
        _index = _dollar == token0 ? 0 : 1;
    }

    function capture() public returns (Decimal.D256 memory, bool) {
        (_latestPrice, _latestValid) = super.capture();
        return (_latestPrice, _latestValid);
    }

    function latestPrice() public view returns (Decimal.D256 memory) {
        return _latestPrice;
    }

    function latestValid() public view returns (bool) {
        return _latestValid;
    }

    function isInitialized() external view returns (bool) {
        return _initialized;
    }

    function cumulative() external view returns (uint256) {
        return _cumulative;
    }

    function timestamp() external view returns (uint256) {
        return _timestamp;
    }

    function reserve() external view returns (uint256) {
        return _reserve;
    }
}
