#!/bin/bash

# based on code developed by Sovrin:  https://github.com/hyperledger/aries-acapy-plugin-toolbox

if [[ ! "${NGROK_NAME}" = "" ]]; then
    echo "using ngrok end point [$NGROK_NAME]"

    NGROK_ENDPOINT=null
    while [ -z "$NGROK_ENDPOINT" ] || [ "$NGROK_ENDPOINT" = "null" ]
    do
        # original get endpoint 
        #NGROK_ENDPOINT=$(curl -s $NGROK_NAME:4040/api/tunnels/command_line | grep -o "https:\/\/.*\.ngrok\.io")
        echo "Fetching end point from ngrok service [$NGROK_NAME] for [$CONTAINER_NAME] ..."
        NGROK_ENDPOINT=$(curl --silent $NGROK_NAME:4040/api/tunnels | ./jq -r --arg CONTAINER_NAME "$CONTAINER_NAME" 'first(.tunnels[] | select(.proto=="https" and (.name | index($CONTAINER_NAME))) | .public_url)')

        if [ -z "$NGROK_ENDPOINT" ] || [ "$NGROK_ENDPOINT" = "null" ]; then
            echo "ngrok not ready, sleeping 5 seconds...."
            sleep 5
        fi
    done

    export AGENT_PUBLIC_ENDPOINT=$NGROK_ENDPOINT
    echo "fetched end point [$AGENT_PUBLIC_ENDPOINT]"
fi

echo "Starting Credo agent ..."

#yarn ts-node src/index.ts "$@"
#yarn node --loader ts-node/esm src/index.ts "$@"
yarn tsx src/index.ts "$@"
