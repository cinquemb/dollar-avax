const { accounts, contract } = require('@openzeppelin/test-environment');

const { BN, expectEvent } = require('@openzeppelin/test-helpers');
const { expect } = require('chai');

const MockRegulator = contract.fromArtifact('MockRegulator');
const MockSettableOracle = contract.fromArtifact('MockSettableOracle');
const Dollar = contract.fromArtifact('Dollar');

const POOL_REWARD_PERCENT = 40;

function lessPoolIncentive(baseAmount, newAmount) {
  return new BN(baseAmount + newAmount - poolIncentive(newAmount));
}

function poolIncentive(newAmount) {
  return new BN(newAmount * POOL_REWARD_PERCENT / 100);
}

describe('Regulator', function () {
  const [ ownerAddress, userAddress, poolAddress, userAddress2, userAddress3,  userAddress4 ] = accounts;

  beforeEach(async function () {
    this.oracle = await MockSettableOracle.new({from: ownerAddress, gas: 8000000});
    this.regulator = await MockRegulator.new(this.oracle.address, poolAddress, {from: ownerAddress, gas: 8000000});
    this.dollar = await Dollar.at(await this.regulator.dollar());
  });

  describe('after bootstrapped', function () {
    beforeEach(async function () {
      await this.regulator.incrementEpochE(); // 1
      await this.regulator.incrementEpochE(); // 2
      await this.regulator.incrementEpochE(); // 3
      await this.regulator.incrementEpochE(); // 4
      await this.regulator.incrementEpochE(); // 5
    });

    describe('up regulation', function () {
      describe('above limit', function () {
        beforeEach(async function () {
          await this.regulator.incrementEpochE(); // 1
          await this.regulator.incrementEpochE(); // 2
          await this.regulator.incrementTotalBondedE(1000000);
          await this.regulator.mintToE(this.regulator.address, 1000000);
        });

        describe('on step', function () {
          beforeEach(async function () {
            await this.oracle.set(115, 100, true);
            this.expectedReward = 30000;

            this.result = await this.regulator.stepE();
            this.txHash = this.result.tx;
          });

          it('mints new Dollar tokens', async function () {
            expect(await this.dollar.totalSupply()).to.be.bignumber.equal(new BN(1000000).add(new BN(this.expectedReward)));
            expect(await this.dollar.balanceOf(this.regulator.address)).to.be.bignumber.equal(lessPoolIncentive(1000000, this.expectedReward));
            expect(await this.dollar.balanceOf(poolAddress)).to.be.bignumber.equal(poolIncentive(this.expectedReward));
            expect(await this.dollar.balanceOf(TREASURY_ADDRESS)).to.be.bignumber.equal(treasuryIncentive(this.expectedReward));
          });

          it('updates totals', async function () {
            expect(await this.regulator.totalStaged()).to.be.bignumber.equal(new BN(0));
            expect(await this.regulator.totalBonded()).to.be.bignumber.equal(lessPoolIncentive(1000000, this.expectedReward));
            expect(await this.regulator.totalDebt()).to.be.bignumber.equal(new BN(0));
            expect(await this.regulator.totalSupply()).to.be.bignumber.equal(new BN(0));
            expect(await this.regulator.totalCoupons()).to.be.bignumber.equal(new BN(0));
            expect(await this.regulator.totalRedeemable()).to.be.bignumber.equal(new BN(0));
          });
          it('has not created any auction in the past 7 epochs', async function () {
            for(var a_idx = 1; a_idx<8; a_idx++){
              expect(await this.regulator.isCouponAuctionInitAtEpochE.call(a_idx)).equal(false);
            }
          });

          it('emits SupplyIncrease event', async function () {
            const event = await expectEvent.inTransaction(this.txHash, MockRegulator, 'SupplyIncrease', {});

            expect(event.args.epoch).to.be.bignumber.equal(new BN(7));
            expect(event.args.price).to.be.bignumber.equal(new BN(115).mul(new BN(10).pow(new BN(16))));
            expect(event.args.newRedeemable).to.be.bignumber.equal(new BN(0));
            expect(event.args.lessDebt).to.be.bignumber.equal(new BN(0));
            expect(event.args.newBonded).to.be.bignumber.equal(new BN(this.expectedReward));
          });
        });
      });

      describe('(2) - only to bonded', function () {
        beforeEach(async function () {
          await this.regulator.incrementEpochE(); // 1
          await this.regulator.incrementEpochE(); // 2
          await this.regulator.incrementTotalBondedE(1000000);
          await this.regulator.mintToE(this.regulator.address, 1000000);
        });

        describe('on step', function () {
          beforeEach(async function () {
            await this.oracle.set(101, 100, true);
            this.expectedReward = 10000;

            this.result = await this.regulator.stepE();
            this.txHash = this.result.tx;
          });

          it('mints new Dollar tokens', async function () {
            expect(await this.dollar.totalSupply()).to.be.bignumber.equal(new BN(1000000).add(new BN(this.expectedReward)));
            expect(await this.dollar.balanceOf(this.regulator.address)).to.be.bignumber.equal(lessPoolIncentive(1000000, this.expectedReward));
            expect(await this.dollar.balanceOf(poolAddress)).to.be.bignumber.equal(poolIncentive(this.expectedReward));
            expect(await this.dollar.balanceOf(TREASURY_ADDRESS)).to.be.bignumber.equal(treasuryIncentive(this.expectedReward));

          });

          it('updates totals', async function () {
            expect(await this.regulator.totalStaged()).to.be.bignumber.equal(new BN(0));
            expect(await this.regulator.totalBonded()).to.be.bignumber.equal(lessPoolIncentive(1000000, this.expectedReward));
            expect(await this.regulator.totalDebt()).to.be.bignumber.equal(new BN(0));
            expect(await this.regulator.totalSupply()).to.be.bignumber.equal(new BN(0));
            expect(await this.regulator.totalCoupons()).to.be.bignumber.equal(new BN(0));
            expect(await this.regulator.totalRedeemable()).to.be.bignumber.equal(new BN(0));
          });

          it('has not created any auction in the past 7 epochs', async function () {
            for(var a_idx = 1; a_idx<8; a_idx++){
              expect(await this.regulator.isCouponAuctionInitAtEpochE.call(a_idx)).equal(false);
            }
          });

          it('emits SupplyIncrease event', async function () {
            const event = await expectEvent.inTransaction(this.txHash, MockRegulator, 'SupplyIncrease', {});

            expect(event.args.epoch).to.be.bignumber.equal(new BN(7));
            expect(event.args.price).to.be.bignumber.equal(new BN(101).mul(new BN(10).pow(new BN(16))));
            expect(event.args.newRedeemable).to.be.bignumber.equal(new BN(0));
            expect(event.args.lessDebt).to.be.bignumber.equal(new BN(0));
            expect(event.args.newBonded).to.be.bignumber.equal(new BN(this.expectedReward));
          });
        });
      });

      describe('(1) - refresh redeemable at specified ratio', function () {
        beforeEach(async function () {
          await this.regulator.incrementEpochE(); // 1

          await this.regulator.incrementTotalBondedE(1000000);
          await this.regulator.mintToE(this.regulator.address, 1000000);

          await this.regulator.increaseDebtE(new BN(2000));
          await this.regulator.incrementBalanceOfCouponsE(userAddress, 1, new BN(100000));

          await this.regulator.incrementEpochE(); // 2
        });

        describe('on step', function () {
          beforeEach(async function () {
            await this.oracle.set(101, 100, true);
            this.expectedReward = 10000;
            this.expectedRewardCoupons = 8000;
            this.expectedRewardDAO = 0;
            this.expectedRewardLP = 2000;

            this.result = await this.regulator.stepE();
            this.txHash = this.result.tx;
          });

          it('mints new Dollar tokens', async function () {
            expect(await this.dollar.totalSupply()).to.be.bignumber.equal(new BN(1000000).add(new BN(this.expectedReward)));
            expect(await this.dollar.balanceOf(this.regulator.address)).to.be.bignumber.equal(new BN(1000000).add(new BN(this.expectedReward - this.expectedRewardLP)));
            expect(await this.dollar.balanceOf(poolAddress)).to.be.bignumber.equal(new BN(this.expectedRewardLP));
            expect(await this.dollar.balanceOf(LEGACY_POOL_ADDRESS)).to.be.bignumber.equal(new BN(0));
          });

          it('updates totals', async function () {
            expect(await this.regulator.totalStaged()).to.be.bignumber.equal(new BN(0));
            expect(await this.regulator.totalBonded()).to.be.bignumber.equal(new BN(1000000).add(new BN(this.expectedRewardDAO)));
            expect(await this.regulator.totalDebt()).to.be.bignumber.equal(new BN(0));
            expect(await this.regulator.totalSupply()).to.be.bignumber.equal(new BN(0));
            expect(await this.regulator.totalCoupons()).to.be.bignumber.equal(new BN(100000));
            expect(await this.regulator.totalRedeemable()).to.be.bignumber.equal(new BN(this.expectedRewardCoupons));
          });

          it('has not created any auction in the past 7 epochs', async function () {
            for(var a_idx = 1; a_idx<8; a_idx++){
              expect(await this.regulator.isCouponAuctionInitAtEpochE.call(a_idx)).equal(false);
            }
          });

          it('emits SupplyIncrease event', async function () {
            const event = await expectEvent.inTransaction(this.txHash, MockRegulator, 'SupplyIncrease', {});

            expect(event.args.epoch).to.be.bignumber.equal(new BN(7));
            expect(event.args.price).to.be.bignumber.equal(new BN(101).mul(new BN(10).pow(new BN(16))));
            expect(event.args.newRedeemable).to.be.bignumber.equal(new BN(this.expectedRewardCoupons));
            expect(event.args.lessDebt).to.be.bignumber.equal(new BN(0));
            expect(event.args.newBonded).to.be.bignumber.equal(new BN(this.expectedRewardLP + this.expectedRewardDAO));
          });
        });
      });
    });

    describe('(1 + 2) - refresh redeemable then mint to bonded', function () {
      beforeEach(async function () {
        await this.regulator.incrementEpochE(); // 1

        await this.regulator.incrementTotalBondedE(1000000);
        await this.regulator.mintToE(this.regulator.address, 1000000);

        await this.regulator.increaseDebtE(new BN(2000));
        await this.regulator.incrementBalanceOfCouponsE(userAddress, 1, new BN(2000));

        await this.regulator.incrementEpochE(); // 2

      });

      describe('on step', function () {
        beforeEach(async function () {
          await this.oracle.set(101, 100, true);
          this.expectedReward = 10000;
          this.poolReward = 400;

          this.result = await this.regulator.stepE();
          this.txHash = this.result.tx;
        });

        it('mints new Dollar tokens', async function () {
          expect(await this.dollar.totalSupply()).to.be.bignumber.equal(new BN(1000000).add(new BN(this.expectedReward)));
          expect(await this.dollar.balanceOf(this.regulator.address)).to.be.bignumber.equal(lessPoolIncentive(1002000, this.expectedReward - 2000).sub(new BN(this.poolReward)));
          expect(await this.dollar.balanceOf(poolAddress)).to.be.bignumber.equal(new BN(this.poolReward).add(poolIncentive(this.expectedReward - 2000)));
        });

        it('updates totals', async function () {
          expect(await this.regulator.totalStaged()).to.be.bignumber.equal(new BN(0));
          expect(await this.regulator.totalBonded()).to.be.bignumber.equal(lessPoolIncentive(1000000, this.expectedReward - 2000).sub(new BN(this.poolReward)));
          expect(await this.regulator.totalDebt()).to.be.bignumber.equal(new BN(0));
          expect(await this.regulator.totalSupply()).to.be.bignumber.equal(new BN(0));
          expect(await this.regulator.totalCoupons()).to.be.bignumber.equal(new BN(2000));
          expect(await this.regulator.totalRedeemable()).to.be.bignumber.equal(new BN(2000));
        });

        it('has not created any auction in the past 7 epochs', async function () {
            for(var a_idx = 1; a_idx<8; a_idx++){
              expect(await this.regulator.isCouponAuctionInitAtEpochE.call(a_idx)).equal(false);
            }
          });

        it('emits SupplyIncrease event', async function () {
          const event = await expectEvent.inTransaction(this.txHash, MockRegulator, 'SupplyIncrease', {});

          expect(event.args.epoch).to.be.bignumber.equal(new BN(7));
          expect(event.args.price).to.be.bignumber.equal(new BN(101).mul(new BN(10).pow(new BN(16))));
          expect(event.args.newRedeemable).to.be.bignumber.equal(new BN(2000));
          expect(event.args.lessDebt).to.be.bignumber.equal(new BN(0));
          expect(event.args.newBonded).to.be.bignumber.equal(new BN(this.expectedReward - 2000));
        });
      });
    });

    describe('(3) - above limit but below coupon limit', function () {
        beforeEach(async function () {
          await this.regulator.incrementEpochE(); // 1

          await this.regulator.incrementTotalBondedE(1000000);
          await this.regulator.mintToE(this.regulator.address, 1000000);

          await this.regulator.increaseDebtE(new BN(2000));
          await this.regulator.incrementBalanceOfCouponsE(userAddress, 1, new BN(100000));

          await this.regulator.incrementEpochE(); // 2
        });

        describe('on step', function () {
          beforeEach(async function () {
            await this.oracle.set(105, 100, true);
            this.expectedReward = 50000;
            this.expectedRewardCoupons = 40000;
            this.expectedRewardDAO = 0;
            this.expectedRewardLP = 10000;

            this.result = await this.regulator.stepE();
            this.txHash = this.result.tx;
          });

          it('mints new Dollar tokens', async function () {
            expect(await this.dollar.totalSupply()).to.be.bignumber.equal(new BN(1000000).add(new BN(this.expectedReward)));
            expect(await this.dollar.balanceOf(this.regulator.address)).to.be.bignumber.equal(new BN(1000000).add(new BN(this.expectedReward - this.expectedRewardLP)));
            expect(await this.dollar.balanceOf(poolAddress)).to.be.bignumber.equal(new BN(this.expectedRewardLP));
            expect(await this.dollar.balanceOf(LEGACY_POOL_ADDRESS)).to.be.bignumber.equal(new BN(0));
          });

          it('updates totals', async function () {
            expect(await this.regulator.totalStaged()).to.be.bignumber.equal(new BN(0));
            expect(await this.regulator.totalBonded()).to.be.bignumber.equal(new BN(1000000).add(new BN(this.expectedRewardDAO)));
            expect(await this.regulator.totalDebt()).to.be.bignumber.equal(new BN(0));
            expect(await this.regulator.totalSupply()).to.be.bignumber.equal(new BN(0));
            expect(await this.regulator.totalCoupons()).to.be.bignumber.equal(new BN(100000));
            expect(await this.regulator.totalRedeemable()).to.be.bignumber.equal(new BN(this.expectedRewardCoupons));
          });

          it('has not created any auction in the past 7 epochs', async function () {
            for(var a_idx = 1; a_idx<8; a_idx++){
              expect(await this.regulator.isCouponAuctionInitAtEpochE.call(a_idx)).equal(false);
            }
          });

          it('emits SupplyIncrease event', async function () {
            const event = await expectEvent.inTransaction(this.txHash, MockRegulator, 'SupplyIncrease', {});

            expect(event.args.epoch).to.be.bignumber.equal(new BN(7));
            expect(event.args.price).to.be.bignumber.equal(new BN(105).mul(new BN(10).pow(new BN(16))));
            expect(event.args.newRedeemable).to.be.bignumber.equal(new BN(this.expectedRewardCoupons));
            expect(event.args.lessDebt).to.be.bignumber.equal(new BN(0));
            expect(event.args.newBonded).to.be.bignumber.equal(new BN(this.expectedRewardLP + this.expectedRewardDAO));
          });
        });
    });

    describe('down regulation', function () {
      describe('under limit', function () {
        beforeEach(async function () {
          await this.regulator.incrementEpochE(); // 1
          await this.regulator.incrementEpochE(); // 2

          await this.regulator.incrementTotalBondedE(1000000);
          await this.regulator.mintToE(this.regulator.address, 1000000);

          await this.regulator.incrementEpochE(); // 3
        });

        describe('on step', function () {
          beforeEach(async function () {
            await this.oracle.set(85, 100, true);
            this.expectedDebt = 30000;

            this.result = await this.regulator.stepE();
            this.txHash = this.result.tx;
          });

          it('doesnt mint new Dollar tokens', async function () {
            expect(await this.dollar.totalSupply()).to.be.bignumber.equal(new BN(1000000));
            expect(await this.dollar.balanceOf(this.regulator.address)).to.be.bignumber.equal(new BN(1000000));
            expect(await this.dollar.balanceOf(poolAddress)).to.be.bignumber.equal(new BN(0));

          it('has created 1 auction in the past 8 epochs', async function () {
            for(var a_idx = 1; a_idx<8; a_idx++){
              expect(await this.regulator.isCouponAuctionInitAtEpochE.call(a_idx)).equal(false);
            }
            expect(await this.regulator.isCouponAuctionInitAtEpochE.call(8)).equal(true);
          });

          it('updates totals', async function () {
            expect(await this.regulator.totalStaged()).to.be.bignumber.equal(new BN(0));
            expect(await this.regulator.totalBonded()).to.be.bignumber.equal(new BN(1000000));
            expect(await this.regulator.totalDebt()).to.be.bignumber.equal(new BN(this.expectedDebt));
            expect(await this.regulator.totalSupply()).to.be.bignumber.equal(new BN(0));
            expect(await this.regulator.totalCoupons()).to.be.bignumber.equal(new BN(0));
            expect(await this.regulator.totalRedeemable()).to.be.bignumber.equal(new BN(0));
          });

          it('emits SupplyDecrease event', async function () {
            const event = await expectEvent.inTransaction(this.txHash, MockRegulator, 'SupplyDecrease', {});

            expect(event.args.epoch).to.be.bignumber.equal(new BN(8));
            expect(event.args.price).to.be.bignumber.equal(new BN(85).mul(new BN(10).pow(new BN(16))));
            expect(event.args.newDebt).to.be.bignumber.equal(new BN(this.expectedDebt));
          });
        });
      });

      describe('without debt', function () {
        beforeEach(async function () {
          await this.regulator.incrementEpochE(); // 1

          await this.regulator.incrementTotalBondedE(1000000);
          await this.regulator.mintToE(this.regulator.address, 1000000);

          await this.regulator.incrementEpochE(); // 2

        });

        describe('on step', function () {
          beforeEach(async function () {
            await this.oracle.set(99, 100, true);
            this.expectedDebt = 10000

            this.result = await this.regulator.stepE();
            this.txHash = this.result.tx;
          });

          it('doesnt mint new Dollar tokens', async function () {
            expect(await this.dollar.totalSupply()).to.be.bignumber.equal(new BN(1000000));
            expect(await this.dollar.balanceOf(this.regulator.address)).to.be.bignumber.equal(new BN(1000000));
            expect(await this.dollar.balanceOf(poolAddress)).to.be.bignumber.equal(new BN(0));
          });

          it('updates totals', async function () {
            expect(await this.regulator.totalStaged()).to.be.bignumber.equal(new BN(0));
            expect(await this.regulator.totalBonded()).to.be.bignumber.equal(new BN(1000000));
            expect(await this.regulator.totalDebt()).to.be.bignumber.equal(new BN(this.expectedDebt));
            expect(await this.regulator.totalSupply()).to.be.bignumber.equal(new BN(0));
            expect(await this.regulator.totalCoupons()).to.be.bignumber.equal(new BN(0));
            expect(await this.regulator.totalRedeemable()).to.be.bignumber.equal(new BN(0));
          });

          it('has created 1 auction in the past 7 epochs', async function () {
            for(var a_idx = 1; a_idx<7; a_idx++){
              expect(await this.regulator.isCouponAuctionInitAtEpochE.call(a_idx)).equal(false);
            }
            expect(await this.regulator.isCouponAuctionInitAtEpochE.call(7)).equal(true);
          });

          it('emits SupplyDecrease event', async function () {
            const event = await expectEvent.inTransaction(this.txHash, MockRegulator, 'SupplyDecrease', {});

            expect(event.args.epoch).to.be.bignumber.equal(new BN(7));
            expect(event.args.price).to.be.bignumber.equal(new BN(99).mul(new BN(10).pow(new BN(16))));
            expect(event.args.newDebt).to.be.bignumber.equal(new BN(this.expectedDebt));
          });
        });
      });

      describe('with debt', function () {
        beforeEach(async function () {
          await this.regulator.incrementEpochE(); // 1

          await this.regulator.incrementTotalBondedE(1000000);
          await this.regulator.mintToE(this.regulator.address, 1000000);

          await this.regulator.increaseDebtE(new BN(100000));

          await this.regulator.incrementEpochE(); // 2
        });

        describe('on step', function () {
          beforeEach(async function () {
            await this.oracle.set(99, 100, true);
            this.expectedDebt = 9000;

            this.result = await this.regulator.stepE();
            this.txHash = this.result.tx;
          });

          it('doesnt mint new Dollar tokens', async function () {
            expect(await this.dollar.totalSupply()).to.be.bignumber.equal(new BN(1000000));
            expect(await this.dollar.balanceOf(this.regulator.address)).to.be.bignumber.equal(new BN(1000000));
            expect(await this.dollar.balanceOf(poolAddress)).to.be.bignumber.equal(new BN(0));
          });

          it('updates totals', async function () {
            it('updates totals', async function () {
              expect(await this.regulator.totalStaged()).to.be.bignumber.equal(new BN(0));
              expect(await this.regulator.totalBonded()).to.be.bignumber.equal(new BN(1000000));
              expect(await this.regulator.totalDebt()).to.be.bignumber.equal(new BN(100000).add(new BN(this.expectedDebt)));
              expect(await this.regulator.totalSupply()).to.be.bignumber.equal(new BN(0));
              expect(await this.regulator.totalCoupons()).to.be.bignumber.equal(new BN(0));
              expect(await this.regulator.totalRedeemable()).to.be.bignumber.equal(new BN(0));
            });
          });

          it('has created 1 auction in the past 7 epochs', async function () {
            for(var a_idx = 1; a_idx<7; a_idx++){
              expect(await this.regulator.isCouponAuctionInitAtEpochE.call(a_idx)).equal(false);
            }
            expect(await this.regulator.isCouponAuctionInitAtEpochE.call(7)).equal(true);
          });

          it('emits SupplyDecrease event', async function () {
            const event = await expectEvent.inTransaction(this.txHash, MockRegulator, 'SupplyDecrease', {});

            expect(event.args.epoch).to.be.bignumber.equal(new BN(7));
            expect(event.args.price).to.be.bignumber.equal(new BN(99).mul(new BN(10).pow(new BN(16))));
            expect(event.args.newDebt).to.be.bignumber.equal(new BN(this.expectedDebt));
          });
        });
      });

      describe('with debt over default but under coupon limit', function () {
        beforeEach(async function () {
          await this.regulator.incrementEpochE(); // 1

          await this.regulator.incrementTotalBondedE(1000000);
          await this.regulator.mintToE(this.regulator.address, 1000000);

          await this.regulator.increaseDebtE(new BN(100000));

          await this.regulator.incrementEpochE(); // 2
        });

        describe('on step', function () {
          beforeEach(async function () {
            await this.oracle.set(95, 100, true);
            this.expectedDebt = 27000; // 3% not 5%

            this.result = await this.regulator.stepE();
            this.txHash = this.result.tx;
          });

          describe('when settling auction', function () {
            describe('auction is not finished and not canceled', function () {
              beforeEach(async function () {
                await this.regulator.mintToE(userAddress, 1000000);
                await this.regulator.mintToE(userAddress2, 1000000);
                await this.regulator.mintToE(userAddress3, 1000000);
                await this.regulator.mintToE(userAddress4, 1000000);
                await this.dollar.approve(this.regulator.address, 1000000, {from: userAddress});
                await this.dollar.approve(this.regulator.address, 1000000, {from: userAddress2});
                await this.dollar.approve(this.regulator.address, 1000000, {from: userAddress3});
                await this.dollar.approve(this.regulator.address, 1000000, {from: userAddress4});
              });

              it('is able to settle auction and generated internals', async function () {
                // add some bidders
                this.result = await this.regulator.placeCouponAuctionBid(20, 1000, 50000, {from: userAddress});
                this.result1 = await this.regulator.placeCouponAuctionBid(5, 2000, 50000, {from: userAddress2});
                //thise bidders will be rejected
                this.result2 = await this.regulator.placeCouponAuctionBid(1000, 900, 50000, {from: userAddress3});
                this.result3 = await this.regulator.placeCouponAuctionBid(100990, 900, 50000, {from: userAddress4});
                this.auction_settlement = await this.regulator.settleCouponAuctionE();
                

                expect(await this.regulator.getCouponAuctionBidsE.call()).to.be.bignumber.equal(new BN(4));
                expect(await this.regulator.getCouponAuctionMinExpiryE.call()).to.be.bignumber.equal(new BN(12));
                expect(await this.regulator.getCouponAuctionMaxExpiryE.call()).to.be.bignumber.equal(new BN(100997));
                expect(await this.regulator.getCouponAuctionMinYieldE.call()).to.be.bignumber.equal(new BN(25));
                expect(await this.regulator.getCouponAuctionMaxYieldE.call()).to.be.bignumber.equal(new BN(55));
                expect(await this.regulator.getCouponAuctionMinDollarAmountE.call()).to.be.bignumber.equal(new BN(900));
                expect(await this.regulator.getCouponAuctionMaxDollarAmountE.call()).to.be.bignumber.equal(new BN(2000));

                expect(await this.regulator.getMinExpiryFilled(7)).to.be.bignumber.equal(new BN(12));
                expect(await this.regulator.getMaxExpiryFilled(7)).to.be.bignumber.equal(new BN(100997));
                expect(await this.regulator.getAvgExpiryFilled(7)).to.be.bignumber.equal(new BN(25510));
                expect(await this.regulator.getMinYieldFilled(7)).to.be.bignumber.equal(new BN(25));
                expect(await this.regulator.getMaxYieldFilled(7)).to.be.bignumber.equal(new BN(55));
                expect(await this.regulator.getAvgYieldFilled(7)).to.be.bignumber.equal(new BN(46));
                expect(await this.regulator.getBidToCover(7)).to.be.bignumber.equal(new BN(100));
                expect(await this.regulator.getTotalFilled(7)).to.be.bignumber.equal(new BN(4));
              });
            });

            describe('auction is finished', function () {
              beforeEach(async function () {
                //finish the auction
                await this.regulator.finishCouponAuctionAtEpochE(1);
              });

              it('is able to not settle auction', async function () {
                // add some bidders
                this.result = await this.regulator.placeCouponAuctionBid(20, 1000, 50000, {from: userAddress});
                this.result1 = await this.regulator.placeCouponAuctionBid(5, 2000, 50000, {from: userAddress2});
                this.auction_settlement = await this.regulator.settleCouponAuctionE.call();
                expect(this.auction_settlement).to.be.equal(false);
              });


            });
            describe('auction is canceled', function () {
              beforeEach(async function () {
                //finish the auction
                await this.regulator.cancelCouponAuctionAtEpochE(7);
              });

              it('is able to not settle auction', async function () {
                // add some bidders
                this.result = await this.regulator.placeCouponAuctionBid(20, 1000, 50000, {from: userAddress});
                this.result1 = await this.regulator.placeCouponAuctionBid(5, 2000, 50000, {from: userAddress2});
                this.auction_settlement = await this.regulator.settleCouponAuctionE.call();
                expect(this.auction_settlement).to.be.equal(false);
              });

            });
          });

          describe('when calling init again during auction', function () {
            describe('auction is not finished and not canceled', function () {
              beforeEach(async function () {
                await this.regulator.mintToE(userAddress, 1000000);
                await this.regulator.mintToE(userAddress2, 1000000);
                await this.regulator.mintToE(userAddress3, 1000000);
                await this.regulator.mintToE(userAddress4, 1000000);
                await this.dollar.approve(this.regulator.address, 1000000, {from: userAddress});
                await this.dollar.approve(this.regulator.address, 1000000, {from: userAddress2});
                await this.dollar.approve(this.regulator.address, 1000000, {from: userAddress3});
                await this.dollar.approve(this.regulator.address, 1000000, {from: userAddress4});
              });

              it('is able to settle auction and generated internals without resetting them', async function () {
                // add some bidders
                this.result = await this.regulator.placeCouponAuctionBid(20, 1000, 50000, {from: userAddress});
                this.result1 = await this.regulator.placeCouponAuctionBid(5, 2000, 50000, {from: userAddress2});
                //thise bidders will be rejected
                this.result2 = await this.regulator.placeCouponAuctionBid(1000, 900, 50000, {from: userAddress3});
                this.result3 = await this.regulator.placeCouponAuctionBid(100990, 900, 50000, {from: userAddress4});
                this.auction_settlement = await this.regulator.settleCouponAuctionE();
                
                await this.regulator.initCouponAuctionE.call();

                expect(await this.regulator.getCouponAuctionBidsE.call()).to.be.bignumber.equal(new BN(4));
                expect(await this.regulator.getCouponAuctionMinExpiryE.call()).to.be.bignumber.equal(new BN(12));
                expect(await this.regulator.getCouponAuctionMaxExpiryE.call()).to.be.bignumber.equal(new BN(100997));
                expect(await this.regulator.getCouponAuctionMinYieldE.call()).to.be.bignumber.equal(new BN(25));
                expect(await this.regulator.getCouponAuctionMaxYieldE.call()).to.be.bignumber.equal(new BN(55));
                expect(await this.regulator.getCouponAuctionMinDollarAmountE.call()).to.be.bignumber.equal(new BN(900));
                expect(await this.regulator.getCouponAuctionMaxDollarAmountE.call()).to.be.bignumber.equal(new BN(2000));

                expect(await this.regulator.getMinExpiryFilled(7)).to.be.bignumber.equal(new BN(12));
                expect(await this.regulator.getMaxExpiryFilled(7)).to.be.bignumber.equal(new BN(100997));
                expect(await this.regulator.getAvgExpiryFilled(7)).to.be.bignumber.equal(new BN(25510));
                expect(await this.regulator.getMinYieldFilled(7)).to.be.bignumber.equal(new BN(25));
                expect(await this.regulator.getMaxYieldFilled(7)).to.be.bignumber.equal(new BN(55));
                expect(await this.regulator.getAvgYieldFilled(7)).to.be.bignumber.equal(new BN(46));
                expect(await this.regulator.getBidToCover(7)).to.be.bignumber.equal(new BN(100));
                expect(await this.regulator.getTotalFilled(7)).to.be.bignumber.equal(new BN(4));
              });
            });
          });

          it('doesnt mint new Dollar tokens', async function () {
            expect(await this.dollar.totalSupply()).to.be.bignumber.equal(new BN(1000000));
            expect(await this.dollar.balanceOf(this.regulator.address)).to.be.bignumber.equal(new BN(1000000));
            expect(await this.dollar.balanceOf(poolAddress)).to.be.bignumber.equal(new BN(0));
            expect(await this.dollar.balanceOf(LEGACY_POOL_ADDRESS)).to.be.bignumber.equal(new BN(0));
          });

          it('updates totals', async function () {
            it('updates totals', async function () {
              expect(await this.regulator.totalStaged()).to.be.bignumber.equal(new BN(0));
              expect(await this.regulator.totalBonded()).to.be.bignumber.equal(new BN(1000000));
              expect(await this.regulator.totalDebt()).to.be.bignumber.equal(new BN(100000).add(new BN(this.expectedDebt)));
              expect(await this.regulator.totalSupply()).to.be.bignumber.equal(new BN(0));
              expect(await this.regulator.totalCoupons()).to.be.bignumber.equal(new BN(0));
              expect(await this.regulator.totalRedeemable()).to.be.bignumber.equal(new BN(0));
            });
          });

          it('has created 1 auction in the past 7 epochs', async function () {
            for(var a_idx = 1; a_idx<7; a_idx++){
              expect(await this.regulator.isCouponAuctionInitAtEpochE.call(a_idx)).equal(false);
            }
            expect(await this.regulator.isCouponAuctionInitAtEpochE.call(7)).equal(true);
          });

          it('emits SupplyDecrease event', async function () {
            const event = await expectEvent.inTransaction(this.txHash, MockRegulator, 'SupplyDecrease', {});

            expect(event.args.epoch).to.be.bignumber.equal(new BN(7));
            expect(event.args.price).to.be.bignumber.equal(new BN(95).mul(new BN(10).pow(new BN(16))));
            expect(event.args.newDebt).to.be.bignumber.equal(new BN(this.expectedDebt));
          });
        });
      });
    });

    describe('neutral regulation', function () {
      beforeEach(async function () {
        await this.regulator.incrementEpochE(); // 1

        await this.regulator.incrementTotalBondedE(1000000);
        await this.regulator.mintToE(this.regulator.address, 1000000);

        await this.regulator.incrementEpochE(); // 2

      });

      describe('on step', function () {
        beforeEach(async function () {
          await this.oracle.set(100, 100, true);
          this.result = await this.regulator.stepE();
          this.txHash = this.result.tx;
        });

        it('doesnt mint new Dollar tokens', async function () {
          expect(await this.dollar.totalSupply()).to.be.bignumber.equal(new BN(1000000));
          expect(await this.dollar.balanceOf(this.regulator.address)).to.be.bignumber.equal(new BN(1000000));
          expect(await this.dollar.balanceOf(poolAddress)).to.be.bignumber.equal(new BN(0));
        });

        it('updates totals', async function () {
          expect(await this.regulator.totalStaged()).to.be.bignumber.equal(new BN(0));
          expect(await this.regulator.totalBonded()).to.be.bignumber.equal(new BN(1000000));
          expect(await this.regulator.totalDebt()).to.be.bignumber.equal(new BN(0));
          expect(await this.regulator.totalSupply()).to.be.bignumber.equal(new BN(0));
          expect(await this.regulator.totalCoupons()).to.be.bignumber.equal(new BN(0));
          expect(await this.regulator.totalRedeemable()).to.be.bignumber.equal(new BN(0));
        });

        it('emits SupplyNeutral event', async function () {
          const event = await expectEvent.inTransaction(this.txHash, MockRegulator, 'SupplyNeutral', {});

          expect(event.args.epoch).to.be.bignumber.equal(new BN(7));
        });
      });
    });

    describe('not valid', function () {
      beforeEach(async function () {
        await this.regulator.incrementEpochE(); // 1

        await this.regulator.incrementTotalBondedE(1000000);
        await this.regulator.mintToE(this.regulator.address, 1000000);

        await this.regulator.incrementEpochE(); // 2

      });

      describe('on step', function () {
        beforeEach(async function () {
          await this.oracle.set(105, 100, false);
          this.result = await this.regulator.stepE();
          this.txHash = this.result.tx;
        });

        it('doesnt mint new Dollar tokens', async function () {
          expect(await this.dollar.totalSupply()).to.be.bignumber.equal(new BN(1000000));
          expect(await this.dollar.balanceOf(this.regulator.address)).to.be.bignumber.equal(new BN(1000000));
          expect(await this.dollar.balanceOf(poolAddress)).to.be.bignumber.equal(new BN(0));
        });

        it('updates totals', async function () {
          expect(await this.regulator.totalStaged()).to.be.bignumber.equal(new BN(0));
          expect(await this.regulator.totalBonded()).to.be.bignumber.equal(new BN(1000000));
          expect(await this.regulator.totalDebt()).to.be.bignumber.equal(new BN(0));
          expect(await this.regulator.totalSupply()).to.be.bignumber.equal(new BN(0));
          expect(await this.regulator.totalCoupons()).to.be.bignumber.equal(new BN(0));
          expect(await this.regulator.totalRedeemable()).to.be.bignumber.equal(new BN(0));
        });

        it('emits SupplyNeutral event', async function () {
          const event = await expectEvent.inTransaction(this.txHash, MockRegulator, 'SupplyNeutral', {});

          expect(event.args.epoch).to.be.bignumber.equal(new BN(7));
        });
      });
    });
  });
});