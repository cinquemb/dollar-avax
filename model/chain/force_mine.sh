while true; do
	curl -H "Content-Type: application/json" -X POST --data '{"id":1337,"jsonrpc":"2.0","method":"evm_mine","params":[]}' http://localhost:7545
	echo ''
	sleep 1
done