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

IS_DEBUG = False
is_try_model_mine = False
block_offset = 16

DEADLINE_FROM_NOW = 60 * 60 * 24 * 7 * 52
UINT256_MAX = 2**256 - 1
ZERO_ADDRESS = '0x0000000000000000000000000000000000000000'

deploy_data = None
with open("deploy_output.txt", 'r+') as f:
    deploy_data = f.read()

logger = logging.getLogger(__name__)
provider = Web3.HTTPProvider('http://localhost:7545', request_kwargs={"timeout": 60*300})
#provider = Web3.WebsocketProvider('ws://localhost:7545', websocket_timeout=60*30)
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
    logger.info(contract["deploy_slug"])
    contract["addr"] = deploy_data.split(contract["deploy_slug"])[1].split('\n')[0]
    logger.info('\t'+contract["addr"])


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

DaoContract = json.loads(open('./build/contracts/Implementation.json', 'r+').read())
USDCContract = json.loads(open('./build/contracts/TestnetUSDC.json', 'r+').read())
# Use the full Dollar ABI so we can interrogate the token for metadata
DollarContract = json.loads(open('./build/contracts/Dollar.json', 'r+').read())

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

def get_nonce(agent):
    if is_try_model_mine:
        current_block = int(w3.eth.get_block('latest')["number"])
        if current_block not in agent.seen_block:
            if (agent.current_block == 0):
                agent.current_block += 1
            else:
                agent.next_tx_count += 1
        else:
            agent.next_tx_count += 1
            agent.seen_block[current_block] = True
        return agent.next_tx_count 
    else:
        return w3.eth.getTransactionCount(agent.address, block_identifier=int(w3.eth.get_block('latest')["number"]))

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

def portion_dedusted(total, fraction):
    """
    Compute the amount of an asset to use, given that you have
    total and you don't want to leave behind dust.
    """
    
    if total - (fraction * total) <= 1:
        return total
    else:
        return fraction * total

# Because token balances need to be accuaate to the atomic unit, we can't store
# them as floats. Otherwise we might turn our float back into a token balance
# different from the balance we actually had, and try to spend more than we
# have. But also, it's ugly to throw around total counts of atomic units. So we
# use this class that represents a fixed-point token balance.
class Balance:
    def __init__(self, wei=0, decimals=0):
        self._wei = int(wei)
        self._decimals = int(decimals)
        
    def clone(self):
        """
        Make a deep copy so += and -= on us won't infect the copy.
        """
        return Balance(self._wei, self._decimals)
        
    def to_decimals(self, new_decimals):
        """
        Get a similar balance with a different number of decimals.
        """
        
        return Balance(self._wei * 10**new_decimals // 10**self._decimals, new_decimals)
        
    @classmethod
    def from_tokens(cls, n, decimals=0):
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

    def __round__(self):
        return Balance(int(math.floor(self._wei / 10**self._decimals)) * 10**self._decimals, self._decimals)
        
    def __format__(self, s):
        if s == '':
            return str(self)
        return float(self).__format__(s)
        
    def to_wei(self):
        return self._wei
        
    def decimals(self):
        return self._decimals

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
        
    def update(self, is_init_agents=[]):
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

        if is_init_agents:
            for agent in is_init_agents:
                # TODO: can we get a return value and a correct-as-of block in the same call?
                self.__balances[agent.address] = Balance(self.__contract.functions.balanceOf(agent.address).call(), self.__decimals)

            
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
            # Clone the stored balance so it doesn't get modified and upset the user
            return self.__balances[address].clone()
            
    def ensure_approved(self, owner, spender):
        """
        Approve the given spender to spend all the owner's tokens on their behalf.
        
        Owner and spender may be addresses or things with addresses.
        """
        spender = getattr(spender, 'address', spender)
        if spender not in self.__approved[getattr(owner, 'address', owner)]:
            # Issue an approval
            self.__contract.functions.approve(spender, UINT256_MAX).transact({
                'nonce': get_nonce(owner),
                'from' : getattr(owner, 'address', owner),
                'gas': 8000000,
                'gasPrice': 1,
            })
            self.__approved[owner].add(spender)
            
    def from_wei(self, wei):
        """
        Convert a number of wei (possibly a float) into a Balance with the
        right number of decimals.
        """
        
        return Balance(wei, self.__decimals)
        
    def from_tokens(self, tokens):
        """
        Convert a number of token units (possibly a float) into a Balance with
        the right number of decimals.
        """
        
        return Balance.from_tokens(tokens, self.__decimals)
        
class Agent:
    """
    Represents an agent. Tracks all the agent's balances.
    """
    
    def __init__(self, dao, uniswap_pair, xsd_token, usdc_token, **kwargs):
 
        # xSD TokenProxy
        self.xsd_token = xsd_token
        # USDC TokenProxy 
        self.usdc_token = usdc_token
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

        #coupon expirys
        self.coupon_expirys = []
        # how many times coupons have been redeemmed
        self.redeem_count = 0

        self.dao = dao

        # current coupon assigned index of epoch
        self.max_coupon_epoch_index = 0

        # Uniswap Pair TokenProxy
        self.uniswap_pair_token = uniswap_pair

        # keeps track of latest block seen for nonce tracking/tx
        self.seen_block = {}
        self.next_tx_count = w3.eth.getTransactionCount(self.address, block_identifier=int(w3.eth.get_block('latest')["number"]))
        self.current_block = 0

        if kwargs.get("is_mint", False):
            # need to mint USDC to the wallets for each agent
            start_usdc_formatted = kwargs.get("starting_usdc", Balance(0, USDC["decimals"]))
            self.usdc_token.contract.functions.mint(self.address, unreg_int(start_usdc_formatted, USDC['decimals'])).transact({
                'nonce': get_nonce(self),
                'from' : self.address,
                'gas': 8000000,
                'gasPrice': 1,
            })
        
    @property
    def xsd(self):
        """
        Get the current balance in USDC from the TokenProxy.
        """
        return self.xsd_token[self]
    
    @property
    def usdc(self):
        """
        Get the current balance in USDC from the TokenProxy.
        """
        return self.usdc_token[self]

    @property
    def lp(self):
        """
        Get the current balance in Uniswap LP Shares from the TokenProxy.
        """
        return self.uniswap_pair_token[self]

    @property
    def coupons(self):
        """
        Get the current balance in of coupons for agent
        """
        return self.dao.total_coupons_for_agent(self)
    
    def __str__(self):
        """
        Turn into a readable string summary.
        """
        return "Agent(xSD={:.2f}, usdc={:.2f}, eth={}, lp={}, coupons={:.2f})".format(
            self.xsd, self.usdc, self.eth, self.lp, self.coupons)

        
    def get_strategy(self, block, price, total_supply, total_coupons):
        """
        Get weights, as a dict from action to float, as a function of the price.
        """
        
        strategy = collections.defaultdict(lambda: 1.0)
        
        # TODO: real (learned? adversarial? GA?) model of the agents
        # TODO: agent preferences/utility function

        # People are fast to coupon bid to get in front of redemption queue
        strategy["coupon_bid"] = 2.0
        
        if price >= 1.0:
            # No rewards for expansion by itself
            strategy["bond"] = 0
            # And not unbond
            strategy["unbond"] = 0
            # Or redeem if possible
            # strategy["redeem"] = 10000000000000.0 if self.coupons > 0 else 0
            # incetive to buy above 1 is for more coupons
            strategy["buy"] = 1.0
            strategy["sell"] = 1.0
        else:
            # We probably want to unbond due to no returns
            strategy["unbond"] = 0
            # And not bond
            strategy["bond"] = 0
       
        if self.use_faith:
            # Vary our strategy based on how much xSD we think ought to exist
            if price * total_supply > self.get_faith(block, price, total_supply):
                # There is too much xSD, so we want to sell
                strategy["sell"] = 10.0 if ((self.coupons > 0) and (price > 1.0)) else 2.0
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
    
    def __init__(self, uniswap, uniswap_router, uniswap_token, usdc_token, xsd_token, **kwargs):
        self.uniswap_pair_token = uniswap
        self.uniswap_router = uniswap_router
        self.uniswap_token = uniswap_token
        self.usdc_token = usdc_token
        self.xsd_token = xsd_token
    
    def operational(self):
        """
        Return true if buying and selling is possible.
        """
        reserve = self.getReserves()
        token0Balance = reserve[0]
        token1Balance = reserve[1]
        return token0Balance > 0 and token1Balance > 0
    
    def getToken0(self):
        exchange = self.uniswap_pair_token.contract
        return exchange.functions.token0().call()

    def getReserves(self):
        exchange = self.uniswap_pair_token.contract
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
            success = False
            while not success:
                try:
                    price = self.getInstantaneousPrice()
                    success = True
                    return price
                except Exception as inst:
                    """
                        Seen:
                            raise ContractLogicError(f'execution reverted: {response["error"]["message"]}')
                            web3.exceptions.ContractLogicError: execution reverted: Reverting to invalid state checkpoint failed
                    """
                    logger.info({"function": "xsd_price", "error": inst })
        else:
            return 1.0

    def total_lp(self):
        return reg_int(self.uniswap_pair_token.contract.functions.totalSupply().call(), UNIV2Router['decimals'])
        
    def provide_liquidity(self, agent, xsd, usdc):
        """
        Provide liquidity.
        """        
        
        self.usdc_token.ensure_approved(agent, UNIV2Router["addr"])
        self.xsd_token.ensure_approved(agent, UNIV2Router["addr"])
        
        slippage = 0.01
        min_xsd_amount = (xsd * (1 - slippage))
        min_usdc_amount = (usdc * (1 - slippage))

        if IS_DEBUG:
            # Make sure we can afford this
            xsd_wei = self.xsd_token[agent].to_wei()
            usdc_wei = self.usdc_token[agent].to_wei()

            assert xsd_wei >= xsd.to_wei()
            assert usdc_wei >= usdc.to_wei()

        rv = self.uniswap_router.functions.addLiquidity(
            self.xsd_token.address,
            self.usdc_token.address,
            unreg_int(xsd, xSD['decimals']),
            unreg_int(usdc, USDC['decimals']),
            unreg_int(min_xsd_amount, xSD['decimals']),
            unreg_int(min_usdc_amount, USDC['decimals']),
            agent.address,
            (int(w3.eth.get_block('latest')['timestamp']) + DEADLINE_FROM_NOW)
        ).transact({
            'nonce': get_nonce(agent),
            'from' : agent.address,
            'gas': 8000000,
            'gasPrice': 1,
        })
        
    def remove_liquidity(self, agent, shares, min_xsd_amount, min_usdc_amount):
        """
        Remove liquidity for the given number of shares.

        """
        self.uniswap_pair_token.ensure_approved(agent, UNIV2Router["addr"])

        slippage = 0.01
        min_xsd_amount = (min_xsd_amount * (1 - slippage))
        min_usdc_amount = (min_usdc_amount * (1 - slippage))

        self.uniswap_router.functions.removeLiquidity(
            self.xsd_token.address,
            self.usdc_token.address,
            unreg_int(shares, UNIV2Router['decimals']),
            unreg_int(min_xsd_amount, xSD['decimals']),
            unreg_int(min_usdc_amount, USDC['decimals']),
            agent.address,
            int(w3.eth.get_block('latest')['timestamp'] + DEADLINE_FROM_NOW)
            
        ).transact({
            'nonce': get_nonce(agent),
            'from' : agent.address,
            'gas': 8000000,
            'gasPrice': 1,
        })
        
    def buy(self, agent, usdc, max_usdc_amount):
        """
        Spend the given number of USDC to buy xSD.
        ['swapTokensForExactTokens(uint256,uint256,address[],address,uint256)']
        """  
        
        self.usdc_token.ensure_approved(agent, UNIV2Router["addr"])
        self.xsd_token.ensure_approved(agent, UNIV2Router["addr"])

        # explore this more?
        slippage = 0.01
        max_usdc_amount = (max_usdc_amount * (1 + slippage))

        self.uniswap_router.functions.swapExactTokensForTokens(
            usdc.to_wei(),
            max_usdc_amount.to_wei(),
            [self.usdc_token.address, self.xsd_token.address],
            agent.address,
            int(w3.eth.get_block('latest')['timestamp'] + DEADLINE_FROM_NOW)
        ).transact({
            'nonce': get_nonce(agent),
            'from' : agent.address,
            'gas': 8000000,
            'gasPrice': 1,
        })
        
    def sell(self, agent, xsd, min_usdc_amount, advancer, uniswap_usdc_supply):
        """
        Sell the given number of xSD for USDC.
        """

        self.usdc_token.ensure_approved(agent, UNIV2Router["addr"])
        self.xsd_token.ensure_approved(agent, UNIV2Router["addr"])

        # explore this more?
        slippage = 0.99 if (advancer.address == agent.address) or ((agent.redeem_count > 0) and agent.xsd > uniswap_usdc_supply) else 0.01
        min_usdc_amount = (min_usdc_amount * (1 - slippage))

        self.uniswap_router.functions.swapExactTokensForTokens(
            xsd.to_wei(),
            min_usdc_amount.to_wei(),
            [self.xsd_token.address, self.usdc_token.address],
            agent.address,
            int(w3.eth.get_block('latest')['timestamp'] + DEADLINE_FROM_NOW)
        ).transact({
            'nonce': get_nonce(agent),
            'from' : agent.address,
            'gas': 8000000,
            'gasPrice': 1,
        })

    def update(self, is_init_agents=[]):
        self.uniswap_pair_token.update(is_init_agents=is_init_agents)

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
        return self.xsd_token.totalSupply

    def total_coupons_at_epoch(self, address, epoch):
        total_coupons = self.contract.caller({'from' : address, 'gas': 8000000}).outstandingCoupons(epoch)
        return Balance.from_tokens(total_coupons, xSD['decimals'])
        
    def total_coupons(self):
        """
        Get all outstanding unexpired coupons.
        """
        
        total = self.contract.caller().totalCoupons()
        return reg_int(total, xSD['decimals'])

    def total_coupons_for_agent(self, agent):
        total_coupons = self.contract.caller({'from' : agent.address, 'gas': 8000000}).outstandingCouponsForAddress(agent.address)
        return total_coupons

    def coupon_balance_at_epoch(self, address, epoch):
        ''' 
            returns the total coupon balance for an address
        '''
        if epoch == 0:
            return 0
        total_coupons = self.contract.caller({'from' : address, 'gas': 8000000}).balanceOfCoupons(address, epoch)
        return total_coupons

    def get_coupon_expirirations(self, agent):
        '''
            Return a list of coupon expirations for an address from last time called
        '''
        epochs = []
        epoch_index_max = self.contract.caller({'from' : agent.address, 'gas': 8000000}).getCouponsCurrentAssignedIndex(agent.address)

        for i in range(agent.max_coupon_epoch_index, epoch_index_max):
            t_epoch = self.contract.caller({'from' : agent.address, 'gas': 8000000}).getCouponsAssignedAtEpoch(agent.address, i)
            epochs.append(t_epoch)

        agent.max_coupon_epoch_index = epoch_index_max
        agent.coupon_expirys += epochs
        return agent.coupon_expirys

    def epoch(self, address):
        return self.contract.caller({'from' : address, 'gas': 8000000}).epoch()
        
    def has_coupon_bid(self):
        """
        Return True if the DAO implements coupon bidding.
        """
        return hasattr(self.contract.functions, 'placeCouponAuctionBid')
        
    def coupon_bid(self, agent, coupon_expiry, xsd_amount, max_coupon_amount):
        """
        Place a coupon bid
        """
        
        self.xsd_token.ensure_approved(agent, self.contract)

        self.contract.functions.placeCouponAuctionBid(
            coupon_expiry,
            unreg_int(xsd_amount, xSD["decimals"]),
            unreg_int(max_coupon_amount, xSD["decimals"])
        ).transact({
            'nonce': get_nonce(agent),
            'from' : agent.address,
            'gas': 8000000,
            'gasPrice': 1,
        })
        
    def redeem(self, agent, epoch_expired):
        """
        Redeem the given number of coupons. Expired coupons redeem to 0.
        
        Pays out the underlying and premium in an expansion phase, or only the
        underlying otherwise, or if the coupons are expired (or nothing depending on the behavior of the protocol).
        
        Assumes everything is actually redeemable.
        """
        total_coupons = self.coupon_balance_at_epoch(agent.address, epoch_expired)
        if total_coupons == 0:
            return

        self.contract.functions.redeemCoupons(
            epoch_expired,
            total_coupons
        ).transact({
            'nonce': get_nonce(agent),
            'from' : agent.address,
            'gas': 8000000,
            'gasPrice': 1,
        })

    def advance(self, agent):
        """
        Advance the epoch. Return the balance of XSD created.
        
        Note that if advance() does any kind of auction settlement or other
        operations, the reported reward may be affected by those transfers.
        """
        global provider
        global w3
        epoch_before = self.epoch(agent.address)
        provider.make_request("evm_increaseTime", [7201])
        before_advance = self.xsd_token[agent.address]
        
        self.contract.functions.advance().transact({
            'nonce': get_nonce(agent),
            'from' : agent.address,
            'gas': 8000000,
            'gasPrice': Web3.toWei(1, 'gwei'),
        })
        
        # need to force mine block after every advance or the state wont change in token balance
        if is_try_model_mine:
            provider.make_request("evm_mine", [])
                        
class Model:
    """
    Full model of the economy.
    """
    
    def __init__(self, dao, uniswap, usdc, uniswap_router, uniswap_token, xsd, agents, **kwargs):
        """
        Takes in experiment parameters and forwards them on to all components.
        """
        self.uniswap = UniswapPool(uniswap, uniswap_router, uniswap_token, usdc, xsd, **kwargs)
        self.dao = DAO(dao, xsd, **kwargs)
        self.agents = []
        self.usdc_token = usdc
        self.uniswap_router = uniswap_router
        self.xsd_token = xsd
        self.max_eth = Balance.from_tokens(100000, 18)
        self.max_usdc = self.usdc_token.from_tokens(100000)
        self.bootstrap_epoch = 2
        self.max_coupon_exp = 131400
        self.max_coupon_premium = 10 #redoo with 10 with same settings
        self.min_usdc_balance = self.usdc_token.from_tokens(200)


        is_mint = is_try_model_mine
        if w3.eth.get_block('latest')["number"] == block_offset:
            # THIS ONLY NEEDS TO BE RUN ON NEW CONTRACTS
            # TODO: tolerate redeployment or time-based generation
            is_mint = True
        
        total_tx_submitted = len(agents) 
        for i in range(len(agents)):

            start_eth = random.random() * self.max_eth
            start_usdc = random.random() * self.max_usdc
            
            address = agents[i]
            agent = Agent(self.dao, uniswap, xsd, usdc, starting_eth=start_eth, starting_usdc=start_usdc, wallet_address=address, is_mint=is_mint, **kwargs)
            #print (agent)  
            self.agents.append(agent)
        #sys.exit()

        if is_try_model_mine:
            for i in range(0, total_tx_submitted):
                provider.make_request("evm_mine", [])

        # Update caches to current chain state
        self.usdc_token.update(is_init_agents=self.agents)
        self.xsd_token.update(is_init_agents=self.agents)
        self.uniswap.update(is_init_agents=self.agents)
        
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
        global provider
        global w3
        # Update caches to current chain state
        self.usdc_token.update()
        self.xsd_token.update()
        self.uniswap.update()

        #randomly have an agent advance the epoch
        seleted_advancer = self.agents[int(random.random() * (len(self.agents) - 1))]
        self.dao.advance(seleted_advancer)
        logger.info("Earliest Non Dead Auction: {}".format(self.dao.contract.caller({'from' : seleted_advancer.address, 'gas': 8000000}).getEarliestDeadAuctionEpoch()))
        logger.info("Advance from {}".format(seleted_advancer.address))

        (usdc_b, xsd_b) = self.uniswap.getTokenBalance()
        revs = self.uniswap.getReserves()

        current_epoch = self.dao.epoch(seleted_advancer.address)

        epoch_start_price = self.uniswap.xsd_price()

        dao_xsd_supply = self.dao.xsd_supply()

        total_coupons = self.dao.total_coupons()
        
        logger.info("Block {}, epoch {}, price {:.2f}, supply {:.2f}, faith: {:.2f}, bonded {:2.1f}%, coupons: {:.2f}, liquidity {:.2f} xSD / {:.2f} USDC".format(
            w3.eth.get_block('latest')["number"], current_epoch, epoch_start_price, dao_xsd_supply,
            self.get_overall_faith(), 0, total_coupons,
            xsd_b, usdc_b)
        )
        
        anyone_acted = False
        if current_epoch < self.bootstrap_epoch:
            anyone_acted = True
            return anyone_acted, seleted_advancer


        total_tx_submitted = 0
        total_coupoun_bidders = 0
        random.shuffle(self.agents)

        is_uni_op = self.uniswap.operational()    

        for agent_num, a in enumerate(self.agents):
            # try to redeem any outstanding coupons here first to better
            if epoch_start_price > 1.0 and total_coupons > 0:
                if a.coupons > 0:
                    # if agent has coupons
                    # logger.info("COUPON EXP: Agent {}, exp_epochs: {}".format(a.address, json.dumps(a.coupon_expirys)))
                    if len(a.coupon_expirys) > 0:
                        a.redeem_count += 1
                        to_delete_index = []             
                        for c_idx, c_exp in enumerate(a.coupon_expirys):
                            try:
                                self.dao.redeem(a, c_exp)
                                to_delete_index.append(c_idx)
                            except Exception as inst:
                                if 'revert SafeMath: subtraction overflow' not in str(inst):
                                    logger.info({"agent": a.address, "error": inst, "action": "redeem", "exact_expiry": c_exp})
                                else:
                                    continue

                        for d_idx in to_delete_index:
                            del a.coupon_expirys[d_idx] 

        for agent_num, a in enumerate(self.agents):            
            # TODO: real strategy
            options = []

            start_tx_count = a.next_tx_count

            if a.usdc > 0 and is_uni_op:
                options.append("buy")
            if a.xsd > 0 and is_uni_op:
                options.append("sell")
            '''
            TODO: CURRENTLY NO INCENTIVE TO BOND INTO LP OR DAO (EXCEPT FOR VOTING, MAY USE THIS TO DISTRUBTION EXPANSIONARY PROFITS)
            if a.xsd > 0:
                options.append("bond")
            if a.xsds > 0:
                options.append("unbond")
            if a.coupons > 0 and epoch_start_price > 1.0:
                options.append("redeem")
            '''
            if a.xsd >= Balance.from_tokens(1, xSD['decimals']) and self.dao.has_coupon_bid():
                options.append("coupon_bid")
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
        
                strategy = a.get_strategy(w3.eth.get_block('latest')["number"], self.uniswap.xsd_price(), dao_xsd_supply, total_coupons)
                
                weights = [strategy[o] for o in options]
                
                action = random.choices(options, weights=weights)[0]
                
                # What fraction of the total possible amount of doing this
                # action will the agent do?
                commitment = random.random() * 0.1
                
                if action == "buy":
                    # this will limit the size of orders avaialble
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
                        logger.info({"agent": a.address, "error": inst, "action": "buy", "amount_in": usdc_in})
                        continue
                    
                    try:
                        price = epoch_start_price
                        #logger.debug("Buy init {:.2f} xSD @ {:.2f} for {:.2f} USDC".format(usdc_in, price, max_amount))
                        self.uniswap.buy(a, usdc_in, max_amount)
                        #logger.debug("Buy end {:.2f} xSD @ {:.2f} for {:.2f} USDC".format(max_amount, price, usdc_in))
                        
                    except Exception as inst:
                        logger.info({"agent": a.address, "error": inst, "action": "buy", "usdc_in": usdc_in, "max_amount": max_amount})
                        continue
                elif action == "sell":
                    # this will limit the size of orders avaialble
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
                        logger.info({"agent": a.address, "error": inst, "action": "sell", "amount_out": xsd_out})

                    try:
                        price = epoch_start_price
                        #logger.debug("Sell init {:.2f} xSD @ {:.2f} for {:.2f} USDC".format(xsd_out, price, max_amount))
                        self.uniswap.sell(a, xsd_out, max_amount, seleted_advancer, usdc_b.to_decimals(xSD['decimals']))
                        #logger.debug("Sell end {:.2f} xSD @ {:.2f} for {:.2f} USDC".format(xsd_out, price, usdc))
                    except Exception as inst:
                        logger.info({"agent": a.address, "error": inst, "action": "sell", "xsd_out": xsd_out, "max_amount": max_amount, "account_xsd": a.xsd})
                elif action == "coupon_bid":
                    '''
                        TODO: NEED TO FIGURE OUT BETTER WAY TO TRACK THIS?
                    '''
                    xsd_at_risk = max(Balance.from_tokens(1, 18), portion_dedusted(a.xsd, commitment))
                    rand_epoch_expiry = int(random.random() * self.max_coupon_exp)
                    rand_max_coupons =  round(int(math.floor(random.random() * self.max_coupon_premium)) * xsd_at_risk)
                    try:
                        exact_expiry = rand_epoch_expiry + current_epoch
                        #logger.info("Addr {} Bid to burn init {:.2f} xSD for {:.2f} coupons with expiry at epoch {}".format(a.address, xsd_at_risk, rand_max_coupons, exact_expiry))
                        self.dao.coupon_bid(a, rand_epoch_expiry, xsd_at_risk, rand_max_coupons)
                        self.dao.get_coupon_expirirations(a)
                        #logger.info("Addr {} Bid to burn end {:.2f} xSD for {:.2f} coupons with expiry at epoch {}".format(a.address, xsd_at_risk, rand_max_coupons, exact_expiry))
                        total_coupoun_bidders += 1
                    except Exception as inst:
                        logger.info({"agent": a.address, "error": inst, "action": "coupon_bid", "exact_expiry": exact_expiry, "xsd_at_risk": xsd_at_risk})
                elif action == "provide_liquidity":
                    min_xsd_needed = Balance(0, xSD['decimals'])
                    usdc = Balance(0, USDC['decimals'])
                    if float(a.xsd) < float(a.usdc):
                        usdc = portion_dedusted(a.xsd.to_decimals(USDC['decimals']), commitment)
                    else:
                        usdc = portion_dedusted(a.usdc, commitment)
                        
                    if revs[1] > 0:
                        min_xsd_needed = reg_int(self.uniswap_router.caller({'from' : a.address, 'gas': 8000000}).quote(unreg_int(usdc, USDC['decimals']), revs[0], revs[1]), xSD['decimals'])
                        if min_xsd_needed == 0:
                            price = epoch_start_price
                            min_xsd_needed = (usdc / float(price)).to_decimals(xSD['decimals'])
                    else:
                        min_xsd_needed = usdc.to_decimals(xSD['decimals'])
                        
                    if min_xsd_needed == 0:
                        continue

                    try:
                        #logger.debug("Provide {:.2f} xSD (of {:.2f} xSD) and {:.2f} USDC".format(min_xsd_needed, a.xsd, usdc))
                        self.uniswap.provide_liquidity(a, min_xsd_needed, usdc)
                    except Exception as inst:
                        # SLENCE TRANSFER_FROM_FAILED ISSUES
                        #logger.info({"agent": a.address, "error": inst, "action": "provide_liquidity", "min_xsd_needed": min_xsd_needed, "usdc": usdc})
                        continue
                elif action == "remove_liquidity":
                    lp = portion_dedusted(a.lp, commitment)
                    total_lp = self.uniswap.total_lp()
                    
                    usdc_b, xsd_b = self.uniswap.getTokenBalance()

                    min_xsd_amount = max(Balance(0, xSD['decimals']), Balance(float(xsd_b) * float(lp / float(total_lp)), xSD['decimals']))
                    min_usdc_amount = max(Balance(0, USDC['decimals']), Balance(float(usdc_b) * float(lp / float(total_lp)), USDC['decimals']))

                    if not (min_xsd_amount > 0 and min_usdc_amount > 0):
                        continue

                    try:
                        #logger.debug("Stop providing {:.2f} xSD and {:.2f} USDC".format(min_xsd_amount, min_usdc_amount))
                        self.uniswap.remove_liquidity(a, lp, min_xsd_amount, min_usdc_amount)
                    except Exception as inst:
                        logger.info({"agent": a.address, "error": inst, "action": "remove_liquidity", "min_xsd_needed": min_xsd_amount, "usdc": min_usdc_amount})
                else:
                    raise RuntimeError("Bad action: " + action)
                    
                anyone_acted = True
            else:
                # It's normal for agents other then the first to advance to not be able to act on block 0.
                pass

            end_tx_count = a.next_tx_count

            total_tx_submitted += (end_tx_count - start_tx_count)

        if is_try_model_mine:
            # mine a block after every iteration for every tx sumbitted during round
            logging.info("{} sumbitted, mining blocks for them now, {} coupon bidders".format(
                total_tx_submitted, total_coupoun_bidders)
            )
            for i in range(0, total_tx_submitted):
                provider.make_request("evm_mine", [])
        else:
            logging.info("{} coupon bidders".format(
                total_coupoun_bidders)
            )

        return anyone_acted, seleted_advancer

def main():
    """
    Main function: run the simulation.
    """
    
    logging.basicConfig(level=logging.INFO)
    
    max_accounts = 20
    logger.info(w3.eth.get_block('latest')["number"])
    if w3.eth.get_block('latest')["number"] == block_offset:
        # THIS ONLY NEEDS TO BE RUN ON NEW CONTRACTS
        logger.info(provider.make_request("evm_increaseTime", [1606348800]))

    logger.info('Total Agents: {}'.format(len(w3.eth.accounts[:max_accounts])))
    dao = w3.eth.contract(abi=DaoContract['abi'], address=xSDS["addr"])
    logger.info('Dao is at: {}'.format(dao.address))
    

    oracle = w3.eth.contract(abi=OracleContract['abi'], address=dao.caller({'from' : dao.address, 'gas': 8000000}).oracle())
    logger.info("Oracle is at: {}".format(oracle.address))

    uniswap = TokenProxy(w3.eth.contract(abi=UniswapPairContract['abi'], address=UNI["addr"]))
    usdc = TokenProxy(w3.eth.contract(abi=USDCContract['abi'], address=USDC["addr"]))
    
    uniswap_router = w3.eth.contract(abi=UniswapRouterAbiContract['abi'], address=UNIV2Router["addr"])
    uniswap_token = w3.eth.contract(abi=PoolContract['abi'], address=UNIV2LP["addr"])

    xsd = TokenProxy(w3.eth.contract(abi=DollarContract['abi'], address=dao.caller().dollar()))
    logger.info(dao.caller().dollar())
    
    # Make a model of the economy
    start_init = time.time()
    logger.info('INIT STARTED')
    model = Model(dao, uniswap, usdc, uniswap_router, uniswap_token, xsd, w3.eth.accounts[:max_accounts], min_faith=0.5E6, max_faith=1E6, use_faith=True)
    end_init = time.time()
    logger.info('INIT FINISHED {} (s)'.format(end_init - start_init))

    # Make a log file for system parameters, for analysis
    stream = open("log.tsv", "a+")
    
    for i in range(50000):
        # Every block
        # Try and tick the model
        start_iter = time.time()

        (anyone_acted, seleted_advancer) = model.step()
        if not anyone_acted:
            # Nobody could act
            logger.info("Nobody could act")
            break
        end_iter = time.time()
        logger.info('iter: %s, sys time %s' % (i, end_iter-start_iter))
        # Log system state
        model.log(stream, seleted_advancer, header=(i == 0))
        
if __name__ == "__main__":
    main()
