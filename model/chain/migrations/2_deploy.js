const Deployer1 = artifacts.require("Deployer1");
const Deployer2 = artifacts.require("Deployer2");
const Deployer3 = artifacts.require("Deployer3");
const MockOracle = artifacts.require("MockOracle");
const Pool = artifacts.require("Pool");
const Constants = artifacts.require("Constants");
const Implementation = artifacts.require("Implementation");
const Root = artifacts.require("Root");
const TestnetUSDT = artifacts.require("TestnetUSDT");

const PangolinFactoryBytecode = require('@pangolindex/exchange-contracts/artifacts/contracts/pangolin-core/PangolinFactory.sol/PangolinFactory.json').bytecode
const PangolinRouter02Bytecode = require('@pangolindex/exchange-contracts/artifacts/contracts/pangolin-periphery/PangolinRouter.sol/PangolinRouter.json').bytecode;
const WAVAXBytecode = require('@pangolindex/exchange-contracts/artifacts/contracts/WAVAX.sol/WAVAX.json').bytecode;


async function deployTestnetUSDT(deployer) {
  return await deployer.deploy(TestnetUSDT);
}

async function deployTestnet(deployer, network, accounts) {
  console.log('Deploy fake USDT');
  const usdt = await deployTestnetUSDT(deployer);

  console.log('USDT is at: ' + usdt.address);

  console.log('Deploy Deployer1');
  const d1 = await deployer.deploy(Deployer1);
  console.log('Deploy Root');
  const root = await deployer.deploy(Root, d1.address);

  console.log('Deploy fake Pangolin Factory');
  // We need an address arg to the contract
  let pangolinArg = '';
  for (let i = 0; i < 32; i++) { pangolinArg += '00';}
  const pangolinFactoryAddress = (await web3.eth.sendTransaction({from: accounts[0], gas: 8000000, data: PangolinFactoryBytecode + pangolinArg})).contractAddress;

  console.log('Deploy fake wAVAX');
  const wAVAXAddress = (await web3.eth.sendTransaction({from: accounts[0], gas: 8000000, data: WAVAXBytecode})).contractAddress;

  console.log('Deploy fake Pangolin Router');
  console.log(pangolinFactoryAddress.substr(2));
  console.log(wAVAXAddress.substr(2));
  console.log(web3.eth.abi.encodeParameters(['address', 'address'],[pangolinFactoryAddress, wAVAXAddress]).slice(2));
  const PangolinRouterAddress = (await web3.eth.sendTransaction({
    from: accounts[0],
    gas: 8000000,
    data: PangolinRouter02Bytecode + web3.eth.abi.encodeParameters(['address', 'address'],[pangolinFactoryAddress, wAVAXAddress]).slice(2)
  })).contractAddress;

  console.log('PangolinRouter is at: ' + PangolinRouterAddress);

  console.log('View Root as Deployer1');
  await new Promise(r => setTimeout(r, 1000));
  const rootAsD1 = await Deployer1.at(root.address);
  
  console.log('Deploy Deployer2');
  const d2 = await deployer.deploy(Deployer2);
  console.log('Implement Deployer2');
  await rootAsD1.implement(d2.address);
  console.log('View root as Deployer2');
  await new Promise(r => setTimeout(r, 1000));
  const rootAsD2 = await Deployer2.at(rootAsD1.address);

  // Set up the fields of the oracle that we can't pass through a Deployer
  await new Promise(r => setTimeout(r, 1000));
  console.log('Setup Oracle');
  const oracleAddress = await rootAsD2.oracle.call();
  console.log('Oracle is at: ' + oracleAddress);
  const oracle = await MockOracle.at(oracleAddress);
  
  // Make the oracle make the pangolin pair on our custom factory
  await oracle.set(pangolinFactoryAddress, usdt.address);
  const pair = await oracle.pair.call();
  console.log('Pangolin pair is at: ' + pair);

  console.log('Deploy Deployer3');
  const d3 = await deployer.deploy(Deployer3);
  console.log('Implement Deployer3');
  await rootAsD2.implement(d3.address);
  console.log('View root as Deployer3');
  await new Promise(r => setTimeout(r, 1000));
  const rootAsD3 = await Deployer3.at(root.address);
  await new Promise(r => setTimeout(r, 1000));
  const pool = await Pool.at(await rootAsD3.pool.call());
  console.log('Pool is at: ' + pool.address);

  await deployer.deploy(Constants);
  await deployer.link(Constants, Implementation);

  console.log('Deploy current Implementation');
  const implementation = await deployer.deploy(Implementation);
  console.log('Implement current Implementation');
  await rootAsD3.implement(implementation.address);
}

module.exports = function(deployer, network, accounts) {
  deployer.then(async() => {
    await deployTestnet(deployer, network, accounts);
  })
};

