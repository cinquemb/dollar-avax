# Chain-based modeling

To model xSD system behavior, you can run it on a local blockchain using the
Truffle project in this directory.

First, you need to install the dependencies in this directory:

```
npm install
```

Then, you need AvalancheGo, AvalancheJs and Truffle installed:

```
go get -v -d github.com/ava-labs/avalanchego/...
cd $GOPATH/src/github.com/ava-labs/avalanchego
./scripts/build.sh
PATH=$GOPATH/src/github.com/ava-labs/avalanchego/build/:$PATH
export PATH
npm install -g truffle
npm install avalanche

```

Finally, you can run the wrapper script, which will start avalanchego, deploy the contracts into it, install necessary Python dependencies, run the `model.py` modeling script, and clean up temporary files afterward.

```
./run.sh
```

If you are editing the model, you can run:

```
RUN_SHELL=1 ./run.sh
```


Then you can run `./model.py` in that shell multiple times, against the same prepared chain. To tear down the chain, just `exit`.



