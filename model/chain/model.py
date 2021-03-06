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
import os
import base64
import mmap
from eth_abi import encode_single, decode_single
from web3 import Web3

IS_DEBUG = False
is_try_model_mine = False
max_accounts = 40
block_offset = 18 + max_accounts
tx_pool_latency = 0.01

DEADLINE_FROM_NOW = 60 * 60 * 24 * 7 * 52
UINT256_MAX = 2**256 - 1
ZERO_ADDRESS = '0x0000000000000000000000000000000000000000'
MMAP_FILE = '/tmp/avax-cchain-nonces'

deploy_data = None
with open("deploy_output.txt", 'r+') as f:
    deploy_data = f.read()

logger = logging.getLogger(__name__)
#provider = Web3.HTTPProvider('http://127.0.0.1:7545/ext/bc/C/rpc', request_kwargs={"timeout": 60*300})
provider = Web3.WebsocketProvider('ws://127.0.0.1:9545/ext/bc/C/ws', websocket_timeout=60*300)

'''
curl -X POST --data '{ "jsonrpc":"2.0", "id" :1, "method" :"platform.incrementTimeTx", "params" :{ "time": 10000 }}' -H 'content-type:application/json;' http://127.0.0.1:9545/ext/P

curl -X POST --data '{ "jsonrpc":"2.0", "id" :1, "method" :"evm.increaseTime", "params" : [0]}' -H 'content-type:application/json;' http://127.0.0.1:9545/ext/bc/C/rpc
'''
providerAvax = Web3.HTTPProvider('http://127.0.0.1:9545/ext/bc/C/avax', request_kwargs={"timeout": 60*300})
w3 = Web3(provider)
from web3.middleware import geth_poa_middleware
w3.middleware_onion.inject(geth_poa_middleware, layer=0)

w3.eth.defaultAccount = w3.eth.accounts[0]
logger.info(w3.eth.blockNumber)
logger.info(w3.clientVersion)
#sys.exit()

# from (Pangolin pair is at:)
PGL = {
  "addr": '',
  "decimals": 18,
  "symbol": 'PGL',
  "deploy_slug": "Pangolin pair is at: "
}

# USDT is at: 
USDT = {
  "addr": '',
  "decimals": 6,
  "symbol": 'USDT',
  "deploy_slug": "USDT is at: "
}

#Pool is at: 
PGLLP = {
    "addr": '',
    "decimals": 18,
    "deploy_slug": "Pool is at: "
}

#PangolinRouter is at: 
PGLRouter = {
    "addr": "",
    "decimals": 12,
    "deploy_slug": "PangolinRouter is at: "
}

for contract in [PGL, USDT, PGLLP, PGLRouter]:
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

AGENT_NONCES = {}

DaoContract = json.loads(open('./build/contracts/Implementation.json', 'r+').read())
USDTContract = json.loads(open('./build/contracts/TestnetUSDT.json', 'r+').read())
# Use the full Dollar ABI so we can interrogate the token for metadata
DollarContract = json.loads(open('./build/contracts/Dollar.json', 'r+').read())

PangolinPairContract = json.loads(open('./build/contracts/IPangolinPair.json', 'r+').read())
PangolinRouterAbiContract = json.loads(open('./node_modules/@pangolindex/exchange-contracts/artifacts/contracts/pangolin-periphery/interfaces/IPangolinRouter.sol/IPangolinRouter.json', 'r+').read())
TokenContract = json.loads(open('./build/contracts/Root.json', 'r+').read())
PoolContract = json.loads(open('./build/contracts/Pool.json', 'r+').read())
OracleContract = json.loads(open('./build/contracts/MockOracle.json', 'r+').read())

def get_addr_from_contract(contract):
    return contract["networks"][str(sorted(map(int,contract["networks"].keys()))[0])]["address"]

xSD['addr'] = get_addr_from_contract(DaoContract)
xSDS['addr'] = get_addr_from_contract(TokenContract)


avax_cchain_nonces = None
mm = None

def lock_nonce(agent):
    global mm
    # DECODE START
    if not mm:
        mm = mmap.mmap(avax_cchain_nonces.fileno(), 0)

    mm.seek(0)
    raw_data_cov = mm.read().decode('utf8')
    nonce_data = json.loads(raw_data_cov)

    nonce_data['locked'] = '1'
    out_data = bytes(json.dumps(nonce_data), 'utf8')
    mm[:] = out_data

def get_nonce(agent):
    global mm
    # DECODE START
    if not mm:
        mm = mmap.mmap(avax_cchain_nonces.fileno(), 0)

    mm.seek(0)
    raw_data_cov = mm.read().decode('utf8')
    nonce_data = json.loads(raw_data_cov)
    current_block = int(w3.eth.get_block('latest')["number"])

    while nonce_data['locked'] == '1':
        mm.seek(0)
        raw_data_cov = mm.read().decode('utf8')
        nonce_data = json.loads(raw_data_cov)
        mm.seek(0)
        continue

    # locked == '1', unlocked == '0'
    
    nonce_data[agent.address]["seen_block"] = decode_single('uint256', base64.b64decode(nonce_data[agent.address]["seen_block"]))
    nonce_data[agent.address]["next_tx_count"] = decode_single('uint256', base64.b64decode(nonce_data[agent.address]["next_tx_count"]))
    # DECODE END

    if current_block != nonce_data[agent.address]["seen_block"]:
        if (nonce_data[agent.address]["seen_block"] == 0):
            nonce_data[agent.address]["seen_block"] = current_block
            nonce_data[agent.address]["next_tx_count"] = agent.next_tx_count
        else:
            nonce_data[agent.address]["seen_block"] = current_block
            nonce_data[agent.address]["next_tx_count"] = agent.next_tx_count
            nonce_data[agent.address]["next_tx_count"] += 1
            agent.next_tx_count = nonce_data[agent.address]["next_tx_count"]
    else:
        nonce_data[agent.address]["next_tx_count"] = agent.next_tx_count
        nonce_data[agent.address]["next_tx_count"] += 1
        agent.next_tx_count = nonce_data[agent.address]["next_tx_count"]

    # ENCODE START
    nonce_data[agent.address]["seen_block"] = base64.b64encode(encode_single('uint256', nonce_data[agent.address]["seen_block"])).decode('ascii')
    nonce_data[agent.address]["next_tx_count"] = base64.b64encode(encode_single('uint256', nonce_data[agent.address]["next_tx_count"])).decode('ascii')
    
    # ENCODE END
    return agent.next_tx_count

def unlock_nonce(agent):
    global mm
    # DECODE START
    if not mm:
        mm = mmap.mmap(avax_cchain_nonces.fileno(), 0)

    mm.seek(0)
    raw_data_cov = mm.read().decode('utf8')
    nonce_data = json.loads(raw_data_cov)

    nonce_data['locked'] = '0'
    out_data = bytes(json.dumps(nonce_data), 'utf8')
    mm[:] = out_data

def transaction_helper(agent, prepped_function_call, gas):
    tx_hash = None
    nonce = get_nonce(agent)
    while tx_hash is None:
        try:
            agent.next_tx_count = nonce
            lock_nonce(agent)
            tx_hash = prepped_function_call.transact({
                'chainId': 43112,
                'nonce': nonce,
                'from' : getattr(agent, 'address', agent),
                'gas': gas,
                'gasPrice': Web3.toWei(225, 'gwei'),
            })
            unlock_nonce(agent)
        except Exception as inst:
            err_str = str(inst)
            if 'nonce too low' in err_str:
                # increment tx_hash
                unlock_nonce(agent)
                nonce +=1
            elif 'replacement transaction underpriced' in err_str:
                # increment tx_hash
                unlock_nonce(agent)
                nonce +=1
            else:
                print(inst)
    return tx_hash

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

def defaultdict_from_dict(d):
    #nd = lambda: collections.defaultdict(nd)
    ni = collections.defaultdict(set)
    ni.update(d)
    return ni

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
        self.__approved_file = "{}-{}.json".format(str(contract.address), 'approvals')

        if not os.path.exists(self.__approved_file):
            f = open(self.__approved_file, 'w+')
            f.write('{}')
            f.close()
            tmp_file_data = {}
        else:
            data = open(self.__approved_file, 'r+').read()
            tmp_file_data = {} if len(data) == 0 else json.loads(data)
        self.__approved = tmp_file_data
        
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
            self.__balances[address] = Balance(self.__contract.caller({'from' : address, 'gas': 100000}).balanceOf(address), self.__decimals)

        if is_init_agents:
            for agent in is_init_agents:
                # TODO: can we get a return value and a correct-as-of block in the same call?
                self.__balances[agent.address] = Balance(self.__contract.caller({'from' : agent.address, 'gas': 100000}).balanceOf(agent.address), self.__decimals)

            
    def __getitem__(self, address):
        """
        Get the balance of the given address as a Balance, with the given number of decimals.
        
        Address can be a string or any object with an .address field.
        """
        
        address = getattr(address, 'address', address)
        
        if address not in self.__balances:
            # Don't actually cache here; wait for a transfer.
            # Transactions may still be in flight
            return Balance(self.__contract.caller({'from' : address, 'gas': 100000}).balanceOf(address), self.__decimals)
        else:
            # Clone the stored balance so it doesn't get modified and upset the user
            return self.__balances[address].clone()
            
    def ensure_approved(self, owner, spender):
        """
        Approve the given spender to spend all the owner's tokens on their behalf.
        
        Owner and spender may be addresses or things with addresses.
        """
        spender = getattr(spender, 'address', spender)
        
        if (getattr(owner, 'address', owner) not in self.__approved) or (spender not in self.__approved[getattr(owner, 'address', owner)]):
            # Issue an approval
            #logger.info('WAITING FOR APPROVAL {} for {}'.format(getattr(owner, 'address', owner), spender))
            tx_hash = transaction_helper(
                owner,
                self.__contract.functions.approve(spender, UINT256_MAX), 
                500000
            )
            providerAvax.make_request("avax.issueBlock", {})
            receipt = w3.eth.waitForTransactionReceipt(tx_hash, poll_latency=tx_pool_latency)
            #logger.info('APPROVED')
            if getattr(owner, 'address', owner) not in self.__approved:
                self.__approved[getattr(owner, 'address', owner)] = {spender: 1}
            else:
                self.__approved[getattr(owner, 'address', owner)][spender] = 1

            open(self.__approved_file, 'w+').write(json.dumps(self.__approved))
            
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
    
    def __init__(self, dao, pangolin_pair, xsd_token, usdt_token, **kwargs):
 
        # xSD TokenProxy
        self.xsd_token = xsd_token
        # USDT TokenProxy 
        self.usdt_token = usdt_token
        # xSDS (Dao share) balance
        self.xsds = Balance(0, xSDS["decimals"])
        # avax balance
        self.avax = kwargs.get("starting_avax", Balance(0, 18))
        
        # Coupon underlying part by expiration epoch
        self.underlying_coupons = collections.defaultdict(float)
        # Coupon premium part by expiration epoch
        self.premium_coupons = collections.defaultdict(float)
        
        # What's our max faith in the system in USDT?
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

        # Pangolin Pair TokenProxy
        self.pangolin_pair_token = pangolin_pair

        # keeps track of latest block seen for nonce tracking/tx
        self.seen_block = {}
        self.next_tx_count = w3.eth.getTransactionCount(self.address, block_identifier=int(w3.eth.get_block('latest')["number"]))
        self.current_block = 0

        if True:#kwargs.get("is_mint", False):
            # need to mint USDT to the wallets for each agent
            start_usdt_formatted = kwargs.get("starting_usdt", Balance(0, USDT["decimals"]))
            providerAvax.make_request("avax.issueBlock", {})
            tx_hash = transaction_helper(
                self,
                self.usdt_token.contract.functions.mint(
                    self.address, start_usdt_formatted.to_wei()
                ), 
                500000
            )
            time.sleep(1.1)
            providerAvax.make_request("avax.issueBlock", {})
            w3.eth.waitForTransactionReceipt(tx_hash, poll_latency=tx_pool_latency)
        
    @property
    def xsd(self):
        """
        Get the current balance in USDT from the TokenProxy.
        """
        return self.xsd_token[self]
    
    @property
    def usdt(self):
        """
        Get the current balance in USDT from the TokenProxy.
        """
        return self.usdt_token[self]

    @property
    def lp(self):
        """
        Get the current balance in Pangolin LP Shares from the TokenProxy.
        """
        return self.pangolin_pair_token[self]

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
        return "Agent(xSD={:.2f}, usdt={:.2f}, avax={}, lp={}, coupons={:.2f})".format(
            self.xsd, self.usdt, self.avax, self.lp, self.coupons)

        
    def get_strategy(self, current_timestamp, price, total_supply, total_coupons, agent_coupons):
        """
        Get weights, as a dict from action to float, as a function of the price.
        """
        
        strategy = collections.defaultdict(lambda: 1.0)
        
        # TODO: real (learned? adversarial? GA?) model of the agents
        # TODO: agent preferences/utility function

        # People are fast to coupon bid to get in front of redemption queue
        strategy["coupon_bid"] = 2.0


        strategy["provide_liquidity"] = 0.1
        
        
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

            # less incentive to remove liquidity above 1
            strategy["remove_liquidity"] = 0.1
        else:
            # We probably want to unbond due to no returns
            strategy["unbond"] = 0
            # And not bond
            strategy["bond"] = 0

            # likely to remove liquidity below peg to reduce IL?
            strategy["remove_liquidity"] = 4.0 if agent_coupons > 0 else 1.0
       
        if self.use_faith:
            # Vary our strategy based on how much xSD we think ought to exist
            if price * total_supply > self.get_faith(current_timestamp, price, total_supply):
                # There is too much xSD, so we want to sell
                strategy["sell"] = 2.0
            else:
                # no faith based buying, just selling
                pass
        
        return strategy
        
    def get_faith(self, current_timestamp, price, total_supply):
        """
        Get the total faith in xSD that this agent has, in USDT.
        
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
        faith = center_faith + swing_faith * math.sin(current_timestamp * (2 * math.pi / 5000000))
        
        return faith
        
class PangolinPool:
    """
    Represents the Pangolin pool. Tracks xSD and USDT balances of pool, and total outstanding LP shares.
    """
    
    def __init__(self, pangolin, pangolin_router, pangolin_token, usdt_token, xsd_token, **kwargs):
        self.pangolin_pair_token = pangolin
        self.pangolin_router = pangolin_router
        self.pangolin_token = pangolin_token
        self.usdt_token = usdt_token
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
        exchange = self.pangolin_pair_token.contract
        return exchange.functions.token0().call()

    def getReserves(self):
        exchange = self.pangolin_pair_token.contract
        return exchange.functions.getReserves().call()

    def getTokenBalance(self):
        reserve, token0 = self.getReserves(), self.getToken0()
        token0Balance = reserve[0]
        token1Balance = reserve[1]
        if (token0.lower() == USDT["addr"].lower()):
            return reg_int(token0Balance, USDT['decimals']), reg_int(token1Balance, xSD['decimals'])
        return reg_int(token1Balance, USDT['decimals']), reg_int(token0Balance, xSD['decimals'])

    def getInstantaneousPrice(self):
      reserve, token0 = self.getReserves(), self.getToken0()
      token0Balance = reserve[0]
      token1Balance = reserve[1]
      if (token0.lower() == USDT["addr"].lower()):
        return int(token0Balance) * pow(10, PGLRouter['decimals']) / float(int(token1Balance)) if int(token1Balance) != 0 else 0
      return int(token1Balance) * pow(10, PGLRouter['decimals']) / float(int(token0Balance)) if int(token0Balance) != 0 else 0
    
    def xsd_price(self):
        """
        Get the current xSD price in USDT.
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

    def total_lp(self, agent):
        return reg_int(self.pangolin_pair_token.contract.caller({'from' : agent.address, 'gas': 100000}).totalSupply(), PGLRouter['decimals'])
        
    def provide_liquidity(self, agent, xsd, usdt, current_timestamp):
        """
        Provide liquidity.
        """        
        
        self.usdt_token.ensure_approved(agent, PGLRouter["addr"])
        self.xsd_token.ensure_approved(agent, PGLRouter["addr"])
        
        slippage = 0.01
        min_xsd_amount = (xsd * (1 - slippage))
        min_usdt_amount = (usdt * (1 - slippage))

        if IS_DEBUG:
            # Make sure we can afford this
            xsd_wei = self.xsd_token[agent].to_wei()
            usdt_wei = self.usdt_token[agent].to_wei()

            assert xsd_wei >= xsd.to_wei()
            assert usdt_wei >= usdt.to_wei()

        tx_hash = transaction_helper(
            agent,
            self.pangolin_router.functions.addLiquidity(
                self.xsd_token.address,
                self.usdt_token.address,
                xsd.to_wei(),
                usdt.to_wei(),
                min_xsd_amount.to_wei(),
                min_usdt_amount.to_wei(),
                agent.address,
                (int(current_timestamp) + DEADLINE_FROM_NOW)
            ), 
            500000
        )

        return tx_hash
        
    def remove_liquidity(self, agent, shares, min_xsd_amount, min_usdt_amount, current_timestamp):
        """
        Remove liquidity for the given number of shares.

        """
        self.pangolin_pair_token.ensure_approved(agent, PGLRouter["addr"])

        slippage = 0.01
        min_xsd_amount = (min_xsd_amount * (1 - slippage))
        min_usdt_amount = (min_usdt_amount * (1 - slippage))

        tx_hash = transaction_helper(
            agent,
            self.pangolin_router.functions.removeLiquidity(
                self.xsd_token.address,
                self.usdt_token.address,
                shares.to_wei(),
                min_xsd_amount.to_wei(),
                min_usdt_amount.to_wei(),
                agent.address,
                int(current_timestamp + DEADLINE_FROM_NOW)   
            ), 
            500000
        )

        return tx_hash
        
    def buy(self, agent, usdt, max_usdt_amount, current_timestamp):
        """
        Spend the given number of USDT to buy xSD.
        ['swapTokensForExactTokens(uint256,uint256,address[],address,uint256)']
        """  
        
        self.usdt_token.ensure_approved(agent, PGLRouter["addr"])
        self.xsd_token.ensure_approved(agent, PGLRouter["addr"])

        # explore this more?
        slippage = 0.01
        max_usdt_amount = (max_usdt_amount * (1 + slippage))

        tx_hash = transaction_helper(
            agent,
            self.pangolin_router.functions.swapExactTokensForTokens(
                usdt.to_wei(),
                max_usdt_amount.to_wei(),
                [self.usdt_token.address, self.xsd_token.address],
                agent.address,
                int(current_timestamp + DEADLINE_FROM_NOW)
            ), 
            500000
        )
        return tx_hash
        
    def sell(self, agent, xsd, min_usdt_amount, advancer, pangolin_usdt_supply, current_timestamp):
        """
        Sell the given number of xSD for USDT.
        """

        self.usdt_token.ensure_approved(agent, PGLRouter["addr"])
        self.xsd_token.ensure_approved(agent, PGLRouter["addr"])

        # explore this more?
        slippage = 0.99 if (advancer.address == agent.address) or ((agent.redeem_count > 0) and agent.xsd > pangolin_usdt_supply) else 0.01
        min_usdt_amount = (min_usdt_amount * (1 - slippage))

        tx_hash = transaction_helper(
            agent,
            self.pangolin_router.functions.swapExactTokensForTokens(
                xsd.to_wei(),
                min_usdt_amount.to_wei(),
                [self.xsd_token.address, self.usdt_token.address],
                agent.address,
                int(current_timestamp + DEADLINE_FROM_NOW)
            ), 
            500000
        )
        return tx_hash

    def update(self, is_init_agents=[]):
        self.pangolin_pair_token.update(is_init_agents=is_init_agents)

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
        total_coupons = self.contract.caller({'from' : address, 'gas': 100000}).outstandingCoupons(epoch)
        return Balance.from_tokens(total_coupons, xSD['decimals'])
        
    def total_coupons(self, address):
        """
        Get all outstanding unexpired coupons.
        """
        
        total = self.contract.caller({'from' : address, 'gas': 100000}).totalCoupons()
        return reg_int(total, xSD['decimals'])

    def total_redeemable(self, address):
        """
        Get total reedeemable supply.
        """
        
        total = self.contract.caller({'from' : address, 'gas': 100000}).totalRedeemable()
        return reg_int(total, xSD['decimals'])


    def total_coupons_for_agent(self, agent):
        total_coupons = self.contract.caller({'from' : agent.address, 'gas': 100000}).outstandingCouponsForAddress(agent.address)
        return total_coupons

    def coupon_balance_at_epoch(self, address, epoch):
        ''' 
            returns the total coupon balance for an address
        '''
        if epoch == 0:
            return 0
        total_coupons = self.contract.caller({'from' : address, 'gas': 100000}).balanceOfCoupons(address, epoch)
        return total_coupons

    def get_coupon_expirirations(self, agent):
        '''
            Return a list of coupon expirations for an address from last time called
        '''
        epochs = []
        epoch_index_max = self.contract.caller({'from' : agent.address, 'gas': 100000}).getCouponsCurrentAssignedIndex(agent.address)

        for i in range(agent.max_coupon_epoch_index, epoch_index_max):
            t_epoch = self.contract.caller({'from' : agent.address, 'gas': 100000}).getCouponsAssignedAtEpoch(agent.address, i)
            total_coupons = self.coupon_balance_at_epoch(agent.address, t_epoch)
            if total_coupons == 0:
                continue
            else:
                epochs.append(t_epoch)

        agent.max_coupon_epoch_index = 0
        agent.coupon_expirys = epochs
        agent.coupon_expirys.sort()

        #agent.coupon_expirys = list(set(agent.coupon_expirys))
        return agent.coupon_expirys

    def epoch(self, address):
        return self.contract.caller({'from' : address, 'gas': 100000}).epoch()
        
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
        tx_hash = transaction_helper(
            agent,
            self.contract.functions.placeCouponAuctionBid(
                coupon_expiry,
                xsd_amount.to_wei(),
                max_coupon_amount.to_wei()
            ), 
            4000000
        )
        return tx_hash
        
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

        tx_hash = transaction_helper(
            agent,
            self.contract.functions.redeemCoupons(
                epoch_expired,
                total_coupons
            ), 
            8000000
        )
        return tx_hash


    def advance(self, agent):
        """
        Advance the epoch. Return the balance of XSD created.
        
        Note that if advance() does any kind of auction settlement or other
        operations, the reported reward may be affected by those transfers.
        """
        tx_hash = transaction_helper(
            agent,
            self.contract.functions.advance(), 
            8000000
        )
        providerAvax.make_request("avax.issueBlock", {})
        return tx_hash
                        
class Model:
    """
    Full model of the economy.
    """
    
    def __init__(self, dao, pangolin, usdt, pangolin_router, pangolin_token, xsd, oracle, agents, **kwargs):
        """
        Takes in experiment parameters and forwards them on to all components.
        """
        self.pangolin = PangolinPool(pangolin, pangolin_router, pangolin_token, usdt, xsd, **kwargs)
        self.dao = DAO(dao, xsd, **kwargs)
        self.oracle = oracle
        self.agents = []
        self.usdt_token = usdt
        self.pangolin_router = pangolin_router
        self.xsd_token = xsd
        self.max_avax = Balance.from_tokens(1000000, 18)
        self.max_usdt = self.usdt_token.from_tokens(100000000)
        self.bootstrap_epoch = 2
        self.max_coupon_exp = 131400
        self.max_coupon_premium = 10.0
        self.min_usdt_balance = self.usdt_token.from_tokens(1)
        self.agent_coupons = {x: 0 for x in agents}
        self.has_prev_advanced = True


        is_mint = is_try_model_mine
        if w3.eth.get_block('latest')["number"] == block_offset:
            # THIS ONLY NEEDS TO BE RUN ON NEW CONTRACTS
            # TODO: tolerate redeployment or time-based generation
            is_mint = True
        
        total_tx_submitted = len(agents) 
        for i in range(len(agents)):
            start_avax = random.random() * self.max_avax
            start_usdt = random.random() * self.max_usdt
            
            address = agents[i]
            agent = Agent(self.dao, pangolin, xsd, usdt, starting_axax=start_avax, starting_usdt=start_usdt, wallet_address=address, is_mint=is_mint, **kwargs)
             
            self.agents.append(agent)

        # Update caches to current chain state
        self.usdt_token.update(is_init_agents=self.agents)
        self.xsd_token.update(is_init_agents=self.agents)
        self.pangolin.update(is_init_agents=self.agents)

        for i in range(len(agents)):
            if not is_mint:
                self.agent_coupons[self.agents[i].address] = self.agents[i].coupons
                self.dao.get_coupon_expirirations(self.agents[i])
            logger.info(self.agents[i])

        sys.exit()
        
    def log(self, stream, seleted_advancer, current_timestamp, header=False):
        """
        Log model statistics a TSV line.
        If header is True, include a header.
        """
        
        if header:
            stream.write("#block\tepoch\tprice\tsupply\tcoupons\ttotal_redeemable\tlp_supply\tfaith\n")

        (usdt_b, xsd_b) = self.pangolin.getTokenBalance()
        xsd_supply = self.dao.xsd_supply()
        
        stream.write('{}\t{}\t{:.2f}\t{:.2f}\t{:.2f}\t{:.2f}\t{:.2f}\t{:.2f}\n'.format(
                w3.eth.get_block('latest')["number"],
                self.dao.epoch(seleted_advancer.address),
                self.pangolin.xsd_price(),
                xsd_supply,
                self.dao.total_coupons(seleted_advancer.address),
                self.dao.total_redeemable(seleted_advancer.address),
                float(xsd_b) / float(xsd_supply) * 100 if xsd_supply > 0 else 0.0,
                self.get_overall_faith(current_timestamp)
            )
        )
       
    def get_overall_faith(self, current_timestamp):
        """
        What target should the system be trying to hit in xSD market cap?
        """
        return self.agents[0].get_faith(current_timestamp, self.pangolin.xsd_price(), self.dao.xsd_supply())
       
    def step(self):
        """
        Step the model Let all the agents act.
        
        Returns True if anyone could act.
        """
        # Update caches to current chain state
        self.usdt_token.update()
        self.xsd_token.update()
        self.pangolin.update()

        #randomly have an agent advance the epoch
        seleted_advancer = self.agents[int(random.random() * (len(self.agents) - 1))]

        if self.has_prev_advanced:
            provider.make_request("debug_increaseTime", [7200])


        current_block = w3.eth.get_block('latest')
        current_timestamp = current_block['timestamp']
        logger.info("Clock: {}".format(current_timestamp))
        ts = time.time()
        epoch_before = self.dao.epoch(seleted_advancer.address)
        incentivized_adv_tx = self.dao.advance(seleted_advancer)
        adv_recp = w3.eth.waitForTransactionReceipt(incentivized_adv_tx, poll_latency=tx_pool_latency)
        is_advance_fail = False

        te = time.time()
        logger.info("Diff Advance Real Time: {}".format(te - ts))
        if adv_recp["status"] == 0:
            is_advance_fail = True
            self.has_prev_advanced = False
        else:
            self.has_prev_advanced = True

        logger.info("Earliest Active Auction: {}".format(self.dao.contract.caller({'from' : seleted_advancer.address, 'gas': 100000}).getEarliestActiveAuctionEpoch()))
        logger.info("Prospective Advance from {}, is_advance_fail: {}".format(seleted_advancer.address, is_advance_fail))

        (usdt_b, xsd_b) = self.pangolin.getTokenBalance()
        revs = self.pangolin.getReserves()

        current_epoch = self.dao.epoch(seleted_advancer.address)

        epoch_start_price = self.pangolin.xsd_price()
        dao_xsd_supply = self.dao.xsd_supply()
        total_coupons = self.dao.total_coupons(seleted_advancer.address)
        
        logger.info("Block {}, epoch {}, price {:.2f}, supply {:.2f}, faith: {:.2f}, bonded {:2.1f}%, coupons: {:.2f}, liquidity {:.2f} xSD / {:.2f} USDT".format(
            current_block["number"], current_epoch, epoch_start_price, dao_xsd_supply,
            self.get_overall_faith(current_timestamp), 0, total_coupons,
            xsd_b, usdt_b)
        )
        
        latest_price = Balance(self.oracle.caller({'from' : seleted_advancer.address, 'gas': 100000}).latestPrice()[0], xSD['decimals'])
        latest_valid = self.oracle.caller({'from' : seleted_advancer.address, 'gas': 100000}).latestValid()
        tr = self.dao.total_redeemable(seleted_advancer.address)
        logger.info("latest_price: {}, latest_valid: {}, totalRedeemable: {}".format(latest_price, latest_valid, tr))
        
        anyone_acted = False
        if current_epoch < self.bootstrap_epoch:
            anyone_acted = True
            return anyone_acted, seleted_advancer


        total_tx_submitted = 0
        total_redeem_submitted = 0
        total_coupoun_bidders = 0
        random.shuffle(self.agents)

        tx_hashes = []

        is_pgl_op = self.pangolin.operational()

        # try to redeem any outstanding coupons here first to better
        if tr > 0 and total_coupons > 0:
            for agent_num, a in enumerate(self.agents):
                tr = self.dao.contract.caller({'from' : a.address, 'gas': 100000}).totalRedeemable()
                if tr == 0:
                    break
                
                if self.agent_coupons[a.address] > 0 and tr >= self.agent_coupons[a.address]:
                    self.dao.get_coupon_expirirations(a)
                    if len(a.coupon_expirys) == 0:
                        #logger.info("ERROR WITH EXIPRIATION LIST")
                        continue
                    else:
                        # if agent has coupons                    
                        logger.info("COUPON EXP: Agent {}, exp_epochs: {}".format(a.address, json.dumps(a.coupon_expirys)))

                        a.redeem_count += 1
                        tried_idx = []
                        for c_idx, c_exp in enumerate(a.coupon_expirys):
                            try:
                                redeem_tx_hash = self.dao.redeem(a, c_exp)
                                total_redeem_submitted += 1
                                providerAvax.make_request("avax.issueBlock", {})
                                tx_hashes.append({'type': 'redeem', 'hash': redeem_tx_hash})
                            except Exception as inst:
                                logger.info({"agent": a.address, "error": inst, "action": "redeem", "exact_expiry": c_exp})

        for agent_num, a in enumerate(self.agents):            
            # TODO: real strategy
            options = []

            start_tx_count = a.next_tx_count
            commitment = random.random() * 0.1

            if portion_dedusted(a.usdt, commitment) > 0 and is_pgl_op:
                options.append("buy")
            if portion_dedusted(a.xsd, commitment) > 0 and is_pgl_op:
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
            if usdt_b >= self.min_usdt_balance and portion_dedusted(a.xsd, commitment) >= Balance.from_tokens(1, xSD['decimals']) and self.dao.has_coupon_bid():
                options.append("coupon_bid")
            if portion_dedusted(a.usdt, commitment) > 0 and portion_dedusted(a.xsd, commitment) > 0:
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
        
                strategy = a.get_strategy(current_timestamp, self.pangolin.xsd_price(), dao_xsd_supply, total_coupons, self.agent_coupons[a.address])
                
                weights = [strategy[o] for o in options]
                
                action = random.choices(options, weights=weights)[0]
                
                # What fraction of the total possible amount of doing this
                # action will the agent do?
                
                if action == "buy":
                    # this will limit the size of orders avaialble
                    (usdt_b, xsd_b) = self.pangolin.getTokenBalance()
                    if xsd_b > 0 and usdt_b > 0:
                        usdt_in = portion_dedusted(
                            min(a.usdt, xsd_b.to_decimals(USDT['decimals'])),
                            commitment
                        )
                    else:
                        continue

                    try:
                        (max_amount, _) = self.pangolin_router.caller({'from' : a.address, 'gas': 100000}).getAmountsIn(
                            usdt_in.to_wei(), 
                            [self.usdt_token.address, self.xsd_token.address]
                        )

                        if max_amount == 1:
                            normed_max_out =  (usdt_in * epoch_start_price)
                            max_amount = normed_max_out.to_decimals(xSD['decimals'])

                    except Exception as inst:
                        # not enough on market to fill bid
                        logger.info({"agent": a.address, "error": inst, "action": "buy", "amount_in": usdt_in})
                        continue
                    
                    try:
                        price = epoch_start_price
                        #logger.info("Buy init {:.2f} xSD @ {:.2f} for {:.2f} USDT".format(usdt_in, price, max_amount))
                        buy_tx = self.pangolin.buy(a, usdt_in, max_amount, current_timestamp)
                        tx_hashes.append({'type': 'buy', 'hash': buy_tx})
                        #logger.debug("Buy end {:.2f} xSD @ {:.2f} for {:.2f} USDT".format(max_amount, price, usdt_in))
                        
                    except Exception as inst:
                        logger.info({"agent": a.address, "error": inst, "action": "buy", "usdt_in": usdt_in, "max_amount": max_amount})
                        continue
                elif action == "sell":
                    # this will limit the size of orders avaialble
                    (usdt_b, xsd_b) = self.pangolin.getTokenBalance()
                    if xsd_b > 0 and usdt_b > 0:
                        xsd_out = min(
                            portion_dedusted(
                                a.xsd,
                                commitment
                            ),
                            usdt_b.to_decimals(xSD['decimals'])
                        )
                    else:
                        continue
                    
                    try:
                        (_, max_amount) = self.pangolin_router.caller({'from' : a.address, 'gas': 100000}).getAmountsOut(
                            xsd_out.to_wei(), 
                            [self.xsd_token.address, self.usdt_token.address]
                        )

                        max_amount = reg_int(max_amount, USDT['decimals'])
                    except Exception as inst:
                        logger.info({"agent": a.address, "error": inst, "action": "sell", "amount_out": xsd_out})

                    try:
                        price = epoch_start_price
                        #logger.info("Sell init {:.2f} xSD @ {:.2f} for {:.2f} USDT".format(xsd_out, price, max_amount))
                        sell_tx = self.pangolin.sell(a, xsd_out, max_amount, seleted_advancer, usdt_b.to_decimals(xSD['decimals']), current_timestamp)
                        tx_hashes.append({'type': 'sell', 'hash': sell_tx})
                        #logger.debug("Sell end {:.2f} xSD @ {:.2f} for {:.2f} USDT".format(xsd_out, price, usdt))
                    except Exception as inst:
                        logger.info({"agent": a.address, "error": inst, "action": "sell", "xsd_out": xsd_out, "max_amount": max_amount, "account_xsd": a.xsd})
                elif action == "coupon_bid":
                    '''
                        TODO: NEED TO FIGURE OUT BETTER WAY TO TRACK THIS?
                    '''
                    xsd_at_risk = max(Balance.from_tokens(1, 18), portion_dedusted(a.xsd, commitment))
                    rand_epoch_expiry = int(random.random() * self.max_coupon_exp)
                    rand_max_coupons =  round(max(1.01, min(random.random() * self.max_coupon_premium, self.max_coupon_premium)) * xsd_at_risk)

                    #rand_max_coupons =  round(max(1.01, min(random.random() + 1.0, self.max_coupon_premium)) * xsd_at_risk)
                    #rand_max_coupons =  round(max(1.01, int(math.floor(self.max_coupon_premium))) * xsd_at_risk)


                    if rand_max_coupons < xsd_at_risk:
                        xsd_at_risk = rand_max_coupons
                    try:
                        exact_expiry = rand_epoch_expiry + current_epoch
                        #logger.info("Addr {} Bid to burn init {:.2f} xSD for {:.2f} coupons with expiry at epoch {}".format(a.address, xsd_at_risk, rand_max_coupons, exact_expiry))
                        coupon_bid_tx_hash = self.dao.coupon_bid(a, rand_epoch_expiry, xsd_at_risk, rand_max_coupons)
                
                        #if (latest_valid == True):
                        if (self.has_prev_advanced == False):
                            providerAvax.make_request("avax.issueBlock", {})
                            coup_adv_recp = w3.eth.waitForTransactionReceipt(coupon_bid_tx_hash, poll_latency=tx_pool_latency)
                            is_advance_fail = False
                            if coup_adv_recp["status"] == 0:
                                is_advance_fail = True
                                self.has_prev_advanced = False
                            else:
                                latest_price = Balance(self.oracle.caller({'from' : a.address, 'gas': 100000}).latestPrice()[0], xSD['decimals'])
                                self.has_prev_advanced = True
                            
                            logger.info("Coupon Advance from {}, is_advance_fail: {}".format(a.address, is_advance_fail))

                        
                        tx_hashes.append({'type': 'coupon_bid', 'hash': coupon_bid_tx_hash})
                        self.agent_coupons[a.address] = a.coupons
                        #logger.info("Addr {} Bid to burn end {:.2f} xSD for {:.2f} coupons with expiry at epoch {}".format(a.address, xsd_at_risk, rand_max_coupons, exact_expiry))
                        total_coupoun_bidders += 1
                    except Exception as inst:
                        logger.info({"agent": a.address, "error": inst, "action": "coupon_bid", "exact_expiry": exact_expiry, "xsd_at_risk": xsd_at_risk})
                elif action == "provide_liquidity":
                    min_xsd_needed = Balance(0, xSD['decimals'])
                    usdt = Balance(0, USDT['decimals'])
                    if float(a.xsd) < float(a.usdt):
                        usdt = portion_dedusted(a.xsd.to_decimals(USDT['decimals']), commitment)
                    else:
                        usdt = portion_dedusted(a.usdt, commitment)
                    
                    try: 
                        if revs[1] > 0:
                            min_xsd_needed = reg_int(
                                self.pangolin_router.caller(
                                    {'from' : a.address, 'gas': 100000}
                                ).quote(
                                    usdt.to_wei(), revs[0], revs[1]
                                ),
                                xSD['decimals']
                            )
                            if min_xsd_needed == 0:
                                price = epoch_start_price
                                min_xsd_needed = (usdt / float(price)).to_decimals(xSD['decimals'])
                        else:
                            min_xsd_needed = usdt.to_decimals(xSD['decimals'])
                            
                        if min_xsd_needed == 0:
                            continue
                    
                        #logger.info("Provide {:.2f} xSD (of {:.2f} xSD) and {:.2f} USDT".format(min_xsd_needed, a.xsd, usdt))
                        plp_hash = self.pangolin.provide_liquidity(a, min_xsd_needed, usdt, current_timestamp)
                        tx_hashes.append({'type': 'provide_liquidity', 'hash': plp_hash})
                    except Exception as inst:
                        # SLENCE TRANSFER_FROM_FAILED ISSUES
                        #logger.info({"agent": a.address, "error": inst, "action": "provide_liquidity", "min_xsd_needed": min_xsd_needed, "usdt": usdt})
                        continue
                elif action == "remove_liquidity":
                    (usdt_b, xsd_b) = self.pangolin.getTokenBalance()
                    lp = portion_dedusted(a.lp, commitment)
                    total_lp = self.pangolin.total_lp(a)
                    min_xsd_amount = max(Balance(0, xSD['decimals']), Balance(float(xsd_b) * float(lp / float(total_lp)), xSD['decimals']))
                    min_usdt_amount = max(Balance(0, USDT['decimals']), Balance(float(usdt_b) * float(lp / float(total_lp)), USDT['decimals']))

                    if not (min_xsd_amount > 0 and min_usdt_amount > 0):
                        continue

                    try:
                        #logger.info("Stop providing {:.2f} xSD and {:.2f} USDT".format(min_xsd_amount, min_usdt_amount))
                        rlp_hash = self.pangolin.remove_liquidity(a, lp, min_xsd_amount, min_usdt_amount, current_timestamp)
                        tx_hashes.append({'type': 'remove_liquidity', 'hash': rlp_hash})
                    except Exception as inst:
                        logger.info({"agent": a.address, "error": inst, "action": "remove_liquidity", "min_xsd_needed": min_xsd_amount, "usdt": min_usdt_amount})
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
            logger.info("{} sumbitted, mining blocks for them now, {} coupon bidders".format(
                total_tx_submitted, total_coupoun_bidders)
            )
        else:
            logger.info("{} coupon bidders".format(
                total_coupoun_bidders)
            )

        providerAvax.make_request("avax.issueBlock", {})
        tx_hashes_good = 0
        tx_fails = []
        #'''
        for tmp_tx_hash in tx_hashes:
            receipt = w3.eth.waitForTransactionReceipt(tmp_tx_hash['hash'], poll_latency=tx_pool_latency)
            tx_hashes_good += receipt["status"]
            if receipt["status"] == 0:
                tx_fails.append(tmp_tx_hash['type'])
        #'''

        logger.info("total tx: {}, successful tx: {}, tx fails: {}".format(
                len(tx_hashes), tx_hashes_good, json.dumps(tx_fails)
            )
        )

        return anyone_acted, seleted_advancer

def main():
    """
    Main function: run the simulation.
    """
    global avax_cchain_nonces
    logging.basicConfig(level=logging.INFO)


    if w3.eth.get_block('latest')["number"] == block_offset:
        logger.info("Start Clock: {}".format(w3.eth.get_block('latest')['timestamp']))

    logger.info(w3.eth.get_block('latest')["number"])
    logger.info('Root Addr: {}'.format(xSDS['addr']))

    logger.info('Total Agents: {}'.format(len(w3.eth.accounts[:max_accounts])))
    dao = w3.eth.contract(abi=DaoContract['abi'], address=xSDS["addr"])
    logger.info('Dao is at: {}'.format(dao.address))

    '''
    for i in range(0, 1000):
        logger.info(dao.functions.getTotalFilled(i).call())
    sys.exit()
    '''

    #'''
    AGENT_NONCES['locked'] = '0'
    for acc in w3.eth.accounts[:max_accounts]:

        AGENT_NONCES[acc] = {
            "next_tx_count": base64.b64encode(encode_single('uint256', 0)).decode('ascii'),
            "seen_block": base64.b64encode(encode_single('uint256', 0)).decode('ascii')
        }

        max_index = dao.caller({'from' : acc, 'gas': 100000}).getCouponsCurrentAssignedIndex(acc)
        logger.info("how many times assigned coupons for {}: {}".format(acc, max_index))
        '''
        for i in range(0, max_index):
            t_epoch = dao.caller({'from' : acc, 'gas': 100000}).getCouponsAssignedAtEpoch(acc, i)
            logger.info("\tepochs: {}".format(t_epoch))
        '''

    '''
        LOAD NONCES INTO MMAP
    '''
    mmap_data = json.dumps(AGENT_NONCES)
    with open(MMAP_FILE, "wb") as f:
        f.write(bytes(mmap_data, 'utf8'))

    avax_cchain_nonces = open(MMAP_FILE, "r+b")

    '''
    avg_auction_yields = []
    for epoch in range(0, dao.caller().epoch()):
        yields = dao.caller().getAvgYieldFilled(epoch)
        tmp_yield = yields[0] / 10. ** xSD["decimals"]
        if (tmp_yield > 0):
            avg_auction_yields.append(tmp_yield)
            logger.info(
                "epoch: {}, avg yeild: {}".format(
                    epoch, tmp_yield
                )
            )

    avg_a_y = sum(avg_auction_yields) / float(len(avg_auction_yields))
    logger.info("avg yield cross auctions: {}".format(avg_a_y))
    sys.exit()
    '''
    
    '''

    #logger.info("getTotalFilled at epoch 4: {}".format(dao.caller().getTotalFilled(10)))
    earlies_active_epoch = dao.caller().getEarliestActiveAuctionEpoch()
    baddr = dao.caller().getBestBidderFromEarliestActiveAuctionEpoch(earlies_active_epoch)
    logger.info("getBestBidderFromEarliestActiveAuctionEpoch at epoch {}: {}".format(earlies_active_epoch, baddr))
    exp = dao.caller().getCouponsAssignedAtEpoch(baddr, 0)

    total_coupons = dao.caller().balanceOfCoupons(baddr, exp) / 10.**xSD["decimals"]
    logger.info("total_coupons at exp epoch {}: {}".format(exp, total_coupons))

    total_best_coupons = dao.caller().getSumofBestBidsAcrossCouponAuctions() / 10.**xSD["decimals"]
    logger.info("total_best_coupons: {}".format(total_best_coupons))
    tr = dao.caller().totalRedeemable() / 10.**xSD["decimals"]
    logger.info("totalRedeemable: {}".format(tr))
    sys.exit()
    dao.functions.redeemCoupons(
        exp,
        dao.caller().balanceOfCoupons(baddr, exp)
    ).transact({
        'nonce': w3.eth.getTransactionCount(baddr, block_identifier=int(w3.eth.get_block('latest')["number"])),
        'from' : baddr,
        'gas': 8000000
    })
    sys.exit()
    '''

    #print(dao.caller().oracle())
    oracle = w3.eth.contract(abi=OracleContract['abi'], address=dao.caller().oracle())
    logger.info("Oracle is at: {}".format(oracle.address))

    pangolin = TokenProxy(w3.eth.contract(abi=PangolinPairContract['abi'], address=PGL["addr"]))
    usdt = TokenProxy(w3.eth.contract(abi=USDTContract['abi'], address=USDT["addr"]))
    
    pangolin_router = w3.eth.contract(abi=PangolinRouterAbiContract['abi'], address=PGLRouter["addr"])
    pangolin_token = w3.eth.contract(abi=PoolContract['abi'], address=PGLLP["addr"])

    xsd = TokenProxy(w3.eth.contract(abi=DollarContract['abi'], address=dao.caller().dollar()))
    logger.info(dao.caller().dollar())

    # Make a model of the economy
    start_init = time.time()
    logger.info('INIT STARTED')
    model = Model(dao, pangolin, usdt, pangolin_router, pangolin_token, xsd, oracle, w3.eth.accounts[:max_accounts], min_faith=0.5E6, max_faith=1E6, use_faith=True)
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
        current_timestamp = w3.eth.get_block('latest')['timestamp']
        model.log(stream, seleted_advancer, current_timestamp, header=(i == 0))
        
if __name__ == "__main__":
    main()
