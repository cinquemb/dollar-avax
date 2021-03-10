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