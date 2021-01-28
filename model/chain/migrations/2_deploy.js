const Deployer1 = artifacts.require("Deployer1");
const Deployer2 = artifacts.require("Deployer2");
const Deployer3 = artifacts.require("Deployer3");
const MockOracle = artifacts.require("MockOracle");
const Pool = artifacts.require("Pool");
const Implementation = artifacts.require("Implementation");
const Root = artifacts.require("Root");
const TestnetUSDC = artifacts.require("TestnetUSDC");

const UniswapV2FactoryBytecode = require('@uniswap/v2-core/build/UniswapV2Factory.json').bytecode
const UniswapV2Router02Bytecode = require('@uniswap/v2-periphery/build/UniswapV2Router02.json').bytecode;
const WETH9Bytecode = require('@uniswap/v2-periphery/build/WETH9.json').bytecode;


async function deployTestnetUSDC(deployer) {
  return await deployer.deploy(TestnetUSDC);
}

async function deployTestnet(deployer, network, accounts) {
  console.log('Deploy fake USDC');
  const usdc = await deployTestnetUSDC(deployer);

  console.log('Deploy Deployer1');
  const d1 = await deployer.deploy(Deployer1);
  console.log('Deploy Root');
  const root = await deployer.deploy(Root, d1.address);
  console.log('View Root as Deployer1');
  const rootAsD1 = await Deployer1.at(root.address);

  console.log('Deploy fake Uniswap Factory');
  // We need an address arg to the contract
  let uniswapArg = '';
  for (let i = 0; i < 32; i++) {
    uniswapArg += '00';
  }
  const uniswapFactoryAddress = (await web3.eth.sendTransaction({from: accounts[0], gas: 8000000, data: UniswapV2FactoryBytecode + uniswapArg})).contractAddress;

  console.log('Deploy fake wETH');
  const wETHAddress = (await web3.eth.sendTransaction({from: accounts[0], gas: 8000000, data: WETH9Bytecode})).contractAddress;

  console.log('Deploy fake UniswapV2 Router');
  const uniswapRouterAddress = (await web3.eth.sendTransaction({
    from: accounts[0],
    gas: 8000000,
    data: UniswapV2Router02Bytecode
  })).contractAddress;

  /*
  const uniswapRouterInstance = new web3.eth.Contract(UniswapV2Router02.abi.stringify(), uniswapRouterAddress.contractAddress);
  const uV2 = await uniswapRouterInstance.deploy({
      data: UniswapV2Router02.bytecode,
      arguments: [uniswapFactoryAddress, wETHAddress]
  });*/

  console.log('UniswapV2Router is at: ' + uniswapRouterAddress);
  
  console.log('Deploy Deployer2');
  const d2 = await deployer.deploy(Deployer2);
  console.log('Implement Deployer2');
  await rootAsD1.implement(d2.address);
  console.log('View root as Deployer2');
  const rootAsD2 = await Deployer2.at(root.address);
  
  // Set up the fields of the oracle that we can't pass through a Deployer
  const oracleAddress = await rootAsD2.oracle.call();
  const oracle = await MockOracle.at(oracleAddress);
  console.log('Oracle is at: ' + oracleAddress);
  
  // Make the oracle make the Uniswap pair on our custom factory
  await oracle.set(uniswapFactoryAddress, usdc.address);
  const pair = await oracle.pair.call();
  console.log('Uniswap pair is at: ' + pair);

  console.log('Deploy Deployer3');
  const d3 = await deployer.deploy(Deployer3);
  console.log('Implement Deployer3');
  await rootAsD2.implement(d3.address);
  console.log('View root as Deployer3');
  const rootAsD3 = await Deployer3.at(root.address);

  const pool = await Pool.at(await rootAsD3.pool.call());
  console.log('Pool is at: ' + pool.address);

  console.log('Deploy current Implementation');
  const implementation = await deployer.deploy(Implementation);
  console.log('Implement current Implementation');
  await rootAsD3.implement(implementation.address);
}

module.exports = function(deployer, network, accounts) {
  deployer.then(async() => {
    console.log(deployer.network);
    switch (deployer.network) {
      case 'development':
        await deployTestnet(deployer, network, accounts);
        break;
      default:
        throw("Unsupported network");
    }
  })
};

