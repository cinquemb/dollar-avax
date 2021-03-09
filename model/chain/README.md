# Chain-based modeling

To model xSD system behavior, you can run it on a local blockchain using the
Truffle project in this directory.

First, you need to install the dependencies in this directory:

```
npm install
```

Then, you need Ganache and Truffle installed:

```
npm install -g ganache-cli
npm install -g truffle
```

Finally, you can run the wrapper script, which will start Ganache, deploy the contracts into it, install necessary Python dependencies, run the `model.py` modeling script, and clean up temporary files afterward.

```
./run.sh
```

If you are editing the model, you can run:

```
RUN_SHELL=1 ./run.sh
```

You will need to run at the sime time when deploying the contracts, then kill it once its finished before running the model
```
./force_mine.sh
```

Then you can run `./model.py` in that shell multiple times, against the same prepared chain. To tear down the chain, just `exit`.



