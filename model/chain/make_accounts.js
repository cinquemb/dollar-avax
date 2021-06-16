const Web3 = require('web3');
const provider = new Web3.providers.HttpProvider('http://127.0.0.1:9545/ext/bc/C/rpc');
const w3 = new Web3(provider);
const avalanche = require("avalanche");
const process = require("process");


//cchain.callMethod('avax.incrementTimeTx', {"time": 10000}).then((res) => console.log(res.data))
//cchain.callMethod('avax.issueBlock').then((res) => console.log(res.data))

let ava = new avalanche.Avalanche('127.0.0.1', 9545, 'http', 12345);
let xchain = ava.XChain();
let cchain = ava.CChain();
let pchain = ava.PChain();
let xKeychain = xchain.keyChain();
let cKeychain = cchain.keyChain();
let pk = avalanche.utils.PrivateKeyPrefix + avalanche.utils.DefaultLocalGenesisPrivateKey;
xKeychain.importKey(pk);
cKeychain.importKey(pk);
let xAddresses = xchain.keyChain().getAddresses();
let cAddresses = cchain.keyChain().getAddresses();
let xAddressStrings = xchain.keyChain().getAddressStrings();
let cAddressStrings = cchain.keyChain().getAddressStrings();
let bintools = avalanche.BinTools.getInstance();

console.log(avalanche.utils.PrivateKeyPrefix);
console.log(avalanche.utils.DefaultLocalGenesisPrivateKey);

const ONEAVAX = new avalanche.BN(1000000000);
let amount = ONEAVAX.mul(new avalanche.BN(1000000)); //seed all wallets with 1000k avax
let locktime = new avalanche.BN(0);
let threshold = 1;

let memo = bintools.stringToBuffer("AVM utility method buildExportTx to export ANT to the C-Chain from the X-Chain");

let cChainBlockchainIdStr = cchain.getBlockchainID();
let cChainBlockchainIdBuf = bintools.cb58Decode(cChainBlockchainIdStr);
let xChainBlockchainIdStr = xchain.getBlockchainID();
let xChainBlockchainIdBuf = bintools.cb58Decode(xChainBlockchainIdStr);

async function exportTxXtoC() {
	var timestamp = Date.now() / 1000 | 0;
	let asOf = new avalanche.BN(timestamp);

	let avaxAssetID = await xchain.getAVAXAssetID();
	getBalanceResponse = await xchain.getBalance(xAddressStrings[0], bintools.cb58Encode(avaxAssetID));
	let avmUTXOResponse = await xchain.getUTXOs(xAddressStrings);
	let utxoSet = avmUTXOResponse.utxos;
	let unsignedTx = await xchain.buildExportTx(utxoSet, amount, cChainBlockchainIdStr, cAddressStrings, xAddressStrings, xAddressStrings, memo, asOf, locktime, threshold, bintools.cb58Encode(avaxAssetID));
	let otx = unsignedTx.sign(xKeychain);
	let xtx_id = await xchain.issueTx(otx);

}

async function importTxXtoC(evmAddr) {
	let u = await cchain.getUTXOs(cAddressStrings, "X");
	let intxoSet = u.utxos;
	let intxo = intxoSet.getAllUTXOs();
	cHexAddress = evmAddr;
	let evmFee = 0;
	let importTx = await cchain.buildImportTx(
		intxoSet,
		cHexAddress,
		cAddressStrings,
		xChainBlockchainIdStr,
		cAddressStrings
	)
	let intx = importTx.sign(cKeychain);
	let ctx_id = await cchain.issueTx(intx);
	let avaxAssetID = await xchain.getAVAXAssetID();
}


async function seedTestAccounts(evmAddr) {
	// EXPORT TX FROM X-CHAIN INTO C-CHAIN
	try {
		await exportTxXtoC()
	} catch (e) {
	    console.log('Error occurred X->C', e);
	}
	
	await new Promise(r => setTimeout(r, 5000));

	// IMPORT TX INTO C-CHAIN FROM X-CHAIN
	try {
		await importTxXtoC(evmAddr);
	} catch (e) {
	    console.log('Error occurred C<-X', e);
	}
}

async function makeAccounts() {
  let maxAccounts = 1;
  for (var i=0; i<process.argv.length;i++) { 
    if (process.argv[i] == '--max-accounts')
  		maxAccounts = parseInt(process.argv[i+1]);
  }
  // create test accounts
  console.log('create test accounts:', maxAccounts);
  for (var i=0; i<maxAccounts;i++) { await w3.eth.personal.newAccount('');}
  var accounts = await w3.eth.personal.getAccounts();

  // create unlock accounts
  console.log('unlock test accounts', accounts);
  for (var i=0; i<accounts.length;i++) {await w3.eth.personal.unlockAccount(accounts[i], '',9099999999);}

  // seed accounts with avax from x-chain to c-chain
  console.log('seed accounts with avax from x-chain to c-chain');
  for (var i=0; i<accounts.length;i++) {await seedTestAccounts(accounts[i]);}
  await new Promise(r => setTimeout(r, 5000));

  // check balance of accounts
  console.log('check balance of accounts');
  for (var i=0; i<accounts.length;i++) {console.log(await w3.eth.getBalance(accounts[i]));}
}

makeAccounts();