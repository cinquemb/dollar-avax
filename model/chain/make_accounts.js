const Web3 = require('web3');
const provider = new Web3.providers.HttpProvider('http://127.0.0.1:7545/ext/bc/C/rpc');
const w3 = new Web3(provider);
module.exports = async (callback) => {
  // perform actions
  for (var i=0; i<21;i++) { await w3.eth.personal.newAccount('');}
  var accounts = await w3.eth.personal.getAccounts();
  console.log(accounts);
  for (var i=0; i<accounts.length;i++) {await w3.eth.personal.unlockAccount(accounts[i],'',9099999999);}
}

/*


const Web3 = require('web3');
const provider = new Web3.providers.HttpProvider('http://127.0.0.1:7545/ext/bc/C/rpc');
const w3 = new Web3(provider);
const avalanche = require("avalanche");

let pk = "PrivateKey-ewoqjP7PxY4yr3iLTpLisriqt94hdyDFNgchSxGGztUrTXtNN";
let ava = new avalanche.Avalanche('127.0.0.1', 7545, 'http', 12345);
let xchain = ava.XChain();
let cchain = ava.CChain();
let xKeychain = xchain.keyChain();
let cKeychain = cchain.keyChain()
xKeychain.importKey(pk);
cKeychain.importKey(pk);
let xAddresses = xchain.keyChain().getAddresses();
let xAddressStrings = xchain.keyChain().getAddressStrings();
let cAddressStrings = cchain.keyChain().getAddressStrings();
let avaxAssetID = await xchain.getAVAXAssetID();
let bintools = avalanche.BinTools.getInstance();
let xBalance = await xchain.getBalance(xAddressStrings[0], bintools.cb58Encode(avaxAssetID));

let cChainBlockchainID = cchain.getBlockchainID();
let amount = new avalanche.BN(10);


// EXPORT TX FROM X-CHAIN INTO C-CHAIN

let avmUTXOResponse = await xchain.getUTXOs(xAddressStrings);
let assetID = "2hrWPkPoNJRgtx24jimCfgiyzAf5DpG2hEBUpVfW8tT76RsRHh";
let threshold = 1;
let locktime = new avalanche.BN(0);
let memo = bintools.stringToBuffer("AVM utility method buildExportTx to export ANT to the C-Chain from the X-Chain");
let asOf = new avalanche.BN(1615401707);

let utxoSet = avmUTXOResponse.utxos;
let unsignedTx = await xchain.buildExportTx(utxoSet, amount, cChainBlockchainID, cAddressStrings, xAddressStrings, xAddressStrings, memo, asOf, locktime, threshold, bintools.cb58Encode(avaxAssetID));
let tx = unsignedTx.sign(xKeychain);
let xtx_id = await xchain.issueTx(Tx);


// IMPORT TX INTO C-CHAIN FROM X-CHAIN 
let u = await cchain.getUTXOs(cAddressStrings[0], "X");
let intxoSet = u.utxos;
let intxo = intxoSet.getAllUTXOs();

let importedIns = [];
let evmOutputs = [];

let cAddresses = cchain.keyChain().getAddresses();
cHexAddress = "0x8db97C7cEcE249c2b98bDC0226Cc4C2A57BF52FC";

cAddresses[0].toString('hex');

intxo.forEach((utxo) => { assetID = utxo.getAssetID(); txid = utxo.getTxID(); outputidx = utxo.getOutputIdx(); output = utxo.getOutput(); amt = output.getAmount().clone(); input = new avalanche.evm.SECPTransferInput(amt); input.addSignatureIdx(0, cAddresses[0]); xferin = new avalanche.evm.TransferableInput(txid, outputidx, assetID, input); importedIns.push(xferin); evmOutput = new avalanche.evm.EVMOutput(cHexAddress, amt, assetID); evmOutputs.push(evmOutput);});

let cChainBlockchainIdStr = cchain.getBlockchainID();
let cChainBlockchainIdBuf = bintools.cb58Decode(cChainBlockchainIdStr);
let xChainBlockchainIdStr = xchain.getBlockchainID();
let xChainBlockchainIdBuf = bintools.cb58Decode(xChainBlockchainIdStr);


let importTx = new avalanche.evm.ImportTx(12345, cChainBlockchainIdBuf, xChainBlockchainIdBuf, importedIns, evmOutputs);

let unsignedTx = new avalanche.evm.UnsignedTx(importTx);
let tx = unsignedTx.sign(cKeychain);
let id = await cchain.issueTx(tx);

*/