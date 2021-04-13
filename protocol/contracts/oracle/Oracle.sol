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

import '@pangolindex/exchange-contracts/contracts/pangolin-core/interfaces/IPangolinFactory.sol';
import '@pangolindex/exchange-contracts/contracts/pangolin-core/interfaces/IPangolinPair.sol';
import '../external/PangolinOracleLibrary.sol';
import '../external/PangolinLibrary.sol';
import "../external/Require.sol";
import "../external/Decimal.sol";
import "./IOracle.sol";
import "./IUSDT.sol";
import "../Constants.sol";

contract Oracle is IOracle {
    using Decimal for Decimal.D256;


    address internal _dao;
    uint256 internal _index;
    address internal _dollar;
    bool private _latestValid;
    uint256 internal _reserve;
    uint32 internal _timestamp;
    bool internal _initialized;
    IPangolinPair internal _pair;
    uint256 internal _cumulative;
    Decimal.D256 private _latestPrice;
    bytes32 private constant FILE = "Oracle";
    address private constant PANGOLIN_FACTORY = address(0xefa94DE7a4656D787667C749f7E1223D71E9FD88);

    constructor (address dollar) public {
        _dao = msg.sender;
        _dollar = dollar;
    }

    function setup() public onlyDao {
        _pair = IPangolinPair(IPangolinFactory(PANGOLIN_FACTORY).createPair(_dollar, usdt()));

        (address token0, address token1) = (_pair.token0(), _pair.token1());
        _index = _dollar == token0 ? 0 : 1;

        Require.that(
            _index == 0 || _dollar == token1,
            FILE,
            "Døllar not found"
        );
    }

    /**
     * Trades/Liquidity: (1) Initializes reserve and blockTimestampLast (can calculate a price)
     *                   (2) Has non-zero cumulative prices
     *
     * Steps: (1) Captures a reference blockTimestampLast
     *        (2) First reported value
     */
    function capture() public onlyDao returns (Decimal.D256 memory, bool) {
        if (_initialized) {
            return updateOracle();
        } else {
            initializeOracle();
            return (Decimal.one(), false);
        }
    }

    function initializeOracle() private {
        IPangolinPair pair = _pair;
        uint256 priceCumulative = _index == 0 ?
            pair.price0CumulativeLast() :
            pair.price1CumulativeLast();
        (uint112 reserve0, uint112 reserve1, uint32 blockTimestampLast) = pair.getReserves();
        if(reserve0 != 0 && reserve1 != 0 && blockTimestampLast != 0) {
            _cumulative = priceCumulative;
            _timestamp = blockTimestampLast;
            _initialized = true;
            _reserve = _index == 0 ? reserve1 : reserve0; // get counter's reserve
        }
    }

    function updateOracle() private returns (Decimal.D256 memory, bool) {
        Decimal.D256 memory price = updatePrice();
        uint256 lastReserve = updateReserve();
        bool isBlacklisted = IUSDT(usdt()).isBlacklisted(address(_pair));

        bool valid = true;
        if (lastReserve < Constants.getOracleReserveMinimum()) {
            valid = false;
        }
        if (_reserve < Constants.getOracleReserveMinimum()) {
            valid = false;
        }
        if (isBlacklisted) {
            valid = false;
        }

        _latestValid = valid;
        _latestPrice = price;

        return (price, valid);
    }

    function updatePrice() private returns (Decimal.D256 memory) {
        (uint256 price0Cumulative, uint256 price1Cumulative, uint32 blockTimestamp) =
        PangolinOracleLibrary.currentCumulativePrices(address(_pair));
        uint32 timeElapsed = blockTimestamp - _timestamp; // overflow is desired
        uint256 priceCumulative = _index == 0 ? price0Cumulative : price1Cumulative;
        Decimal.D256 memory price = Decimal.ratio((priceCumulative - _cumulative) / timeElapsed, 2**112);

        _timestamp = blockTimestamp;
        _cumulative = priceCumulative;

        return price.mul(1e12);
    }

    function updateReserve() private returns (uint256) {
        uint256 lastReserve = _reserve;
        (uint112 reserve0, uint112 reserve1,) = _pair.getReserves();
        _reserve = _index == 0 ? reserve1 : reserve0; // get counter's reserve

        return lastReserve;
    }

    function liveReserve() external view returns (uint256) {
        (uint112 reserve0, uint112 reserve1,) = _pair.getReserves();
        uint256 lastReserve = _index == 0 ? reserve1 : reserve0; // get counter's reserve

        return lastReserve;
    }

    function usdt() internal view returns (address) {
        return Constants.getUsdtAddress();
    }

    function pair() external view returns (address) {
        return address(_pair);
    }

    function reserve() external view returns (uint256) {
        return _reserve;
    }

    function dao() public view returns (address) {
        return _dao;
    }

    function latestPrice() public view returns (Decimal.D256 memory) {
        return _latestPrice;
    }

    function latestValid() public view returns (bool) {
        return _latestValid;
    }

    modifier onlyDao() {
        Require.that(
            msg.sender == _dao,
            FILE,
            "Not dao"
        );

        _;
    }
}