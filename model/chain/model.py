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

logger = logging.getLogger(__name__)
provider = Web3.WebsocketProvider('ws://localhost:7545')
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

DaoContract = json.loads(open('./build/contracts/Implementation.json', 'r+').read())
USDCContract = json.loads(open('./build/contracts/TestnetUSDC.json', 'r+').read())
DollarContract = json.loads(open('./build/contracts/IDollar.json', 'r+').read())

UniswapPairContract = json.loads(open('./build/contracts/IUniswapV2Pair.json', 'r+').read())
UniswapRouterAbiContract = json.loads(open('./node_modules/@uniswap/v2-periphery/build/IUniswapV2Router02.json', 'r+').read())
UniswapClientAbiContract = json.loads(open('./node_modules/@uniswap/v2-core/build/IUniswapV2ERC20.json', 'r+').read())
TokenContract = json.loads(open('./build/contracts/Root.json', 'r+').read())
PoolContract = json.loads(open('./build/contracts/Pool.json', 'r+').read())

def get_addr_from_contract(contract):
    return contract["networks"][str(sorted(map(int,contract["networks"].keys()))[-1])]["address"]

xSD['addr'] = get_addr_from_contract(DaoContract)
xSDS['addr'] = get_addr_from_contract(TokenContract)

def reg_int(value, scale):
    return round(value / float(int(pow(10,scale))), scale)

def unreg_int(value, scale):
    scaled = int(round(value, scale) * pow(10, scale))
    return scaled

def pretty(d, indent=0):
   for key, value in d.items():
      print('\t' * indent + str(key))
      if isinstance(value, dict):
         pretty(value, indent+1)
      elif isinstance(value, list):
        for v in value:
            pretty(v, indent+1)
      else:
         print('\t' * (indent+1) + str(value))

class Agent:
    """
    Represents an agent. Tracks all the agent's balances.
    """
    
    def __init__(self, dao, uniswap_pair, xsd_lp, usdc_lp, **kwargs):
 
        # xSD contract
        self.xsd_lp = xsd_lp
        # USDC contract 
        self.usdc_lp = usdc_lp
        # xSD balance
        self.xsd = 0.0
        # USDC balance
        self.usdc = kwargs.get("starting_usdc", 0.0)
        # xSDS (Dao share) balance
        self.xsds = 0.0
        # Eth balance
        self.eth = kwargs.get("starting_eth", 0.0)
        
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
        self.total_coupons_bid = 0

        #coupon expirys
        self.coupon_expirys = []

        self.dao = dao
        self.uniswap_pair = uniswap_pair

        # Uniswap LP share balance
        self.lp = 0
        is_seeded = True

        if is_seeded:
            self.lp = reg_int(self.uniswap_pair.caller({'from' : self.address, 'gas': 8000000}).balanceOf(self.address), UNIV2Router['decimals'])

            self.xsd = reg_int(self.xsd_lp.caller({'from' : self.address, 'gas': 8000000}).balanceOf(self.address), xSD['decimals'])

            self.usdc = reg_int(self.usdc_lp.caller({'from' : self.address, 'gas': 8000000}).balanceOf(self.address), USDC['decimals'])
        
    def __str__(self):
        """
        Turn into a readable string summary.
        """
        return "Agent(xSD={:.2f}, usdc={:.2f}, eth={}, lp={}, coupons={:.2f})".format(
            self.xsd, self.usdc, self.eth, self.lp,
            self.dao.total_coupons(self.address))
        
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
        
        if price > 1.0:
            # No rewards for expansion by itself
            strategy["bond"] = 0
            # And not unbond
            strategy["unbond"] = 0
            # Or redeem if possible
            strategy["redeem"] = 100
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
                # We prefer to buy
                strategy["buy"] = 4.0
        
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
    
    def __init__(self, uniswap, uniswap_router, uniswap_lp, usdc_lp, xsd, **kwargs):
        self.uniswap_pair = uniswap
        self.uniswap_router = uniswap_router
        self.uniswap_lp = uniswap_lp
        self.usdc_lp = usdc_lp
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
        
    def provide_liquidity(self, address, xsd, usdc):
        """
        Provide liquidity. Returns the number of new LP shares minted.
        """        
        is_usdc_approved = self.usdc_lp.caller({'from' : address, 'gas': 8000000}).allowance(address, UNIV2Router["addr"])
        if not (is_usdc_approved > 0):
            self.usdc_lp.functions.approve(UNIV2Router["addr"], UINT256_MAX).transact({
                'nonce': w3.eth.getTransactionCount(address),
                'from' : address,
                'gas': 8000000,
                'gasPrice': 1,
            })      

        is_xsd_approved = self.xsd.caller({'from' : address, 'gas': 8000000}).allowance(address, UNIV2Router["addr"])
        if not (is_xsd_approved > 0):
            self.xsd.functions.approve(UNIV2Router["addr"], UINT256_MAX).transact({
                'nonce': w3.eth.getTransactionCount(address),
                'from' : address,
                'gas': 8000000,
                'gasPrice': 1,
            })

        slippage = 0.02
        min_xsd_amount = (xsd * (1 - slippage))
        min_usdc_amount = (usdc * (1 - slippage))

        logger.debug(
            'Balanace for {}: {:.2f} xSD, {:.2f} USDC'.format(
                address,
                reg_int(self.xsd.caller({'from' : address, 'gas': 8000000}).balanceOf(address), xSD['decimals']),
                reg_int(self.usdc_lp.caller({'from' : address, 'gas': 8000000}).balanceOf(address), USDC['decimals'])
            )
        )

        rv = self.uniswap_router.functions.addLiquidity(
            self.xsd.address,
            self.usdc_lp.address,
            unreg_int(xsd, xSD['decimals']),
            unreg_int(usdc, USDC['decimals']),
            unreg_int(min_xsd_amount, xSD['decimals']),
            unreg_int(min_usdc_amount, USDC['decimals']),
            address,
            (int(w3.eth.get_block('latest')['timestamp']) + DEADLINE_FROM_NOW)
        ).transact({
            'nonce': w3.eth.getTransactionCount(address),
            'from' : address,
            'gas': 8000000,
            'gasPrice': 1,
        })

        lp_shares = reg_int(self.uniswap_pair.caller({'from' : address, 'gas': 8000000}).balanceOf(address), UNIV2Router['decimals'])
        return lp_shares
        
    def remove_liquidity(self, address, shares, min_xsd_amount, min_usdc_amount):
        """
        Remove liquidity for the given number of shares.

        """
        self.uniswap_router.functions.removeLiquidity(
            self.xsd.address,
            self.usdc_lp.address,
            unreg_int(shares, UNIV2Router['decimals']),
            unreg_int(min_xsd_amount, xSD['decimals']),
            unreg_int(min_usdc_amount, USDC['decimals']),
            address,
            int(w3.eth.get_block('latest')['timestamp'] + DEADLINE_FROM_NOW)
            
        ).transact({
            'nonce': w3.eth.getTransactionCount(address),
            'from' : address,
            'gas': 8000000,
            'gasPrice': 1,
        })

        lp_shares = reg_int(self.uniswap_pair.caller({'from' : address, 'gas': 8000000}).balanceOf(address), UNIV2Router['decimals'])
        return lp_shares
        
    def buy(self, address, usdc, max_usdc_amount):
        """
        Spend the given number of USDC to buy xSD. Returns the xSD bought.
        ['swapTokensForExactTokens(uint256,uint256,address[],address,uint256)']
        """  
        # get balance of xSD before and after
        balance_before = self.xsd.caller({"from": address, 'gas': 8000000}).balanceOf(address)


        is_usdc_approved = self.usdc_lp.caller({'from' : address, 'gas': 8000000}).allowance(UNIV2Router["addr"], address)
        if not (is_usdc_approved > 0):
            self.usdc_lp.functions.approve(UNIV2Router["addr"], UINT256_MAX).transact({
                'nonce': w3.eth.getTransactionCount(address),
                'from' : address,
                'gas': 8000000,
                'gasPrice': 1,
            })      

        is_xsd_approved = self.xsd.caller({'from' : address, 'gas': 8000000}).allowance(UNIV2Router["addr"], address)
        if not (is_xsd_approved > 0):
            self.xsd.functions.approve(UNIV2Router["addr"], UINT256_MAX).transact({
                'nonce': w3.eth.getTransactionCount(address),
                'from' : address,
                'gas': 8000000,
                'gasPrice': 1,
            })

        logger.info(
            'Balanace for {}: {:.2f} xSD, {:.2f} USDC'.format(
                address,
                reg_int(self.xsd.caller({'from' : address, 'gas': 8000000}).balanceOf(address), xSD['decimals']),
                reg_int(self.usdc_lp.caller({'from' : address, 'gas': 8000000}).balanceOf(address), USDC['decimals'])
            )
        )

        slippage = 0.02
        max_usdc_amount = (max_usdc_amount * (1 + slippage))

        self.uniswap_router.functions.swapTokensForExactTokens(
            unreg_int(usdc, USDC["decimals"]),
            unreg_int(max_usdc_amount, xSD["decimals"]),
            [self.usdc_lp.address, self.xsd.address],
            address,
            int(w3.eth.get_block('latest')['timestamp'] + DEADLINE_FROM_NOW)
        ).transact({
            'nonce': w3.eth.getTransactionCount(address),
            'from' : address,
            'gas': 8000000,
            'gasPrice': 1,
        })
        balance_after = self.xsd.caller({"from": address, 'gas': 8000000}).balanceOf(address)
        amount_bought = reg_int(balance_after - balance_before, xSD["decimals"])
        return amount_bought
        
    def sell(self, address, xsd, min_usdc_amount):
        """
        Sell the given number of xSD for USDC. Returns the xSD received.
        """
        # get balance of xsd before and after
        balance_before = self.xsd.caller({"from": address, 'gas': 8000000}).balanceOf(address)

        is_usdc_approved = self.usdc_lp.caller({'from' : address, 'gas': 8000000}).allowance(address, UNIV2Router["addr"])
        if not (is_usdc_approved > 0):
            self.usdc_lp.functions.approve(UNIV2Router["addr"], UINT256_MAX).transact({
                'nonce': w3.eth.getTransactionCount(address),
                'from' : address,
                'gas': 8000000,
                'gasPrice': 1,
            })      

        is_xsd_approved = self.xsd.caller({'from' : address, 'gas': 8000000}).allowance(address, UNIV2Router["addr"])
        if not (is_xsd_approved > 0):
            self.xsd.functions.approve(UNIV2Router["addr"], UINT256_MAX).transact({
                'nonce': w3.eth.getTransactionCount(address),
                'from' : address,
                'gas': 8000000,
                'gasPrice': 1,
            })

        logger.info(
            'Balance for {}: {:.2f} xSD, {:.2f} USDC'.format(
                address,
                reg_int(self.xsd.caller({'from' : address, 'gas': 8000000}).balanceOf(address), xSD['decimals']),
                reg_int(self.usdc_lp.caller({'from' : address, 'gas': 8000000}).balanceOf(address), USDC['decimals'])
            )
        )
        slippage = 0.01
        min_usdc_amount = (min_usdc_amount * (1 - slippage))

        self.uniswap_router.functions.swapExactTokensForTokens(
            unreg_int(xsd, xSD["decimals"]),
            unreg_int(min_usdc_amount, USDC["decimals"]),
            [self.xsd.address, self.usdc_lp.address],
            address,
            int(w3.eth.get_block('latest')['timestamp'] + DEADLINE_FROM_NOW)
        ).transact({
            'nonce': w3.eth.getTransactionCount(address),
            'from' : address,
            'gas': 8000000,
            'gasPrice': 1,
        })
        balance_after = self.xsd.caller({"from": address, 'gas': 8000000}).balanceOf(address)
        amount_sold = reg_int(abs(balance_after - balance_before), xSD["decimals"])
        return amount_sold
        
class DAO:
    """
    Represents the xSD DAO. Tracks xSD balance of DAO and total outstanding xSDS.
    """
    
    def __init__(self, contract, dollar_contract, **kwargs):
        """
        Take keyword arguments to nspecify experimental parameters.
        """
        self.contract = contract  
        self.dollar = dollar_contract    

    def xsd_supply(self):
        '''
        How many xSD exist?
        '''
        total = self.dollar.caller().totalSupply()
        return reg_int(total, xSD['decimals'])
        
    def total_coupons(self):
        """
        Get all outstanding unexpired coupons.
        """
        
        total = self.contract.caller().totalCoupons()
        return reg_int(total, xSD['decimals'])

    def coupon_balance_at_epoch(self, address, epoch):
        ''' 
            returns the total coupon balance for an address
        '''
        total_coupons = self.contract.caller({'from' : address, 'gas': 8000000}).balanceOfCoupons(address, epoch)
        return total_coupons

    def epoch(self, address):
        return self.contract.caller({'from' : address, 'gas': 8000000}).epoch()
        
    def coupon_bid(self, address, coupon_expiry, xsd_amount, max_coupon_amount):
        """
        Place a coupon bid
        """
        # placeCouponAuctionBid(uint256 couponEpochExpiry, uint256 dollarAmount, uint256 maxCouponAmount)

        self.contract.caller({'from' : address, 'gas': 8000000}).placeCouponAuctionBid(
            unreg_int(coupon_expiry, xSD["decimals"]),
            unreg_int(xsd_amount, xSD["decimals"]),
            unreg_int(xSD["decimals"], xSD["decimals"])
        )
        
    def redeem(self, address, epoch_expired, coupons_to_redeem):
        """
        Redeem the given number of coupons. Expired coupons redeem to 0.
        
        Pays out the underlying and premium in an expansion phase, or only the
        underlying otherwise, or if the coupons are expired.
        
        Assumes everything is actually redeemable.
        """
        total_before_coupons = self.coupon_balance_at_epoch(address, epoch_expired)
        self.contract.caller({'from' : address, 'gas': 8000000}).redeemCoupons(
            unreg_int(epoch_expired, xSD["decimals"]),
            unreg_int(coupons_to_redeem, xSD["decimals"])
        )
        total_after_coupons = self.coupon_balance_at_epoch(address, epoch_list)
            
        return total_before_coupons - total_after_coupons

    def token_balance_of(self, address):
        return reg_int(self.dollar.caller({'from' : address, 'gas': 8000000}).balanceOf(address), xSD["decimals"])
    def advance(self, address):
        before_advance = self.token_balance_of(address)
        self.contract.functions.advance().transact({
            'nonce': w3.eth.getTransactionCount(address),
            'from' : address,
            'gas': 8000000,
            'gasPrice': 1,
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
    
    def __init__(self, dao, uniswap, usdc, uniswap_router, uniswap_lp, xsd, agents, **kwargs):
        """
        Takes in experiment parameters and forwards them on to all components.
        """
        #pretty(dao.functions.__dict__)
        #sys.exit()
        self.uniswap = UniswapPool(uniswap, uniswap_router, uniswap_lp, usdc, xsd, **kwargs)
        self.dao = DAO(dao, xsd, **kwargs)
        self.agents = []
        self.usdc_lp = usdc
        self.uniswap_router = uniswap_router
        self.xsd_lp = xsd
        self.max_eth = 100000
        self.max_usdc = 100000

        is_mint = False
        if w3.eth.get_block('latest')["number"] == 16:
            # THIS ONLY NEEDS TO BE RUN ON NEW CONTRACTS
            is_mint = True
        
        for i in range(len(agents)):
            start_eth = round(random.random() * self.max_eth, UNI["decimals"]) 
            start_usdc = round(random.random() * self.max_usdc, USDC["decimals"])
            start_usdc_formatted = unreg_int(start_usdc, USDC["decimals"])
            address = agents[i]
            
            if IS_DEBUG:
                '''
                (max_amount, _) = self.uniswap.uniswap_router.caller({'from' : address, 'gas': 8000000}).getAmountsIn(
                    unreg_int(30, xSD['decimals']), 
                    [self.usdc_lp.address, self.xsd_lp.address]
                )

                max_amount = reg_int(max_amount, USDC['decimals'])
                '''
                (_, max_amount) = self.uniswap.uniswap_router.caller({'from' : address, 'gas': 8000000}).getAmountsOut(
                    unreg_int(10, xSD['decimals']), 
                    [self.xsd_lp.address, self.usdc_lp.address]
                )

                max_amount = reg_int(max_amount, USDC['decimals'])
                    

                print (10, max_amount)
                sys.exit()

                usdc_b, xsd_b = self.uniswap.getTokenBalance()
                print (usdc_b, xsd_b)
                #print(self.dao.advance(address))

                commitment = random.random() * 0.1
                to_use_xsd = portion_dedusted(self.dao.token_balance_of(address), commitment)

                price = self.uniswap.xsd_price()
                print("price", price)

                revs = self.uniswap.getReserves()

                min_xsd_needed = reg_int(self.uniswap_router.caller({'from' : address, 'gas': 8000000}).quote(unreg_int(start_usdc, xSD['decimals']), revs[0], revs[1]), xSD['decimals'])
                print ("min_xsd_needed", min_xsd_needed)

                usdc = portion_dedusted(start_usdc, commitment)
                max_amount = price / usdc
                print("xSD available", reg_int(revs[1],xSD['decimals']))
                xsd = self.uniswap.sell(address, reg_int(revs[1],xSD['decimals']) , max_amount)

                print("xSD sold", xsd)
                print("price", self.uniswap.xsd_price())

                usdc_b, xsd_b = self.uniswap.getTokenBalance()

                print (usdc_b, xsd_b)
                sys.exit()

            
            

            if is_mint:
                # need to mint USDC to the wallets for each agent
                usdc.functions.mint(address, int(start_usdc_formatted)).transact({
                    'nonce': w3.eth.getTransactionCount(address),
                    'from' : address,
                    'gas': 8000000,
                    'gasPrice': 1,
                })

            agent = Agent(self.dao, uniswap, xsd, usdc, starting_eth=start_eth, starting_usdc=start_usdc, wallet_address=address, **kwargs)
            self.agents.append(agent)
        
    def log(self, stream, header=False):
        """
        Log model statistics a TSV line.
        If header is True, include a header.
        """
        
        if header:
            stream.write("#block\tprice\tsupply\tcoupons\tfaith\n")
        
        stream.write('{}\t{:.2f}\t{:.2f}\t{:.2f}\t{:.2f}\n'.format(
            w3.eth.get_block('latest')["number"], self.uniswap.xsd_price(), self.dao.xsd_supply(), self.dao.total_coupons(), self.get_overall_faith()))
       
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

        #randomly have an agent advance the epoch
        seleted_advancer = self.agents[int(random.random() * (len(self.agents) - 1))]
        xsd = self.dao.advance(seleted_advancer.address)
        seleted_advancer.xsd += xsd
        logger.debug("Advance for {:.2f} xSD".format(xsd))

        (usdc_b, xsd_b) = self.uniswap.getTokenBalance()
        
        logger.info("Block {}, epoch {}, price {:.2f}, supply {:.2f}, faith: {:.2f}, bonded {:2.1f}%, coupons: {:.2f}, liquidity {:.2f} xSD / {:.2f} USDC".format(
            w3.eth.get_block('latest')["number"], self.dao.epoch(seleted_advancer.address), self.uniswap.xsd_price(), self.dao.xsd_supply(),
            self.get_overall_faith(), 0, self.dao.total_coupons(),
            xsd_b, usdc_b))
        
        anyone_acted = False

        for agent_num, a in enumerate(self.agents):
            # TODO: real strategy
            options = []
            if a.usdc > 0 and self.uniswap.operational() and (a.lp == 0):
                options.append("buy")
            if a.xsd > 0 and self.uniswap.operational() and (a.lp == 0):
                options.append("sell")
            '''
            TODO: CURRENTLY NO INCENTIVE TO BOND INTO LP OR DAO (EXCEPT FOR VOTING)
            if a.xsd > 0:
                options.append("bond")
            if a.xsds > 0:
                options.append("unbond")
            '''
            if a.xsd > 0 and self.uniswap.xsd_price() <= 1.0:
                options.append("coupon_bid")

            # try any ways but handle traceback, faster than looping over all the epocks
            if self.uniswap.xsd_price() >= 1.0:
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
                        advance, provide_liquidity, remove_liquidity, buy, sell, coupon_bid, redeem
                '''
        
                strategy = a.get_strategy(w3.eth.get_block('latest')["number"], self.uniswap.xsd_price(), self.dao.xsd_supply())
                
                weights = [strategy[o] for o in options]
                
                action = random.choices(options, weights=weights)[0]
                
                # What fraction of the total possible amount of doing this
                # action will the agent do?
                commitment = random.random() * 0.1
                
                logger.debug("Agent {}: {}".format(agent_num, action))
                
                if action == "buy":
                    # this will limit the size of orders avaialble
                    (usdc_b, xsd_b) = self.uniswap.getTokenBalance()
                    print("usdc_b:", usdc_b, "xsd_b:", xsd_b)

                    if xsd_b > 0:
                        usdc = portion_dedusted(a.usdc, commitment)
                    else:
                        continue
                    
                    price = self.uniswap.xsd_price()
                    usdc_in = usdc#min(usdc,usdc_b)
                    (max_amount, _) = self.uniswap_router.caller({'from' : a.address, 'gas': 8000000}).getAmountsIn(
                        unreg_int(usdc_in, xSD['decimals']), 
                        [self.usdc_lp.address, self.xsd_lp.address]
                    )
                    max_amount = reg_int(max_amount, USDC['decimals'])
                    
                    try:                        
                        logger.info("Buy init {:.2f} xSD @ {:.2f} for {:.2f} USDC".format(usdc_in, price, max_amount))

                        xsd = self.uniswap.buy(a.address, usdc_in, max_amount)
                        a.usdc -= usdc
                        a.xsd += xsd
                        logger.info("Buy end {:.2f} xSD @ {:.2f} for {:.2f} USDC".format(xsd, price, usdc))
                        
                    except Exception as inst:
                        print({"agent": a.address, "error": inst, "action": "buy"})
                elif action == "sell":
                    # this will limit the size of orders avaialble
                    (usdc_b, xsd_b) = self.uniswap.getTokenBalance()
                    print("usdc_b:", usdc_b, "xsd_b:", xsd_b)
                    if xsd_b > 0 and usdc_b > 0:
                        xsd = min(portion_dedusted(a.xsd, commitment), xsd_b)
                    else:
                        continue
                    price = self.uniswap.xsd_price()
                    xsd_out = min(xsd, xsd_b)
                    (_, max_amount) = self.uniswap_router.caller({'from' : a.address, 'gas': 8000000}).getAmountsOut(
                        unreg_int(xsd_out, xSD['decimals']), 
                        [self.xsd_lp.address, self.usdc_lp.address]
                    )
                    max_amount = reg_int(max_amount, USDC['decimals'])

                    try:
                        logger.info("Sell init {:.2f} xSD @ {:.2f} for {:.2f} USDC".format(xsd_out, price, max_amount))
                        usdc = self.uniswap.sell(a.address, xsd_out, max_amount)
                        a.xsd -= xsd
                        a.usdc += usdc
                        logger.info("Sell end {:.2f} xSD @ {:.2f} for {:.2f} USDC".format(xsd, price, usdc))
                    except Exception as inst:
                        print({"agent": a.address, "error": inst, "action": "sell"})
                elif action == "advance":
                    xsd = self.dao.advance(a.address)
                    a.xsd = xsd
                    logger.debug("Advance for {:.2f} xSD".format(xsd))
                elif action == "coupon_bid":
                    xsd_at_risk = portion_dedusted(a.xsd, commitment)
                    rand_epoch_expiry = int(random.random() * 10000000)
                    rand_max_coupons = random.random() * 10000000 * xsd_at_risk
                    self.dao.coupon_bid(a.address, rand_epoch_expiry, xsd_at_risk, rand_max_coupons)
                    a.total_coupons_bid += rand_max_coupons
                    a.coupon_expirys.append(rand_epoch_expiry)
                    logger.debug("Bid to burn {:.2f} xSD for {:.2f} coupons with expiry {:.2f}".format(xsd_at_risk, rand_max_coupons, rand_epoch_expiry))
                elif action == "redeem":
                    total_redeemed = 0
                    for c_idx in a.coupon_expirys:
                        try:
                            total_redeemed += self.dao.redeem(a.address, c_idx, a.total_coupons_bid)
                        except:
                            pass

                    if total_redeemed > 0:
                        a.total_coupons_bid -= total_redeemed
                        logger.debug("Redeem {:.2f} coupons for {:.2f} xSD".format(total_redeemed, total_redeemed))
                elif action == "provide_liquidity":
                    price = self.uniswap.xsd_price()
                    min_xsd_needed = 0                   
                    if a.xsd * price < a.usdc:
                        xsd = portion_dedusted(a.xsd, commitment)
                        usdc = xsd * price
                    else:
                        usdc = portion_dedusted(a.usdc, commitment)
                        xsd = usdc / price

                    revs = self.uniswap.getReserves()
                    if revs[0] > 0:
                        min_xsd_needed = reg_int(self.uniswap_router.caller({'from' : a.address, 'gas': 8000000}).quote(unreg_int(usdc, xSD['decimals']), revs[0], revs[1]), xSD['decimals'])

                        print("min_xsd_needed", min_xsd_needed)
                        if min_xsd_needed < xsd:
                            min_xsd_needed = xsd
                            print("min_xsd_needed_adj", min_xsd_needed)
                    else:
                        min_xsd_needed = xsd


                    if int(min_xsd_needed) <= 0:
                        continue

                    logger.info("Provide {:.2f} xSD (of {:.2f} xSD) and {:.2f} USDC".format(min_xsd_needed, a.xsd, usdc))
                    after_lp = self.uniswap.provide_liquidity(a.address, min_xsd_needed, usdc)

                    usdc_b, xsd_b = self.uniswap.getTokenBalance()
                    min_xsd_amount_after = xsd_b / usdc_b * after_lp
                    min_usdc_amount_after = usdc_b / xsd_b * after_lp

                    diff_xsd = (min_xsd_amount_after - xsd_b)
                    diff_usdc = (min_usdc_amount_after - usdc_b)
                    
                    a.xsd = max(0, a.xsd - diff_xsd)
                    a.usdc = max(0, a.usdc - diff_usdc)
                    a.lp += after_lp
                elif action == "remove_liquidity":
                    lp = portion_dedusted(a.lp, commitment)
                    total_lp = self.uniswap.total_lp(a.address)
                    
                    usdc_b, xsd_b = self.uniswap.getTokenBalance()

                    

                    slippage = 0.1
                    min_reduction = 1.0 - slippage

                    min_xsd_amount = xsd_b * (lp / float(total_lp)) * min_reduction
                    min_usdc_amount = usdc_b * (lp / float(total_lp)) * min_reduction

                    #print(min_xsd_amount * min_reduction, min_usdc_amount * min_reduction, lp)

                    try:
                        logger.debug("Stop providing {:.2f} xSD and {:.2f} USDC".format(min_xsd_amount, min_usdc_amount))
                        after_lp = self.uniswap.remove_liquidity(a.address, lp, min_xsd_amount, min_usdc_amount)

                        min_xsd_amount_after = xsd_b / usdc_b * after_lp
                        min_usdc_amount_after = usdc_b / xsd_b * after_lp

                        diff_xsd = (min_xsd_amount - min_xsd_amount_after)
                        diff_usdc = (min_usdc_amount - min_usdc_amount_after)
                        
                        a.lp -= after_lp
                        a.xsd += diff_xsd
                        a.usdc += diff_usdc
                        
                    except Exception as inst:
                        print({"agent": a.address, "error": inst, "action": "remove_liquidity"})
                else:
                    raise RuntimeError("Bad action: " + action)
                    
                anyone_acted = True
            else:
                # It's normal for agents other then the first to advance to not be able to act on block 0.
                pass
        return anyone_acted

def main():
    """
    Main function: run the simulation.
    """
    max_accounts = 20
    print(w3.eth.get_block('latest')["number"])
    if w3.eth.get_block('latest')["number"] == 16:
        # THIS ONLY NEEDS TO BE RUN ON NEW CONTRACTS
        print(provider.make_request("evm_increaseTime", [1606348800]))

    print('Total Agents:',len(w3.eth.accounts[:max_accounts]))
    dao = w3.eth.contract(abi=DaoContract['abi'], address=xSDS["addr"])
    uniswap = w3.eth.contract(abi=UniswapPairContract['abi'], address=UNI["addr"])
    usdc = w3.eth.contract(abi=USDCContract['abi'], address=USDC["addr"])
    
    uniswap_router = w3.eth.contract(abi=UniswapRouterAbiContract['abi'], address=UNIV2Router["addr"])
    uniswap_lp = w3.eth.contract(abi=PoolContract['abi'], address=UNIV2LP["addr"])

    xsd = w3.eth.contract(abi=DollarContract['abi'], address=dao.caller().dollar())
    print (dao.caller().dollar())

    logging.basicConfig(level=logging.INFO)

    # Make a model of the economy
    start_init = time.time()
    print ('INIT STARTED')
    model = Model(dao, uniswap, usdc, uniswap_router, uniswap_lp, xsd, w3.eth.accounts[:max_accounts], min_faith=0.5E6, max_faith=1E6, use_faith=True, expire_all=True)
    end_init = time.time()
    print ('INIT FINISHED', end_init - start_init, '(s)')

    # Make a log file for system parameters, for analysis
    stream = open("log.tsv", "w")
    
    for i in range(50000):
        # Every block
        # Try and tick the model
        start_iter = time.time()
        if not model.step():
            # Nobody could act
            print("Nobody could act")
            break
        end_iter = time.time()
        print('iter: %s, sys time %s' % (i, end_iter-start_iter))
        # Log system state
        model.log(stream, header=(i == 0))
        
if __name__ == "__main__":
    main()
