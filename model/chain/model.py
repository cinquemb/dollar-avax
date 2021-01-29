#!/usr/bin/env python3

"""
model.py: agent-based model of ESD system behavior, against a testnet
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


logger = logging.getLogger(__name__)
provider = Web3.HTTPProvider('http://localhost:7545')
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
    "decimals": 18,
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

DaoContract = json.loads(open('./build/contracts/Implementation.json', 'r+').read())
USDCContract = json.loads(open('./build/contracts/TestnetUSDC.json', 'r+').read())

UniswapPairContract = json.loads(open('./build/contracts/IUniswapV2Pair.json', 'r+').read())
UniswapRouterAbiContract = json.loads(open('./node_modules/@uniswap/v2-periphery/build/UniswapV2Router02.json', 'r+').read())
TokenContract = json.loads(open('./build/contracts/Root.json', 'r+').read())
PoolContract = json.loads(open('./build/contracts/Pool.json', 'r+').read())

def get_addr_from_contract(contract):
    return contract["networks"][str(sorted(map(int,contract["networks"].keys()))[-1])]["address"]

xSD['addr'] = get_addr_from_contract(DaoContract)
xSDS['addr'] = get_addr_from_contract(TokenContract)

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
    
    def __init__(self, **kwargs):
        # ESD balance
        self.esd = 0.0
        # USDC balance
        self.usdc = kwargs.get("starting_usdc", 0.0)
        # ESDS (Dao share) balance
        self.esds = 0.0
        # Eth balance
        self.eth = kwargs.get("starting_eth", 0.0)
        # Uniswap LP share balance
        self.lp = 0.0
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
        
        # What ESD is coming to us in future epochs?
        self.future_esd = collections.defaultdict(float)

        # add wallet addr
        self.address = kwargs.get("wallet_address", '0x0000000000000000000000000000000000000000')
        
    def __str__(self):
        """
        Turn into a readable string summary.
        """
        return "Agent(esd={:.2f}, usdc={:.2f}, esds={}, eth={}, lp={}, coupons={:.2f})".format(
            self.esd, self.usdc, self.esds, self.eth, self.lp,
            sum(self.underlying_coupons.values()) + sum(self.premium_coupons.values()))
        
    def get_strategy(self, block, price, total_supply):
        """
        Get weights, as a dict from action to float, as a function of the price.
        """
        
        strategy = collections.defaultdict(lambda: 1.0)
        
        # TODO: real (learned? adversarial? GA?) model of the agents
        # TODO: agent preferences/utility function
        
        # People are slow to coupon
        strategy["coupon"] = 0.1

        # People are slow to coupon bid
        strategy["coupon_bid"] = 0.1

        # And to unbond because of the delay
        strategy["unbond"] = 0.1
        
        if price > 1.0:
            # No rewards for expansion by itself
            strategy["bond"] = 2.0
            # And not unbond
            strategy["unbond"] = 2.0
            # Or redeem if possible
            strategy["redeem"] = 100
        else:
            # We probably want to unbond due to no returns
            strategy["unbond"] = 2.0
            # And not bond
            strategy["bond"] = 0.5
       
        if self.use_faith:
            # Vary our strategy based on how much ESD we think ought to exist
            if price * total_supply > self.get_faith(block, price, total_supply):
                # There is too much ESD, so we want to sell
                strategy["unbond"] *= 2
                strategy["sell"] = 4.0
            else:
                # We prefer to buy
                strategy["buy"] = 4.0
        
        return strategy
        
    def get_faith(self, block, price, total_supply):
        """
        Get the total faith in ESD that this agent has, in USDC.
        
        If the market cap is over the faith, the agent thinks the system is
        over-valued. If the market cap is under the faith, the agent thinks the
        system is under-valued.
        """
        
        # TODO: model the real economy as bidding on utility in
        # mutually-beneficial exchanges conducted in ESD, for which a velocity
        # is needed, instead of an abstract faith?
        
        # TODO: different faith for different people
        
        center_faith = (self.max_faith + self.min_faith) / 2
        swing_faith = (self.max_faith - self.min_faith) / 2
        faith = center_faith + swing_faith * math.sin(block * (2 * math.pi / 5000))
        
        return faith

class UniswapPool:
    """
    Represents the Uniswap pool. Tracks ESD and USDC balances of pool, and total outstanding LP shares.
    """
    
    def __init__(self, uniswap, uniswap_router, uniswap_lp, **kwargs):
        self.uniswap_pair = uniswap
        self.uniswap_router = uniswap_router
        self.uniswap_lp = uniswap_lp
        # ESD balance
        self.esd = 0.0
        # USDC balance
        self.usdc = 0.0
        # Total shares
        self.total_shares = 0.0
        
    def operational(self):
        """
        Return true if buying and selling is possible.
        """
        reserve, token0 = self.getReserves()
        token0Balance = reserve[0]
        token1Balance = reserve[1]
        return token0Balance > 0 and token1Balance > 0
    
    def getToken0(self):
        exchange = self.uniswap_pair
        return exchange.functions.token0().call()

    def getReserves(self):
        exchange = self.uniswap_pair
        return exchange.functions.getReserves().call()

    def getInstantaneousPrice(self):
      reserve, token0 = self.getReserves(), self.getToken0()
      token0Balance = reserve[0]
      token1Balance = reserve[1]
      if (token0.lower() == USDC["addr"].lower()):
        return int(token0Balance) * pow(10, 12) / float(int(token1Balance)) if int(token1Balance) != 0 else 0
      return int(token1Balance) * pow(10, 12) / float(int(token0Balance)) if int(token0Balance) != 0 else 0
    
    def esd_price(self):
        """
        Get the current ESD price in USDC.
        """
        
        if self.operational():
            return self.getInstantaneousPrice()
        else:
            return 1.0
        
    def deposit(self, esd, usdc):
        """
        Deposit the given number of ESD and USDC. Returns the number of new LP shares minted.
        """
        
        # TODO: get the real uniswap deposit logic
        
        new_value = esd * self.esd_price() + usdc
        held_value = self.esd * self.esd_price() + self.usdc
        if held_value > 0:
            new_shares = self.total_shares / held_value * new_value
        else:
            new_shares = 1
        
        self.esd += esd
        self.usdc += usdc
        self.total_shares += new_shares
        
        return new_shares
        
    def withdraw(self, shares):
        """
        Withdraw the given number of shares. Gets a balanced amount of ESD and USDC.
        Returns a tuple of (ESD, USDC)
        """
        
        if self.total_shares == 0:
            return 0, 0
        
        # TODO: get the real uniswap withdraw logic
        portion = shares / self.total_shares
        
        esd = portion * self.esd
        usdc = portion * self.usdc
        
        self.total_shares = max(0, self.total_shares - shares)
        self.esd = max(0, self.esd - esd)
        self.usdc = max(0, self.usdc - usdc)
        
        return (esd, usdc)
        
    def buy(self, account, usdc, max_esd_amount):
        """
        Spend the given number of USDC to buy xSD. Returns the xSD bought.
        ['swapTokensForExactTokens(uint256,uint256,address[],address,uint256)']
        """  
        print (usdc, max_esd_amount, [USDC['addr'], xSD['addr']], account, int(time.time()) + DEADLINE_FROM_NOW)      
        amount_bought = self.uniswap_router.functions.swapTokensForExactTokens(
            int(round(usdc, 6) * pow(10, USDC["decimals"])),
            int(round(max_esd_amount, xSD["decimals"]) * pow(10, xSD["decimals"])),
            [USDC['addr'], xSD['addr']],
            account,
            (int(time.time()) + DEADLINE_FROM_NOW) * pow(10, UNI["decimals"])
        ).call()
        print(amount_bought)
        
        
        
        return (amount_bought)
        
    def sell(self, account, esd, min_usdc_amount):
        """
        Sell the given number of xSD for USDC. Returns the xSDC received.
        """        
        amount_sold = self.uniswap_router.functions.swapExactTokensForTokens(
            int(round(esd, xSD["decimals"]) * pow(10, xSD["decimals"])),
            int(round(min_usdc_amount, 6) * pow(10, USDC["decimals"])),
            [xSD['addr'], USDC['addr']],
            account,
            (int(time.time()) + DEADLINE_FROM_NOW) * pow(10, UNI["decimals"])
        ).call()
        print (amount_sold)
        return (amount_sold)
        
class DAO:
    """
    Represents the ESD DAO. Tracks ESD balance of DAO and total outstanding ESDS.
    """
    
    def __init__(self, contract, **kwargs):
        """
        Take keyword arguments to nspecify experimental parameters.
        """
        self.contract = contract        
        # How many ESD are bonded
        self.esd = 0.0
        # How many ESD exist?
        self.esd_supply = 0.0
        # How many shares are outstanding
        self.total_shares = 0.0
        # What block did the epoch start
        self.epoch_block = 0
        # Are we expanding or contracting
        self.expanding = False
        # And since when?
        self.phase_since = -1
        
        # TODO: add real interest/debt/coupon model
        self.interest = 1E-4
        # How many ESD can be issued in coupons?
        self.debt = 0.0
        # How many ESD can be redeemed from coupons?
        self.total_redeemable = 0.0
        
        # How many epochs do coupons take to expire?
        self.expiry_delay = 90
        
        # Coupon underlying parts by issue epoch
        self.underlying_coupon_supply = collections.defaultdict(float)
        # Coupon premium parts by issue epoch
        self.premium_coupon_supply = collections.defaultdict(float)
        
        # How many coupons expired?
        self.expired_coupons = 0.0
        
        # Should all coupon parts expire?
        self.param_expire_all = kwargs.get("expire_all", False)
        
    def total_coupons(self):
        """
        Get all outstanding unexpired coupons.
        """
        
        total = 0.0
        for epoch, amount in self.underlying_coupon_supply.items():
            if epoch + self.expiry_delay >= self.epoch or not self.param_expire_all:
                # Underlying isn't expired
                total += amount
        for epoch, amount in self.premium_coupon_supply.items():
            if epoch + self.expiry_delay >= self.epoch:
                # Premium isn't expired
                total += amount
        return total
        
    def bond(self, esd):
        """
        Deposit and bond the given amount of ESD.
        Returns the number of ESDS minted.
        """
    
        # TODO: model lockups
        
        if self.esd > 0:
            new_shares = self.total_shares / self.esd * esd
        else:
            new_shares = 1.0
        
        self.esd += esd
        self.total_shares += new_shares
        
        return new_shares
        
    def unbond(self, shares):
        """
        Unbond and withdraw the given number of shares.
        Returns the amount of ESD received, and the epoch it will be available.
        """
        
        
        if self.total_shares == 0:
            return 0, self.epoch + 1
        
        portion = shares / self.total_shares
        
        esd = self.esd * portion
        
        self.total_shares = max(0, self.total_shares - shares)
        self.esd = max(0, self.esd - esd)
        
        return esd, self.epoch + 15

    def coupon_balance(self, wallet):
        ''' 
            TODO: IS SLOWWWWWWWW, how can i speed this up
            returns the coupon balance for an address
        '''
        current_epoch = self.epoch(wallet)
        total_coupons = 0
        for i in range(0, current_epoch):
            total_coupons += self.contract.caller({'from' : wallet, 'gas': 8000000}).balanceOfCoupons(wallet, i)
        return total_coupons

    def epoch(self, wallet):
        return self.contract.caller({'from' : wallet, 'gas': 8000000}).epoch()
        
    def coupon_bid(self, esd):
        """
        Spend the given number of ESD on coupons.
        Returns (issued_at, underlying_coupons, premium_coupons)
        """
        
        rate = self.get_coupon_rate()
        
        underlying_coupons = esd
        premium_coupons = esd * rate
        issued_at = self.epoch
        
        self.esd_supply = max(0, self.esd_supply - esd)
        self.debt = max(0, self.debt - esd)
        self.underlying_coupon_supply[issued_at] += underlying_coupons
        self.premium_coupon_supply[issued_at] += premium_coupons
        
        return (issued_at, underlying_coupons, premium_coupons)
        
    def filter_expired(self, underlying, premium):
        """
        Given a dict of underlying coupon balances by creation epoch, and
        premium coupon balances by epoch, drop all the coupons that are
        expired.
        
        Return the total value expired.
        """
        
        total = 0
        
        expired = set()
        unexpired = set()
        for epoch in premium.keys():
            if epoch + self.expiry_delay < self.epoch:
                expired.add(epoch)
        for to_drop in expired:
            total += premium[to_drop]
            del premium[to_drop]
            
        if self.param_expire_all:
            # Also do the underlying
            for epoch in underlying.keys():
                if epoch + self.expiry_delay < self.epoch:
                    expired.add(epoch)
            for to_drop in expired:
                total += underlying[to_drop]
                del underlying[to_drop]
                
        return total
        
    def expire_coupons(self):
        """
        Expire all expired coupons in the total supplies.
        """
        
        self.expired_coupons += self.filter_expired(self.underlying_coupon_supply,
                                                    self.premium_coupon_supply)
        
    def redeemable(self, issued_at, underlying_coupons, premium_coupons):
        """
        Return the maximum (underlying, premium) coupons currently redeemable
        from those issued at the given epoch, up to the given limits.
        
        Redeemable coupons may actually be expired, in which case they redeem to 0.
        
        Premium coupons will always be redeemed even if expired; they just
        redeem for no money.
        """
        
        # TODO: real redemption cap logic
        
        if self.expanding and issued_at + 2 >= self.epoch:
            # Coupons are only redeemable at all 2 epochs after issuance, and during expansions
            if underlying_coupons >= self.total_redeemable:
                return (self.total_redeemable, 0)
            elif underlying_coupons + premium_coupons >= self.total_redeemable:
                return (underlying_coupons, self.total_redeemable - underlying_coupons)
            else:
                return (underlying_coupons, premium_coupons)
        else:   
            # Don't let people redeem anything when not expanding, even the
            # underlying.
            return (0.0, 0.0)
    
    def redeem(self, issued_at, underlying_coupons, premium_coupons):
        """
        Redeem the given number of coupons. Expired coupons redeem to 0.
        
        Pays out the underlying and premium in an expansion phase, or only the
        underlying otherwise, or if the coupons are expired.
        
        Assumes everything is actually redeemable.
        """
        
        # TODO: real redeem logic
        
        self.underlying_coupon_supply[issued_at] = max(0, self.underlying_coupon_supply[issued_at] - underlying_coupons)
        self.premium_coupon_supply[issued_at] = max(0, self.premium_coupon_supply[issued_at] - premium_coupons)
        
        if self.epoch <= issued_at + self.expiry_delay:
            # Not expired
            esd = underlying_coupons + premium_coupons
        else:
            # Expired
            if self.param_expire_all:
                # Destroy underlying ESD
                esd = 0
            else:
                # Return underlying ESD
                esd = underlying_coupons
            
        self.esd_supply += esd
        self.total_redeemable -= esd
            
        return esd
        
    def expire(self, issued_at, underlying_coupons, premium_coupons):
        """
        Handle expiration of coupons.
        """
        
    def fee(self):
        """
        How much does it cost in ETH to advance, probably.
        """
        
        return 0.001

    def advance(self, address):
        print(self.epoch(address))
        '''
        tx = self.contract.functions.advance().buildTransaction({
            'nonce': w3.eth.getTransactionCount(address),
            'from': address,
            'gas': 8000000,
            'gasPrice': 1,
        })
        print(tx)
        signed_tx = w3.eth.account.signTransaction(tx, private_key='0xbcc21bcb2168e415067967842967b6553fd91ce683041ef78a4064115142f13d')
        print(signed_tx)
        raw_tx = w3.eth.sendRawTransaction(signed_tx.rawTransaction)
        print(raw_tx)
        '''

        print(self.contract.functions.advance().transact({'from' : address, 'gas': 8000000}))

        print(self.contract.caller({'from' : address, 'gas': 8000000}).advance())
        print(self.epoch(address))
        sys.exit()
        return self.contract.caller({'from' : address, 'gas': 8000000}).balanceOf(address)

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
    
    def __init__(self, dao, uniswap, usdc, uniswap_router, uniswap_lp, agents, **kwargs):
        """
        Takes in experiment parameters and forwards them on to all components.
        """
        #pretty(dao.functions.__dict__)
        self.uniswap = UniswapPool(uniswap, uniswap_router, uniswap_lp, **kwargs)
        self.dao = DAO(dao, **kwargs)
        self.agents = []
        self.max_eth = 100000
        self.max_usdc = 100000
        for i in range(len(agents)):
            start_eth = round(random.random() * self.max_eth, UNI["decimals"]) 
            start_usdc = round(random.random() * self.max_usdc, USDC["decimals"])
            start_usdc_formatted = int(start_usdc * pow(10, USDC["decimals"]))
            address = agents[i]
            print('here', address)

            print(provider.make_request("evm_increaseTime", [1]))
            total_esd = self.dao.advance(address)
            print(total_esd)

            '''
            commitment = random.random() * 0.1
            to_use_usdc = portion_dedusted(start_usdc, commitment)
            self.uniswap.buy(address, to_use_usdc, 100)
            '''

            # need to mint USDC to the wallets for each agent
            usdc.functions.mint(address, start_usdc_formatted).call()
            agent = Agent(starting_eth=start_eth, starting_usdc=start_usdc, wallet_address=address, **kwargs)
            self.agents.append(agent)
        
        # Track time in blocks
        self.block = 0
        
    def log(self, stream, header=False):
        """
        Log model statistics a TSV line.
        If header is True, include a header.
        """
        
        if header:
            stream.write("#block\tprice\tsupply\tbonded\tdebt\tcoupons\texpired\tfaith\n")
        
        stream.write('{}\t{:.2f}\t{:.2f}\t{}\t{:.2f}\t{:.2f}\t{:.2f}\t{:.2f}\n'.format(
            self.block, self.uniswap.esd_price(), self.dao.esd_supply, self.dao.esd/self.dao.esd_supply,
            self.dao.debt, self.dao.total_coupons(), self.dao.expired_coupons,
            self.get_overall_faith()))
       
    def get_overall_faith(self):
        """
        What target should the system be trying to hit in ESD market cap?
        """
        
        return self.agents[0].get_faith(self.block, self.uniswap.esd_price(), self.dao.esd_supply)
       
    def step(self):
        """
        Step the model by one block. Let all the agents act.
        
        Returns True if anyone could act.
        """
        
        self.block += 1
        provider.make_request("evm_increaseTime", [7201])
        
        # Clean up coupon expiry on the DAO side
        # self.dao.expire_coupons()
        
        logger.info("Block {}, epoch {}, price {:.2f}, supply {:.2f}, faith: {:.2f}, bonded {:2.1f}%, coupons: {:.2f}, liquidity {:.2f} ESD / {:.2f} USDC".format(
            self.block, self.dao.epoch(), self.uniswap.esd_price(), self.dao.esd_supply,
            self.get_overall_faith(), self.dao.esd / max(self.dao.esd_supply, 1E-9) * 100, self.dao.total_coupons(),
            self.uniswap.esd, self.uniswap.usdc))
        
        anyone_acted = False
        for agent_num, a in enumerate(self.agents):
            # TODO: real strategy
            options = []
            if a.usdc > 0 and self.uniswap.operational():
                options.append("buy")
            if a.esd > 0 and self.uniswap.operational():
                options.append("sell")
            if a.eth >= self.dao.fee():
                options.append("advance")
            if a.esd > 0:
                options.append("bond")
            if a.esds > 0:
                options.append("unbond")
            if a.esd > 0 and self.dao.esd_price() <= 1.0:
                options.append("coupon_bid")

            # try any ways but handle traceback, faster than looping over all the epocks
            if self.dao.esd_price() >= 1.0:
                options.append("redeem")
            if a.usdc > 0 and a.esd > 0:
                options.append("deposit")
            if a.lp > 0:
                options.append("withdraw")
                                
            if len(options) > 0:
                # We can act
        
                strategy = a.get_strategy(self.block, self.uniswap.esd_price(), self.dao.esd_supply)
                
                weights = [strategy[o] for o in options]
                
                action = random.choices(options, weights=weights)[0]
                
                # What fraction of the total possible amount of doing this
                # action will the agent do?
                commitment = random.random() * 0.1
                
                logger.debug("Agent {}: {}".format(agent_num, action))
                
                if action == "buy":
                    usdc = portion_dedusted(a.usdc, commitment)
                    price = self.uniswap.esd_price()
                    max_amount = usdc / price
                    esd = self.uniswap.buy(a.address, usdc, max_amount)
                    a.usdc -= usdc
                    a.esd += esd
                    logger.debug("Buy {:.2f} ESD @ {:.2f} for {:.2f} USDC".format(esd, price, usdc))
                elif action == "sell":
                    esd = portion_dedusted(a.esd, commitment)
                    price = self.uniswap.esd_price()
                    max_amount = price / esd
                    usdc = self.uniswap.sell(a.address, esd, max_amount)
                    a.esd -= esd
                    a.usdc += usdc
                    logger.debug("Sell {:.2f} ESD @ {:.2f} for {:.2f} USDC".format(esd, price, usdc))
                elif action == "advance":
                    esd = self.dao.advance(a.address)
                    a.esd = esd
                    logger.debug("Advance for {:.2f} ESD".format(esd))
                elif action == "bond":
                    esd = portion_dedusted(a.esd, commitment)
                    esds = self.dao.bond(esd)
                    a.esd -= esd
                    a.esds += esds
                    logger.debug("Bond {:.2f} ESD".format(esd))
                elif action == "unbond":
                    esds = portion_dedusted(a.esds, commitment)
                    esd, when = self.dao.unbond(esds)
                    a.esds -= esds
                    logger.debug("Unbond {:.2f} ESD".format(esd))
                elif action == "coupon_bid":
                    logger.debug("Bid to burn {:.2f} ESD for {:.2f} coupons".format(esd, underlying_coupons + premium_coupons))
                elif action == "redeem":
                    logger.debug("Redeem {:.2f} coupons for {:.2f} ESD".format(total_redeemed, total_esd))
                elif action == "deposit":
                    price = self.uniswap.esd_price()
                    
                    if a.esd * price < a.usdc:
                        esd = portion_dedusted(a.esd, commitment)
                        usdc = esd * price
                    else:
                        usdc = portion_dedusted(a.usdc, commitment)
                        esd = usdc / price
                    lp = self.uniswap.deposit(esd, usdc)
                    a.esd = max(0, a.esd - esd)
                    a.usdc = max(0, a.usdc - usdc)
                    a.lp += lp
                    logger.debug("Provide {:.2f} ESD and {:.2f} USDC".format(esd, usdc))
                elif action == "withdraw":
                    lp = portion_dedusted(a.lp, commitment)
                    (esd, usdc) = self.uniswap.withdraw(lp)
                    a.lp -= lp
                    a.esd += esd
                    a.usdc += usdc
                    logger.debug("Stop providing {:.2f} ESD and {:.2f} USDC".format(esd, usdc))
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

    print('Total Agents:',len(w3.eth.accounts))
    dao = w3.eth.contract(abi=DaoContract['abi'], address=xSD["addr"])
    uniswap = w3.eth.contract(abi=UniswapPairContract['abi'], address=UNI["addr"])
    usdc = w3.eth.contract(abi=USDCContract['abi'], address=USDC["addr"])
    xsds = w3.eth.contract(abi=TokenContract['abi'], address=xSDS["addr"]) 
    uniswap_router = w3.eth.contract(abi=UniswapRouterAbiContract['abi'], address=UNIV2Router["addr"])
    uniswap_lp = w3.eth.contract(abi=PoolContract['abi'], address=UNIV2LP["addr"])

    #pretty(uniswap_router.functions.__dict__, indent=4)
    #pretty(dao.functions.__dict__, indent=4)

    logging.basicConfig(level=logging.INFO)

    # Make a model of the economy
    model = Model(dao, uniswap, usdc, uniswap_router, uniswap_lp, w3.eth.accounts, min_faith=0.5E6, max_faith=1E6, use_faith=True, expire_all=True)

    '''
    
    
    # Make a log file for system parameters, for analysis
    stream = open("log.tsv", "w")
    
    for i in range(50000):
        # Every block
        # Try and tick the model
        if not model.step():
            # Nobody could act
            break
        # Log system state
        model.log(stream, header=(i == 0))
    '''
        
if __name__ == "__main__":
    main()
