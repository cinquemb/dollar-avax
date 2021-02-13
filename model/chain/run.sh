#!/usr/bin/env bash
# run.sh: run the model against a clean testnet, and clean up afterwards

set -e

# We keep our Ganache database right here, in ./db, because one time it
# entirely hosed a system by taking up the whole /tmp. Note that it can quickly
# and easily grow to tens of thousands of files! Make sure you have the inodes
# to spare!

# Clean it out
echo "Cleaning Old Database..."
rm -Rf db

# Have a function to kill off Ganache and clean up the database when we quit.
function cleanup {
    echo "Stopping Ganache (${GANACHE})..."
    # Kill Ganache if not dead already
    kill "${GANACHE}" 2>/dev/null || true
    # Clean database
    echo "Cleaning Up Database..."
    rm -Rf db
}

trap cleanup EXIT

# Start the chain
echo "Starting Ganache..."
TMPDIR="$(pwd)" ganache-cli --p 7545 --gasLimit 8000000 --accounts 2000 --defaultBalanceEther 1000000 --db ./db >ganache_output.txt &
#TMPDIR="$(pwd)" ganache-cli --p 7545 --gasLimit 8000000 --accounts 2000 --defaultBalanceEther 1000000 --blockTime 1 --db ./db >ganache_output.txt &
GANACHE=$!

# Wait for it to come up
echo "Waiting for Ganache..."
while ! grep "^Listening on" ganache_output.txt 2>/dev/null ; do
    sleep 1
done

# Run the deployment
echo "Deploying contracts..."
truffle migrate --reset --network=development | tee deploy_output.txt

if [[ ! -e venv ]] ; then
    # Set up the virtual environment
    echo "Preparing Virtual Environment..."
    virtualenv --python python3 venv
    . venv/bin/activate
    pip3 install -r requirements.txt
else
    # Just go into it
    echo "Entering Virtual Environment..."
    . venv/bin/activate
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




