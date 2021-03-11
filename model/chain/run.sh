#!/usr/bin/env bash
# run.sh: run the model against a clean testnet, and clean up afterwards

set -e

# We keep our Ganache database right here, in ./db, because one time it
# entirely hosed a system by taking up the whole /tmp. Note that it can quickly
# and easily grow to tens of thousands of files! Make sure you have the inodes
# to spare!

# Clean it out
echo "Cleaning Old Database..."
mkdir -p ./empty_db
time rsync -a --delete ./empty_db/ ./db/
rm -Rf db go-ethereum-keystore*

# Have a function to kill off Ganache and clean up the database when we quit.
function cleanup {
    #echo "Stopping Ganache (${GANACHE})..."
    echo "Stopping AvalancheGo (${GANACHE})..."
    # Kill Ganache if not dead already
    kill "${GANACHE}" 2>/dev/null || true
    # Clean database
    echo "Cleaning Up Database..."
    mkdir -p ./empty_db
    time rsync -a --delete ./empty_db/ ./db/
    rm -Rf db go-ethereum-keystore*
}

trap cleanup EXIT

# Start the chain
#echo "Starting Ganache..."
# Need to run the below command in a while loop when deploying locally
# curl -H "Content-Type: application/json" -X POST --data '{"id":1337,"jsonrpc":"2.0","method":"evm_mine","params":[]}' http://localhost:7545
echo "Starting AvalancheGo..."
TMPDIR="$(pwd)" avalanchego --network-id=local --staking-enabled=false --snow-sample-size=1 --snow-quorum-size=1 --db-dir=./db/ --http-port=9545  > ganache_output.txt &
#TMPDIR="$(pwd)" ganache-cli --p 7545 --gasLimit 8000000 --accounts 20 --defaultBalanceEther 1000000 --db ./db --noVMErrorsOnRPCResponse > ganache_output.txt &
#TMPDIR="$(pwd)" ganache-cli --p 7545 --gasLimit 8000000 --accounts 20 --defaultBalanceEther 1000000 --blockTime 604800 --db ./db --noVMErrorsOnRPCResponse  >ganache_output.txt &
GANACHE=$!

# Wait for it to come up
#echo "Waiting for Ganache..."
echo "Waiting for AvalancheGo..."
#while ! grep "^Listening on" ganache_output.txt 2>/dev/null ; do
while ! grep -i "listening on" ganache_output.txt 2>/dev/null ; do
    sleep 1
done


# Creating accounts
echo "Creating test accounts..."
time truffle exec make_accounts.js --network development >> ganache_output.txt
# Run the deployment
echo "Deploying contracts..."
truffle migrate --reset --skip-dry-run --network=development | tee deploy_output.txt

#truffle migrate --reset --network=development | tee deploy_output.txt

if [[ ! -e venv ]] ; then
    # Set up the virtual environment
    echo "Preparing Virtual Environment..."
    virtualenv --python python3 venv
    . venv/bin/activate
    pip3 install -r requirements.txt
    time python -m py_compile model.py
else
    # Just go into it
    echo "Entering Virtual Environment..."
    . venv/bin/activate
    time python -m py_compile model.py
fi

if [[ "${RUN_SHELL}" == "1" ]] ; then
    # Run a shell so that you can run the model several times
    echo "Running Interactive Shell..."
    bash
else
    # Run the model
    echo "Running Model..."
    ./model.py
fi


# grep -P "^  Gas usage: .{6,}" ganache_output.txt | wc -l
# grep -P "^  Gas usage: .{0,}" ganache_output.txt | wc -l


