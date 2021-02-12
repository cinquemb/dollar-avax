#!/usr/bin/env python3

"""
model.py: agent-based model of xSD system behavior, against a testnet
"""

import json
import collections
import random
import math
import logging
import time
import sys

from web3 import Web3

deploy_data = None
with open("deploy_output.txt", 'r+') as f:
    deploy_data = f.read()

IS_DEBUG = False
block_offset = 16

logger = logging.getLogger(__name__)
provider = Web3.WebsocketProvider('ws://localhost:7545', websocket_timeout=60)
#provider = Web3.IPCProvider("./development.ipc")
w3 = Web3(provider)

# from (Uniswap pair is at:)
UNI = {
  "addr": '',
  "decimals": 18,
  "symbol": 'UNI',
  "deploy_slug": "Uniswap pair is at: "
}

# USDC is at: 
USDC = {
  "addr": '',
  "decimals": 6,
  "symbol": 'USDC',
  "deploy_slug": "USDC is at: "
}

#Pool is at: 
UNIV2LP = {
    "addr": '',
    "decimals": 18,
    "deploy_slug": "Pool is at: "
}

#UniswapV2Router is at: 
UNIV2Router = {
    "addr": "",
    "decimals": 12,
    "deploy_slug": "UniswapV2Router is at: "
}

for contract in [UNI, USDC, UNIV2LP, UNIV2Router]:
    print(contract["deploy_slug"])
    contract["addr"] = deploy_data.split(contract["deploy_slug"])[1].split('\n')[0]
    print('\t'+contract["addr"])


# dao (from Deploy current Implementation on testnet)
xSD = {
  "addr": '',
  "decimals": 18,
  "symbol": 'xSD',
}

# token (from Deploy Root on testnet)
xSDS = {
  "addr": '',
  "decimals": 18,
  "symbol": 'xSDS',
}

DEADLINE_FROM_NOW = 60 * 15
UINT256_MAX = 2**256 - 1
ZERO_ADDRESS = '0x0000000000000000000000000000000000000000'

DaoContract = json.loads(open('./build/contracts/Implementation.json', 'r+').read())
USDCContract = json.loads(open('./build/contracts/TestnetUSDC.json', 'r+').read())
DollarContract = json.loads(open('./build/contracts/IDollar.json', 'r+').read())

UniswapPairContract = json.loads(open('./build/contracts/IUniswapV2Pair.json', 'r+').read())
UniswapRouterAbiContract = json.loads(open('./node_modules/@uniswap/v2-periphery/build/IUniswapV2Router02.json', 'r+').read())
UniswapClientAbiContract = json.loads(open('./node_modules/@uniswap/v2-core/build/IUniswapV2ERC20.json', 'r+').read())
TokenContract = json.loads(open('./build/contracts/Root.json', 'r+').read())
PoolContract = json.loads(open('./build/contracts/Pool.json', 'r+').read())
OracleContract = json.loads(open('./build/contracts/MockOracle.json', 'r+').read())

def get_addr_from_contract(contract):
    return contract["networks"][str(sorted(map(int,contract["networks"].keys()))[-1])]["address"]

xSD['addr'] = get_addr_from_contract(DaoContract)
xSDS['addr'] = get_addr_from_contract(TokenContract)

def get_nonce(address):
    return w3.eth.getTransactionCount(address)

# Because token balances need to be accuaate to the atomic unit, we can't store
# them as floats. Otherwise we might turn our float back into a token balance
# different from the balance we actually had, and try to spend more than we
# have. But also, it's ugly to throw around total counts of atomic units. So we
# use this class that represents a fixed-point token balance.
class Balance:
    def __init__(self, wei=0, decimals=0):
        self._wei = int(wei)
        self._decimals = int(decimals)
        
    def to_decimals(self, new_decimals):
        """
        Get a similar balance with a different number of decimals.
        """
        
        return Balance(self._wei * 10**new_decimals // 10**self._decimals, new_decimals)
        
    @classmethod
    def from_float(cls, n, decimals=0):
        return cls(n * 10**decimals, decimals)

    def __add__(self, other):
        if isinstance(other, Balance):
            if other._decimals != self._decimals:
                raise ValueError("Cannot add balances with different decimals: {}, {}", self, other)
            return Balance(self._wei + other._wei, self._decimals)
        else:
            return Balance(self._wei + other * 10**self._decimals, self._decimals)

    def __iadd__(self, other):
        if isinstance(other, Balance):
            if other._decimals != self._decimals:
                raise ValueError("Cannot add balances with different decimals: {}, {}", self, other)
            self._wei += other._wei
        else:
            self._wei += other * 10**self._decimals
        return self
        
    def __radd__(self, other):
        return self + other
        
    def __sub__(self, other):
        if isinstance(other, Balance):
            if other._decimals != self._decimals:
                raise ValueError("Cannot subtract balances with different decimals: {}, {}", self, other)
            return Balance(self._wei - other._wei, self._decimals)
        else:
            return Balance(self._wei - other * 10**self._decimals, self._decimals)

    def __isub__(self, other):
        if isinstance(other, Balance):
            if other._decimals != self._decimals:
                raise ValueError("Cannot subtract balances with different decimals: {}, {}", self, other)
            self._wei -= other._wei
        else:
            self._wei -= other * 10**self._decimals
        return self
        
    def __rsub__(self, other):
        return Balance(other * 10**self._decimals, self._decimals) - self
        
    def __mul__(self, other):
        if isinstance(other, Balance):
            raise TypeError("Cannot multiply two balances")
        return Balance(self._wei * other, self._decimals)
        
    def __imul__(self, other):
        if isinstance(other, Balance):
            raise TypeError("Cannot multiply two balances")
        self._wei = int(self._wei * other)
        
    def __rmul__(self, other):
        return self * other
        
    def __truediv__(self, other):
        if isinstance(other, Balance):
            raise TypeError("Cannot divide two balances")
        return Balance(self._wei // other, self._decimals)
        
    def __itruediv__(self, other):
        if isinstance(other, Balance):
            raise TypeError("Cannot divide two balances")
        self._wei = int(self._wei // other)
        
    # No rtruediv because dividing by a balance is silly.
    
    # Todo: floordiv? divmod?
    
    def __lt__(self, other):
        if isinstance(other, Balance):
            if other._decimals != self._decimals:
                raise ValueError("Cannot compare balances with different decimals: {}, {}", self, other)
            return self._wei < other._wei
        else:
            return float(self) < other
            
    def __le__(self, other):
        if isinstance(other, Balance):
            if other._decimals != self._decimals:
                raise ValueError("Cannot compare balances with different decimals: {}, {}", self, other)
            return self._wei <= other._wei
        else:
            return float(self) <= other
            
    def __gt__(self, other):
        if isinstance(other, Balance):
            if other._decimals != self._decimals:
                raise ValueError("Cannot compare balances with different decimals: {}, {}", self, other)
            return self._wei > other._wei
        else:
            return float(self) > other
            
    def __ge__(self, other):
        if isinstance(other, Balance):
            if other._decimals != self._decimals:
                raise ValueError("Cannot compare balances with different decimals: {}, {}", self, other)
            return self._wei >= other._wei
        else:
            return float(self) >= other
            
    def __eq__(self, other):
        if isinstance(other, Balance):
            if other._decimals != self._decimals:
                raise ValueError("Cannot compare balances with different decimals: {}, {}", self, other)
            return self._wei == other._wei
        else:
            return float(self) == other
            
    def __ne__(self, other):
        if isinstance(other, Balance):
            if other._decimals != self._decimals:
                raise ValueError("Cannot compare balances with different decimals: {}, {}", self, other)
            return self._wei != other._wei
        else:
            return float(self) != other

    def __str__(self):
        base = 10**self._decimals
        ipart = self._wei // base
        fpart = self._wei - base * ipart
        return ('{}.{:0' + str(self._decimals) + 'd}').format(ipart, fpart)

    def __repr__(self):
        return 'Balance({}, {})'.format(self._wei, self._decimals)
        
    def __float__(self):
        return self._wei / 10**self._decimals
        
    def __format__(self, s):
        if s == '':
            return str(self)
        return float(self).__format__(s)
        
    def to_wei(self):
        return self._wei
        
    def decimals(self):
        return self._decimals
        
def reg_int(value, scale):
    """
    Convert from atomic token units with the given number of decimals, to a
    Balance with the right number of decimals.
    """
    return Balance(value, scale)

def unreg_int(value, scale):
    """
    Convert from a Balance with the right number of decimals to atomic token
    units with the given number of decimals.
    """
    
    assert(value.decimals() == scale)
    return value.to_wei()

def pretty(d, indent=0):
   """
   Pretty-print a value.
   """
   for key, value in d.items():
      print('\t' * indent + str(key))
      if isinstance(value, dict):
         pretty(value, indent+1)
      elif isinstance(value, list):
        for v in value:
            pretty(v, indent+1)
      else:
         print('\t' * (indent+1) + str(value))
         
         
class TokenProxy:
    """
    A proxy for an ERC20 token. Monitors events, processes them when update()
    is called, and fulfils balance requests from memory.
    """
    
    def __init__(self, contract):
        """
        Set up a proxy around a Web3py contract object that implements ERC20.
        """
        
        self.__contract = contract
        self.__transfer_filter = self.__contract.events.Transfer.createFilter(fromBlock='latest')
        # This maps from string address to Balance balance
        self.__balances = {}
        # This records who we approved for who
        self.__approved = collections.defaultdict(set)
        
        
        # Load initial parameters from the chain.
        # Assumes no events are happening to change the supply while we are doing this.
        self.__decimals = self.__contract.functions.decimals().call()
        self.__symbol = self.__contract.functions.symbol().call()
        self.__supply = Balance(self.__contract.functions.totalSupply().call(), self.__decimals)
        
    # Expose some properties to make us easy to use in place of the contract
        
    @property
    def decimals(self):
        return self.__decimals
        
    @property
    def symbol(self):
        return self.__symbol
        
    @property
    def totalSupply(self):
        return self.__supply
        
    @property
    def address(self):
        return self.__contract.address
        
    @property
    def contract(self):
        return self.__contract
        
    def update(self):
        """
        Process pending events and update state to match chain.
        Assumes no transactions are still in flight.
        """
        
        # These addresses need to be polled because we have no balance from
        # before all these events.
        new_addresses = set()
        
        for transfer in self.__transfer_filter.get_new_entries():
            # For every transfer event since we last updated...
            
            # Each loooks something like:
            # AttributeDict({'args': AttributeDict({'from': '0x0000000000000000000000000000000000000000', 
            # 'to': '0x20042A784Bf0743fcD81136422e12297f52959a0', 'value': 19060347313}), 
            # 'event': 'Transfer', 'logIndex': 0, 'transactionIndex': 0,
            # 'transactionHash': HexBytes('0xa6f4ca515b28301b224f24b7ee14b8911d783e2bf965dbcda5784b4296c84c23'), 
            # 'address': '0xa2Ff73731Ee46aBb6766087CE33216aee5a30d5e', 
            # 'blockHash': HexBytes('0xb5ffd135318581fcd5cd2463cf3eef8aaf238bef545e460c284ad6283928ed08'),
            # 'blockNumber': 17})
            args = transfer['args']
            
            moved = Balance(args['value'], self.__decimals)
            if args['from'] in self.__balances:
                self.__balances[args['from']] -= moved
            elif args['from'] == ZERO_ADDRESS:
                # This is a mint
                self.__supply += moved
            else:
                new_addresses.add(args['from'])
            if args['to'] in self.__balances:
                self.__balances[args['to']] += moved
            elif args['to'] == ZERO_ADDRESS:
                # This is a burn
                self.__supply -= moved
            else:
                new_addresses.add(args['to'])
        
        for address in new_addresses:
            # TODO: can we get a return value and a correct-as-of block in the same call?
            self.__balances[address] = Balance(self.__contract.functions.balanceOf(address).call(), self.__decimals)
            
    def __getitem__(self, address):
        """
        Get the balance of the given address as a Balance, with the given number of decimals.
        
        Address can be a string or any object with an .address field.
        """
        
        address = getattr(address, 'address', address)
        
        if address not in self.__balances:
            # Don't actually cache here; wait for a transfer.
            # Transactions may still be in flight
            return Balance(self.__contract.functions.balanceOf(address).call(), self.__decimals)
        else:
            return self.__balances[address]
            
    def ensure_approved(self, owner, spender):
        """
        Approve the given spender to spend all the owner's tokens on their behalf.
        
        Owner and spender may be addresses or things with addresses.
        """
        
        owner = getattr(owner, 'address', owner)
        spender = getattr(spender, 'address', spender)
        
        if spender not in self.__approved[owner]:
            # Issue an approval
            self.__contract.functions.approve(spender, UINT256_MAX).transact({
                'nonce': get_nonce(owner),
                'from' : owner,
                'gas': 8000000,
                'gasPrice': 1,
            })
            self.__approved[owner].add(spender)
        
class Agent:
    """
    Represents an agent. Tracks all the agent's balances.
    """
    
    def __init__(self, dao, uniswap_pair, xsd_token, usdc_token, **kwargs):
 
        # xSD contract
        self.xsd_token = xsd_token
        # USDC TokenProxy 
        self.usdc_token = usdc_token
        # xSD balance
        self.xsd = Balance(0, xSD["decimals"])
        # xSDS (Dao share) balance
        self.xsds = Balance(0, xSDS["decimals"])
        # Eth balance
        self.eth = kwargs.get("starting_eth", Balance(0, 18))
        
        # Coupon underlying part by expiration epoch
        self.underlying_coupons = collections.defaultdict(float)
        # Coupon premium part by expiration epoch
        self.premium_coupons = collections.defaultdict(float)
        
        # What's our max faith in the system in USDC?
        self.max_faith = kwargs.get("max_faith", 0.0)
        # And our min faith
        self.min_faith = kwargs.get("min_faith", 0.0)
        # Should we even use faith?
        self.use_faith = kwargs.get("use_faith", True)

        # add wallet addr
        self.address = kwargs.get("wallet_address", '0x0000000000000000000000000000000000000000')
        # total coupons bid
        self.total_coupons_bid = Balance(0, xSD["decimals"])

        #coupon expirys
        self.coupon_expirys = []
        #coupons at a given exirpy index
        self.coupon_expiry_coupons = []

        self.dao = dao
        self.uniswap_pair = uniswap_pair

        self.is_uniswap_approved = False
        self.is_xsd_approved = False
        self.is_dao_approved = False

        # Uniswap LP share balance
        self.lp = 0
        is_seeded = True

        if is_seeded:
            self.lp = reg_int(self.uniswap_pair.caller({'from' : self.address, 'gas': 8000000}).balanceOf(self.address), UNIV2Router['decimals'])

            self.xsd = reg_int(self.xsd_token.caller({'from' : self.address, 'gas': 8000000}).balanceOf(self.address), xSD['decimals'])
            
    @property
    def usdc(self):
        """
        Get the current balance in USDC from the token.
        """
        return self.usdc_token[self]
            
    def __str__(self):
        """
        Turn into a readable string summary.
        """
        return "Agent(xSD={:.2f}, usdc={:.2f}, eth={}, lp={}, coupons={:.2f})".format(
            self.xsd, self.usdc, self.eth, self.lp, self.dao.total_coupons(self.address))
        
    def get_strategy(self, block, price, total_supply):
        """
        Get weights, as a dict from action to float, as a function of the price.
        """
        
        strategy = collections.defaultdict(lambda: 1.0)
        
        # TODO: real (learned? adversarial? GA?) model of the agents
        # TODO: agent preferences/utility function
        
        # People are slow to coupon
        strategy["coupon"] = 0.1

        # People are fast to coupon bid to get in front of redemption queue
        strategy["coupon_bid"] = 1.0

        # And to unbond because of the delay
        strategy["unbond"] = 0.1
        
        if price >= 1.0:
            # No rewards for expansion by itself
            strategy["bond"] = 0
            # And not unbond
            strategy["unbond"] = 0
            # Or redeem if possible
            strategy["redeem"] = 100.0
            # no incetive to buy above 1
            strategy["buy"] = 0.0
        else:
            # We probably want to unbond due to no returns
            strategy["unbond"] = 0
            # And not bond
            strategy["bond"] = 0
       
        if self.use_faith:
            # Vary our strategy based on how much xSD we think ought to exist
            if price * total_supply > self.get_faith(block, price, total_supply):
                # There is too much xSD, so we want to sell
                strategy["unbond"] *= 2
                strategy["sell"] = 4.0
            else:
                # no faith based buying, just selling
                pass
        
        return strategy
        
    def get_faith(self, block, price, total_supply):
        """
        Get the total faith in xSD that this agent has, in USDC.
        
        If the market cap is over the faith, the agent thinks the system is
        over-valued. If the market cap is under the faith, the agent thinks the
        system is under-valued.
        """
        
        # TODO: model the real economy as bidding on utility in
        # mutually-beneficial exchanges conducted in xSD, for which a velocity
        # is needed, instead of an abstract faith?
        
        # TODO: different faith for different people
        
        center_faith = (self.max_faith + self.min_faith) / 2
        swing_faith = (self.max_faith - self.min_faith) / 2
        faith = center_faith + swing_faith * math.sin(block * (2 * math.pi / 5000))
        
        return faith
        
class UniswapPool:
    """
    Represents the Uniswap pool. Tracks xSD and USDC balances of pool, and total outstanding LP shares.
    """
    
    def __init__(self, uniswap, uniswap_router, uniswap_token, usdc_token, xsd, **kwargs):
        self.uniswap_pair = uniswap
        self.uniswap_router = uniswap_router
        self.uniswap_token = uniswap_token
        self.usdc_token = usdc_token
        self.xsd = xsd
    
    def operational(self):
        """
        Return true if buying and selling is possible.
        """
        reserve = self.getReserves()
        token0Balance = reserve[0]
        token1Balance = reserve[1]
        return token0Balance > 0 and token1Balance > 0
    
    def getToken0(self):
        exchange = self.uniswap_pair
        return exchange.functions.token0().call()

    def getReserves(self):
        exchange = self.uniswap_pair
        return exchange.functions.getReserves().call()

    def getTokenBalance(self):
        reserve, token0 = self.getReserves(), self.getToken0()
        token0Balance = reserve[0]
        token1Balance = reserve[1]
        if (token0.lower() == USDC["addr"].lower()):
            return reg_int(token0Balance, USDC['decimals']), reg_int(token1Balance, xSD['decimals'])
        return reg_int(token1Balance, USDC['decimals']), reg_int(token0Balance, xSD['decimals'])

    def getInstantaneousPrice(self):
      reserve, token0 = self.getReserves(), self.getToken0()
      token0Balance = reserve[0]
      token1Balance = reserve[1]
      if (token0.lower() == USDC["addr"].lower()):
        return int(token0Balance) * pow(10, UNIV2Router['decimals']) / float(int(token1Balance)) if int(token1Balance) != 0 else 0
      return int(token1Balance) * pow(10, UNIV2Router['decimals']) / float(int(token0Balance)) if int(token0Balance) != 0 else 0
    
    def xsd_price(self):
        """
        Get the current xSD price in USDC.
        """
        
        if self.operational():
            return self.getInstantaneousPrice()
        else:
            return 1.0

    def total_lp(self, address):
        return reg_int(self.uniswap_pair.caller({'from' : address, 'gas': 8000000}).totalSupply(), UNIV2Router['decimals'])
        
    def provide_liquidity(self, agent, xsd, usdc):
        """
        Provide liquidity. Returns the number of new LP shares minted.
        """        
        
        self.usdc_token.ensure_approved(agent, UNIV2Router["addr"])
        
        if not agent.is_xsd_approved:
            self.xsd.functions.approve(UNIV2Router["addr"], UINT256_MAX).transact({
                'nonce': get_nonce(agent.address),
                'from' : agent.address,
                'gas': 8000000,
                'gasPrice': 1,
            })
            agent.is_xsd_approved = True

        slippage = 0.01
        min_xsd_amount = (xsd * (1 - slippage))
        min_usdc_amount = (usdc * (1 - slippage))

        if IS_DEBUG:
            xsd_wei = self.xsd.caller({'from' : agent.address, 'gas': 8000000}).balanceOf(address)
            usdc_wei = self.usdc_token[agent].to_wei()

            assert xsd_wei >= xsd.to_wei()
            assert usdc_wei >= usdc.to_wei()

        rv = self.uniswap_router.functions.addLiquidity(
            self.xsd.address,
            self.usdc_token.address,
            unreg_int(xsd, xSD['decimals']),
            unreg_int(usdc, USDC['decimals']),
            unreg_int(min_xsd_amount, xSD['decimals']),
            unreg_int(min_usdc_amount, USDC['decimals']),
            agent.address,
            (int(w3.eth.get_block('latest')['timestamp']) + DEADLINE_FROM_NOW)
        ).transact({
            'nonce': get_nonce(agent.address),
            'from' : agent.address,
            'gas': 8000000,
            'gasPrice': 1,
        })
        
        lp_shares = reg_int(self.uniswap_pair.caller({'from' : agent.address, 'gas': 8000000}).balanceOf(agent.address), UNIV2Router['decimals'])
        return lp_shares
        
    def remove_liquidity(self, agent, shares, min_xsd_amount, min_usdc_amount):
        """
        Remove liquidity for the given number of shares.

        """        
        if not agent.is_uniswap_approved:
            self.uniswap_pair.functions.approve(UNIV2Router["addr"], UINT256_MAX).transact({
                'nonce': get_nonce(agent.address),
                'from' : agent.address,
                'gas': 8000000,
                'gasPrice': 1,
            }) 
            agent.is_uniswap_approved = True 

        slippage = 0.01
        min_xsd_amount = (min_xsd_amount * (1 - slippage))
        min_usdc_amount = (min_usdc_amount * (1 - slippage))

        self.uniswap_router.functions.removeLiquidity(
            self.xsd.address,
            self.usdc_token.address,
            unreg_int(shares, UNIV2Router['decimals']),
            unreg_int(min_xsd_amount, xSD['decimals']),
            unreg_int(min_usdc_amount, USDC['decimals']),
            agent.address,
            int(w3.eth.get_block('latest')['timestamp'] + DEADLINE_FROM_NOW)
            
        ).transact({
            'nonce': get_nonce(agent.address),
            'from' : agent.address,
            'gas': 8000000,
            'gasPrice': 1,
        })

        lp_shares = reg_int(self.uniswap_pair.caller({'from' : agent.address, 'gas': 8000000}).balanceOf(agent.address), UNIV2Router['decimals'])
        return lp_shares
        
    def buy(self, agent, usdc, max_usdc_amount):
        """
        Spend the given number of USDC to buy xSD. Returns the xSD bought.
        ['swapTokensForExactTokens(uint256,uint256,address[],address,uint256)']
        """  
        # get balance of xSD before and after
        balance_before = self.xsd.caller({"from": agent.address, 'gas': 8000000}).balanceOf(agent.address)

        
        self.usdc_token.ensure_approved(agent, UNIV2Router["addr"])

        if not agent.is_xsd_approved:
            self.xsd.functions.approve(UNIV2Router["addr"], UINT256_MAX).transact({
                'nonce': get_nonce(agent.address),
                'from' : agent.address,
                'gas': 8000000,
                'gasPrice': 1,
            })
            agent.is_xsd_approved = True

        # explore this more?
        slippage = 0.01
        max_usdc_amount = (max_usdc_amount * (1 + slippage))

        self.uniswap_router.functions.swapExactTokensForTokens(
            unreg_int(usdc, USDC["decimals"]),
            unreg_int(max_usdc_amount, xSD["decimals"]),
            [self.usdc_token.address, self.xsd.address],
            agent.address,
            int(w3.eth.get_block('latest')['timestamp'] + DEADLINE_FROM_NOW)
        ).transact({
            'nonce': get_nonce(agent.address),
            'from' : agent.address,
            'gas': 8000000,
            'gasPrice': 1,
        })
        balance_after = self.xsd.caller({"from": agent.address, 'gas': 8000000}).balanceOf(agent.address)
        amount_bought = reg_int(balance_after - balance_before, xSD["decimals"])
        return amount_bought
        
    def sell(self, agent, xsd, min_usdc_amount):
        """
        Sell the given number of xSD for USDC. Returns the USDC received.
        """
        # get balance of xsd before and after
        balance_before = self.xsd.caller({"from": agent.address, 'gas': 8000000}).balanceOf(agent.address)

        self.usdc_token.ensure_approved(agent, UNIV2Router["addr"])

        if not agent.is_xsd_approved:
            self.xsd.functions.approve(UNIV2Router["addr"], UINT256_MAX).transact({
                'nonce': get_nonce(agent.address),
                'from' : agent.address,
                'gas': 8000000,
                'gasPrice': 1,
            })
            agent.is_xsd_approved = True

        # explore this more?
        slippage = 0.75
        min_usdc_amount = (min_usdc_amount * (1 - slippage))

        self.uniswap_router.functions.swapExactTokensForTokens(
            unreg_int(xsd, xSD["decimals"]),
            unreg_int(min_usdc_amount, USDC["decimals"]),
            [self.xsd.address, self.usdc_token.address],
            agent.address,
            int(w3.eth.get_block('latest')['timestamp'] + DEADLINE_FROM_NOW)
        ).transact({
            'nonce': get_nonce(agent.address),
            'from' : agent.address,
            'gas': 8000000,
            'gasPrice': 1,
        })
        # To get the balance after, we need to process events.
        self.usdc_token.update()
        balance_after = self.usdc_token[agent].to_wei()
        amount_sold = reg_int(abs(balance_after - balance_before), USDC["decimals"])
        return amount_sold
        
class DAO:
    """
    Represents the xSD DAO. Tracks xSD balance of DAO and total outstanding xSDS.
    """
    
    def __init__(self, contract, xsd, **kwargs):
        """
        Take keyword arguments to nspecify experimental parameters.
        """
        self.contract = contract  
        self.xsd_token = xsd    

    def xsd_supply(self):
        '''
        How many xSD exist?
        '''
        total = self.xsd_token.caller().totalSupply()
        return reg_int(total, xSD['decimals'])
        
    def total_coupons(self):
        """
        Get all outstanding unexpired coupons.
        """
        
        total = self.contract.caller().totalCoupons()
        return reg_int(total, xSD['decimals'])

    def total_coupons_for_agent(self, agent):
        total_coupons = 0
        for c_idx, c_exp in enumerate(agent.coupon_expirys):
            total_coupons += self.coupon_balance_at_epoch(agent.address, c_exp)
        if total_coupons == 0:
            agent.coupon_expirys = []
            agent.coupon_expiry_coupons = []
        return total_coupons

    def coupon_balance_at_epoch(self, address, epoch):
        ''' 
            returns the total coupon balance for an address
        '''
        total_coupons = self.contract.caller({'from' : address, 'gas': 8000000}).balanceOfCoupons(address, unreg_int(epoch, xSD["decimals"]))
        return total_coupons

    def epoch(self, address):
        return self.contract.caller({'from' : address, 'gas': 8000000}).epoch()
        
    def coupon_bid(self, agent, coupon_expiry, xsd_amount, max_coupon_amount):
        """
        Place a coupon bid
        """
        if not agent.is_dao_approved:
            self.xsd_token.functions.approve(self.contract.address, UINT256_MAX).transact({
                'nonce': get_nonce(agent.address),
                'from' : agent.address,
                'gas': 8000000,
                'gasPrice': 1,
            })
            agent.is_dao_approved = True

        self.contract.functions.placeCouponAuctionBid(
            unreg_int(coupon_expiry, xSD["decimals"]),
            unreg_int(xsd_amount, xSD["decimals"]),
            unreg_int(max_coupon_amount, xSD["decimals"])
        ).transact({
            'nonce': get_nonce(agent.address),
            'from' : agent.address,
            'gas': 8000000,
            'gasPrice': 1,
        })
        
    def redeem(self, agent, epoch_expired, coupons_to_redeem):
        """
        Redeem the given number of coupons. Expired coupons redeem to 0.
        
        Pays out the underlying and premium in an expansion phase, or only the
        underlying otherwise, or if the coupons are expired.
        
        Assumes everything is actually redeemable.
        """
        total_before_coupons = self.coupon_balance_at_epoch(agent.address, epoch_expired)
        self.contract.functions.redeemCoupons(
            unreg_int(epoch_expired, xSD["decimals"]),
            unreg_int(coupons_to_redeem, xSD["decimals"])
        ).transact({
            'nonce': get_nonce(agent.address),
            'from' : agent.address,
            'gas': 8000000,
            'gasPrice': 1,
        })
        total_after_coupons = self.coupon_balance_at_epoch(agent.address, epoch_expired)
            
        return total_before_coupons - total_after_coupons

    def token_balance_of(self, address):
        return reg_int(self.xsd_token.caller({'from' : address, 'gas': 8000000}).balanceOf(address), xSD["decimals"])
    
    def advance(self, address):
        before_advance = self.token_balance_of(address)
        self.contract.functions.advance().transact({
            'nonce': get_nonce(address),
            'from' : address,
            'gas': 8000000,
            'gasPrice': Web3.toWei(1, 'gwei'),
        })
        after_advance = self.token_balance_of(address)
        return after_advance - before_advance

def portion_dedusted(total, fraction):
    """
    Compute the amount of an asset to use, given that you have
    total and you don't want to leave behind dust.
    """
    
    if total - (fraction * total) <= 1:
        return total
    else:
        return fraction * total
        

def drop_zeroes(d):
    """
    Delete all items with zero value from the dict d, in place.
    """
    
    to_remove = [k for k, v in d.items() if v == 0]
    for k in to_remove:
        del d[k]
                        
                        
class Model:
    """
    Full model of the economy.
    """
    
    def __init__(self, dao, uniswap, usdc, uniswap_router, uniswap_token, xsd, agents, **kwargs):
        """
        Takes in experiment parameters and forwards them on to all components.
        """
        #pretty(dao.functions.__dict__)
        #sys.exit()
        self.uniswap = UniswapPool(uniswap, uniswap_router, uniswap_token, usdc, xsd, **kwargs)
        self.dao = DAO(dao, xsd, **kwargs)
        self.agents = []
        self.usdc_token = usdc
        self.uniswap_router = uniswap_router
        self.xsd_token = xsd
        self.max_eth = Balance.from_float(100000, 18)
        self.max_usdc = Balance.from_float(100000, USDC["decimals"])
        self.bootstrap_epoch = 20
        self.max_coupon_exp = 10000000
        self.max_coupon_premium = 10000000
        self.min_usdc_balance = Balance.from_float(200, USDC["decimals"])


        is_mint = False
        if w3.eth.get_block('latest')["number"] == block_offset:
            # THIS ONLY NEEDS TO BE RUN ON NEW CONTRACTS
            # TODO: tolerate redeployment or time-based generation
            is_mint = True
        
        for i in range(len(agents)):
            start_eth = random.random() * self.max_eth
            start_usdc = random.random() * self.max_usdc
            start_usdc_formatted = unreg_int(start_usdc, USDC["decimals"])
            address = agents[i]

            if is_mint:
                # need to mint USDC to the wallets for each agent
                usdc.contract.functions.mint(address, int(start_usdc_formatted)).transact({
                    'nonce': get_nonce(address),
                    'from' : address,
                    'gas': 8000000,
                    'gasPrice': 1,
                })

            agent = Agent(self.dao, uniswap, xsd, usdc, starting_eth=start_eth, wallet_address=address, **kwargs)
            self.agents.append(agent)
        
    def log(self, stream, seleted_advancer, header=False):
        """
        Log model statistics a TSV line.
        If header is True, include a header.
        """
        
        if header:
            stream.write("#block\tepoch\tprice\tsupply\tcoupons\tfaith\n")
        
        stream.write('{}\t{}\t{:.2f}\t{:.2f}\t{:.2f}\t{:.2f}\n'.format(
            w3.eth.get_block('latest')["number"],
            self.dao.epoch(seleted_advancer.address),
            self.uniswap.xsd_price(),
            self.dao.xsd_supply(),
            self.dao.total_coupons(),
            self.get_overall_faith())
        )
       
    def get_overall_faith(self):
        """
        What target should the system be trying to hit in xSD market cap?
        """
        
        return self.agents[0].get_faith(w3.eth.get_block('latest')["number"], self.uniswap.xsd_price(), self.dao.xsd_supply())
       
    def step(self):
        """
        Step the model Let all the agents act.
        
        Returns True if anyone could act.
        """
        
        provider.make_request("evm_increaseTime", [7201])
        #provider.make_request("debug_increaseTime", [7201])
        
        # Update caches to current chain state
        self.usdc_token.update()

        #randomly have an agent advance the epoch
        seleted_advancer = self.agents[int(random.random() * (len(self.agents) - 1))]
        xsd = self.dao.advance(seleted_advancer.address)
        seleted_advancer.xsd += xsd
        logger.info("Advance for {:.2f} xSD".format(xsd))

        (usdc_b, xsd_b) = self.uniswap.getTokenBalance()

        current_epoch = self.dao.epoch(seleted_advancer.address)

        epoch_start_price = self.uniswap.xsd_price()

        total_coupons = self.dao.total_coupons()
        
        logger.info("Block {}, epoch {}, price {:.2f}, supply {:.2f}, faith: {:.2f}, bonded {:2.1f}%, coupons: {:.2f}, liquidity {:.2f} xSD / {:.2f} USDC".format(
            w3.eth.get_block('latest')["number"], current_epoch, self.uniswap.xsd_price(), self.dao.xsd_supply(),
            self.get_overall_faith(), 0, total_coupons,
            xsd_b, usdc_b))
        
        anyone_acted = False

        #'''
        if self.dao.epoch(seleted_advancer.address) < self.bootstrap_epoch:
            anyone_acted = True
            return anyone_acted, seleted_advancer

        #'''

        for agent_num, a in enumerate(self.agents):
            # TODO: real strategy
            options = []
            if a.usdc > 0 and self.uniswap.operational():
                options.append("buy")
            if a.xsd > 0 and self.uniswap.operational():
                options.append("sell")
            '''
            TODO: CURRENTLY NO INCENTIVE TO BOND INTO LP OR DAO (EXCEPT FOR VOTING, MAY USE THIS TO DISTRUBTION EXPANSIONARY PROFITS)
            if a.xsd > 0:
                options.append("bond")
            if a.xsds > 0:
                options.append("unbond")
            '''
            # no point in buying coupons untill theres at least 10k usdc in the pool (so like 80-100 epoch effective warmup)
            if a.xsd > 0 and epoch_start_price < 1.0 and self.dao.epoch(a.address) > self.bootstrap_epoch and self.min_usdc_balance <= usdc_b:
                options.append("coupon_bid")
            # try any ways but handle traceback, faster than looping over all the epocks
            if epoch_start_price > 1.0 and total_coupons > 0 and self.dao.total_coupons_for_agent(a):
                options.append("redeem")
            if a.usdc > 0 and a.xsd > 0:
                options.append("provide_liquidity")
            if a.lp > 0:
                options.append("remove_liquidity")
                                
            if len(options) > 0:
                # We can act

                '''
                    TODO:
                        bond, unbond
                        
                    TOTEST:
                        bond, unbond
                    WORKS:
                        advance, provide_liquidity, remove_liquidity, buy, sell, coupon_bid, redeem, 
                '''
        
                strategy = a.get_strategy(w3.eth.get_block('latest')["number"], self.uniswap.xsd_price(), self.dao.xsd_supply())
                
                weights = [strategy[o] for o in options]
                
                action = random.choices(options, weights=weights)[0]
                
                # What fraction of the total possible amount of doing this
                # action will the agent do?
                commitment = random.random() * 0.1
                
                logger.debug("Agent {}: {}".format(a.address, action))
                
                if action == "buy":
                    # this will limit the size of orders avaialble
                    (usdc_b, xsd_b) = self.uniswap.getTokenBalance()
                    if xsd_b > 0 and usdc_b > 0:
                        usdc_in = portion_dedusted(
                            min(a.usdc, xsd_b.to_decimals(USDC['decimals'])),
                            commitment
                        )
                    else:
                        continue

                    try:
                        (max_amount, _) = self.uniswap_router.caller({'from' : a.address, 'gas': 8000000}).getAmountsIn(
                            unreg_int(usdc_in, USDC['decimals']), 
                            [self.usdc_token.address, self.xsd_token.address]
                        )
                        max_amount = reg_int(max_amount, xSD['decimals'])
                    except Exception as inst:
                        # not enough on market to fill bid
                        print({"agent": a.address, "error": inst, "action": "buy", "amount_in": usdc_in})
                        continue
                    
                    try:
                        price = self.uniswap.xsd_price()
                        logger.debug("Buy init {:.2f} xSD @ {:.2f} for {:.2f} USDC".format(usdc_in, price, max_amount))
                        xsd = self.uniswap.buy(a, usdc_in, max_amount)
                        a.xsd += xsd
                        logger.debug("Buy end {:.2f} xSD @ {:.2f} for {:.2f} USDC".format(xsd, price, usdc_in))
                        
                    except Exception as inst:
                        print({"agent": a.address, "error": inst, "action": "buy", "usdc_in": usdc_in, "max_amount": max_amount})
                        continue
                elif action == "sell":
                    # this will limit the size of orders avaialble
                    (usdc_b, xsd_b) = self.uniswap.getTokenBalance()
                    if xsd_b > 0 and usdc_b > 0:
                        xsd_out = min(
                            portion_dedusted(
                                a.xsd,
                                commitment
                            ),
                            usdc_b.to_decimals(xSD['decimals'])
                        )
                    else:
                        continue
                    
                    try:
                        (_, max_amount) = self.uniswap_router.caller({'from' : a.address, 'gas': 8000000}).getAmountsOut(
                            unreg_int(xsd_out, xSD['decimals']), 
                            [self.xsd_token.address, self.usdc_token.address]
                        )
                        max_amount = reg_int(max_amount, USDC['decimals'])
                    except Exception as inst:
                        print({"agent": a.address, "error": inst, "action": "sell", "amount_out": xsd_out})

                    try:
                        price = self.uniswap.xsd_price()
                        #logger.debug("Sell init {:.2f} xSD @ {:.2f} for {:.2f} USDC".format(xsd_out, price, max_amount))
                        usdc = self.uniswap.sell(a, xsd_out, max_amount)
                        a.xsd -= xsd_out
                        #logger.debug("Sell end {:.2f} xSD @ {:.2f} for {:.2f} USDC".format(xsd, price, usdc))
                    except Exception as inst:
                        print({"agent": a.address, "error": inst, "action": "sell", "xsd_out": xsd_out, "max_amount": max_amount, "account_xsd": a.xsd})
                elif action == "coupon_bid":
                    xsd_at_risk = portion_dedusted(a.xsd, commitment)
                    rand_epoch_expiry = Balance.from_float(int(random.random() * self.max_coupon_exp), xSD['decimals'])
                    rand_max_coupons = random.random() * self.max_coupon_premium * xsd_at_risk
                    try:
                        exact_expiry = rand_epoch_expiry + Balance.from_float(current_epoch, xSD['decimals'])
                        logger.info("Addr {} Bid to burn init {:.2f} xSD for {:.2f} coupons with expiry at epoch {}".format(a.address, xsd_at_risk, rand_max_coupons, exact_expiry))
                        self.dao.coupon_bid(a, rand_epoch_expiry, xsd_at_risk, rand_max_coupons)
                        a.total_coupons_bid += rand_max_coupons
                        a.coupon_expirys.append(exact_expiry)
                        a.coupon_expiry_coupons.append(rand_max_coupons)
                        logger.info("Addr {} Bid to burn end {:.2f} xSD for {:.2f} coupons with expiry at epoch {}".format(a.address, xsd_at_risk, rand_max_coupons, exact_expiry))
                    except Exception as inst:
                        print({"agent": a.address, "error": inst, "action": "coupon_bid", "exact_expiry": exact_expiry, "xsd_at_risk": xsd_at_risk})
                elif action == "redeem":
                    total_redeemed = 0
                    for c_idx, c_exp in enumerate(a.coupon_expirys):
                        try:
                            total_redeemed += self.dao.redeem(a, c_exp, a.coupon_expiry_coupons[c_idx])
                        except Exception as inst:
                            if 'revert SafeMath: subtraction overflow' not in str(inst):
                                print({"agent": a.address, "error": inst, "action": "redeem", "exact_expiry": c_exp, "coupons_tried": a.coupon_expiry_coupons[c_idx]})
                            else:
                                continue

                    a.xsd = self.dao.token_balance_of(agent.address)

                    if total_redeemed > 0:
                        a.total_coupons_bid -= total_redeemed
                        logger.info("Redeem {:.2f} coupons for {:.2f} xSD".format(total_redeemed, total_redeemed))
                elif action == "provide_liquidity":
                    min_xsd_needed = Balance(0, xSD['decimals'])
                    usdc = Balance(0, USDC['decimals'])
                    if float(a.xsd) < float(a.usdc):
                        usdc = portion_dedusted(a.xsd.to_decimals(USDC['decimals']), commitment)
                    else:
                        usdc = portion_dedusted(a.usdc, commitment)
                        
                    revs = self.uniswap.getReserves()
                    if revs[1] > 0:
                        min_xsd_needed = reg_int(self.uniswap_router.caller({'from' : a.address, 'gas': 8000000}).quote(unreg_int(usdc, USDC['decimals']), revs[0], revs[1]), xSD['decimals'])
                        if min_xsd_needed == 0:
                            price = self.uniswap.xsd_price()
                            min_xsd_needed = (usdc / float(price)).to_decimals(xSD['decimals'])
                    else:
                        min_xsd_needed = usdc.to_decimals(xSD['decimals'])
                        
                    if min_xsd_needed == 0:
                        continue

                    try:
                        #logger.debug("Provide {:.2f} xSD (of {:.2f} xSD) and {:.2f} USDC".format(min_xsd_needed, a.xsd, usdc))
                        after_lp = self.uniswap.provide_liquidity(a, min_xsd_needed, usdc)

                        usdc_a, xsd_a = self.uniswap.getTokenBalance()

                        diff_xsd = (xsd_a - xsd_b)
                        diff_usdc = (usdc_a - usdc_b)
                        
                        a.xsd = max(Balance(0, xSD['decimals']), a.xsd - diff_xsd)
                        a.lp = after_lp
                    except Exception as inst:
                        # SLENCE TRANSFER_FROM_FAILED ISSUES
                        #print({"agent": a.address, "error": inst, "action": "provide_liquidity", "min_xsd_needed": min_xsd_needed, "usdc": usdc})
                        continue
                elif action == "remove_liquidity":
                    lp = portion_dedusted(a.lp, commitment)
                    total_lp = self.uniswap.total_lp(a.address)
                    
                    usdc_b, xsd_b = self.uniswap.getTokenBalance()

                    min_xsd_amount = max(Balance(0, xSD['decimals']), Balance(float(xsd_b) * float(lp / float(total_lp)), xSD['decimals']))
                    min_usdc_amount = max(Balance(0, USDC['decimals']), Balance(float(usdc_b) * float(lp / float(total_lp)), USDC['decimals']))

                    if not (min_xsd_amount > 0 and min_usdc_amount > 0):
                        continue

                    try:
                        #logger.debug("Stop providing {:.2f} xSD and {:.2f} USDC".format(min_xsd_amount, min_usdc_amount))
                        after_lp = self.uniswap.remove_liquidity(a, lp, min_xsd_amount, min_usdc_amount)
                        usdc_a, xsd_a = self.uniswap.getTokenBalance()

                        diff_xsd = (xsd_b - xsd_a)
                        diff_usdc = (usdc_b - usdc_a)
                        
                        a.lp = after_lp
                        a.xsd += diff_xsd
                        
                    except Exception as inst:
                        print({"agent": a.address, "error": inst, "action": "remove_liquidity", "min_xsd_needed": min_xsd_amount, "usdc": min_usdc_amount})
                else:
                    raise RuntimeError("Bad action: " + action)
                    
                anyone_acted = True
            else:
                # It's normal for agents other then the first to advance to not be able to act on block 0.
                pass
        return anyone_acted, seleted_advancer

def main():
    """
    Main function: run the simulation.
    """
    
    logging.basicConfig(level=logging.INFO)
    
    max_accounts = 20
    print(w3.eth.get_block('latest')["number"])
    if w3.eth.get_block('latest')["number"] == block_offset:
        # THIS ONLY NEEDS TO BE RUN ON NEW CONTRACTS
        print(provider.make_request("evm_increaseTime", [1606348800]))

    print('Total Agents:',len(w3.eth.accounts[:max_accounts]))
    dao = w3.eth.contract(abi=DaoContract['abi'], address=xSDS["addr"])

    oracle = w3.eth.contract(abi=OracleContract['abi'], address=dao.caller({'from' : dao.address, 'gas': 8000000}).oracle())

    uniswap = w3.eth.contract(abi=UniswapPairContract['abi'], address=UNI["addr"])
    usdc = TokenProxy(w3.eth.contract(abi=USDCContract['abi'], address=USDC["addr"]))
    
    uniswap_router = w3.eth.contract(abi=UniswapRouterAbiContract['abi'], address=UNIV2Router["addr"])
    uniswap_token = w3.eth.contract(abi=PoolContract['abi'], address=UNIV2LP["addr"])

    xsd = w3.eth.contract(abi=DollarContract['abi'], address=dao.caller().dollar())
    print (dao.caller().dollar())
    
    # Make a model of the economy
    start_init = time.time()
    print ('INIT STARTED')
    model = Model(dao, uniswap, usdc, uniswap_router, uniswap_token, xsd, w3.eth.accounts[:max_accounts], min_faith=0.5E6, max_faith=1E6, use_faith=True)
    end_init = time.time()
    print ('INIT FINISHED', end_init - start_init, '(s)')

    # Make a log file for system parameters, for analysis
    stream = open("log.tsv", "w")
    
    for i in range(50000):
        # Every block
        # Try and tick the model
        start_iter = time.time()

        (anyone_acted, seleted_advancer) = model.step()
        if not anyone_acted:
            # Nobody could act
            print("Nobody could act")
            break
        end_iter = time.time()
        print('iter: %s, sys time %s' % (i, end_iter-start_iter))
        # Log system state
        model.log(stream, seleted_advancer, header=(i == 0))
        
if __name__ == "__main__":
    main()
