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
#: '
time rsync -a --delete ./empty_db/ ./db/
rm -Rf db go-ethereum-keystore*
#'

# Have a function to kill off Ganache and clean up the database when we quit.
function cleanup {
    #echo "Stopping Ganache (${GANACHE})..."
    echo "Stopping AvalancheGo (${GANACHE})..."
    # Kill Ganache if not dead already
    kill "${GANACHE}" 2>/dev/null || true
    # Clean database
    echo "Cleaning Up Database..."
    mkdir -p ./empty_db
    if [[ "${SAVE_STATE}" == "1" ]] ; then
        echo "Just Kidding... Leaving Database Alone"
    else
        time rsync -a --delete ./empty_db/ ./db/
        rm -Rf db go-ethereum-keystore*
        rm *-approvals.json
    fi
}

trap cleanup EXIT

: '
# THIS IS NEEDED TO CHECK FOR DIFFS BETWEEN UPDATES
diff $GOPATH/pkg/mod/github.com/ava-labs/coreth@\@v0.3.26/plugin/evm/client.go $GOPATH/pkg/mod/github.com/ava-labs/coreth@\@v0.3.27/plugin/evm/client.go
diff $GOPATH/pkg/mod/github.com/ava-labs/coreth@\@v0.3.26/plugin/evm/service.go $GOPATH/pkg/mod/github.com/ava-labs/coreth@\@v0.3.27/plugin/evm/service.go
diff $GOPATH/pkg/mod/github.com/ava-labs/coreth@\@v0.3.26/miner/worker.go $GOPATH/pkg/mod/github.com/ava-labs/coreth@\@v0.3.27/miner/worker.go
'

# Start the chain
# Need to run the below command in a while loop when deploying locally
echo "Starting AvalancheGo..."

#TMPDIR="$(pwd)" avalanchego --network-id=local --staking-enabled=false --snow-sample-size=1 --snow-quorum-size=1 --db-dir=./db/ --http-port=9545 --log-level=verbo --log-dir=./db/ --snow-avalanche-batch-size=1 
TMPDIR="$(pwd)" avalanchego --config-file=./config.json > ganache_output.txt &
GANACHE=$!

# Wait for it to come up
#echo "Waiting for Ganache..."
echo "Waiting for AvalancheGo..."
#while ! grep "^Listening on" ganache_output.txt 2>/dev/null ; do
while ! grep -i "listening on" ganache_output.txt 2>/dev/null ; do
    sleep 1
done

echo "Advancing the clock..."
curl -X POST --data '{ "jsonrpc":"2.0", "id" :1, "method" :"debug_increaseTime", "params" : [3770166]}' -H 'content-type:application/json;' http://127.0.0.1:9545/ext/bc/C/rpc

#: '
# Creating accounts
echo "Creating deploy test accounts..."
time truffle exec make_accounts.js --network development > make_accounts_output.txt
# Run the deployment
echo "Deploying contracts..."
time truffle migrate --reset --skip-dry-run --network=development | tee deploy_output.txt
echo "Creating sim test accounts..."
time truffle exec make_accounts.js --network development --max-accounts 20 >> make_accounts_output.txt

#truffle migrate --reset --network=development | tee deploy_output.txt
#'
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


