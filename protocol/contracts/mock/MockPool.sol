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

import "../oracle/Pool.sol";

contract MockPool is Pool {
    address private _usdt;
    address private _dao;
    address private _dollar;
    address private _pangolin;

    constructor(address dollar, address usdt, address pangolin) Pool(dollar, pangolin) public {
        _usdt = usdt;
    }

    function set(address dao, address dollar, address pangolin) external {
        _dao = dao;
        _dollar = dollar;
        _pangolin = pangolin;
    }

    function usdt() public view returns (address) {
        return _usdt;
    }

    function dao() public view returns (IDAO) {
        return IDAO(_dao);
    }

    function dollar() public view returns (IDollar) {
        return IDollar(_dollar);
    }

    function pangolin() public view returns (IERC20) {
        return IERC20(_pangolin);
    }

    function getReserves(address tokenA, address tokenB) internal view returns (uint reserveA, uint reserveB) {
        (reserveA, reserveB,) = IPangolinPair(address(pangolin())).getReserves();
    }
}
