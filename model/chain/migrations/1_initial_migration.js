const Migrations = artifacts.require("Migrations");

module.exports = function(deployer) {
  deployer.deploy(Migrations);
/*
  deployer.then(async() => {
    console.log(deployer.network);
    switch (deployer.network) {
      case 'development':
        await deployer.deploy(Migrations);
        break;
      default:
        throw("Unsupported network");
    }
  })*/
};